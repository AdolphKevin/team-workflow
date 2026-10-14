"""Read-only knowledge brief for one task, within a character budget."""
from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from . import Invalid, KB, cache, entries, gitutil, globs, textmatch

KNOWLEDGE = ('rule', 'decision', 'lesson')
EXPLICIT, SCOPE, TEXT, RELATED = range(4)
OVERVIEW_LIMIT, GLOSSARY_LIMIT, NAV_LIMIT = 1200, 400, 600


@dataclass
class Pick:
    entry: object
    root: Path
    tier: int
    specificity: int = 0
    reasons: list = field(default_factory=list)

    def key(self):
        return (self.tier, -self.specificity, -len(self.reasons), self.entry.label)


def relative_paths(root, paths):
    result = []
    for value in paths or ():
        path = Path(value)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(root)
            except ValueError as exc:
                raise Invalid(f'路径不在仓库内：{value}') from exc
        text = path.as_posix()
        while text.startswith('./'):
            text = text[2:]
        if globs.problem(text):
            raise Invalid(f'路径必须是仓库内的相对路径：{value}')
        result.append(text)
    return result


def explicit_label(value):
    value = value.strip()
    repo, sep, ref = value.partition(':')
    if not sep:
        repo, ref = 'self', value
    if ref.startswith(KB + '/'):
        ref = ref[len(KB) + 1:]
    return ref if repo == 'self' else f'{repo}:{ref}'


def applies_here(project, repo, alias):
    """Whether a scope alias written inside `repo` points at the current project."""
    if repo is None:
        return alias == 'self'
    if alias == 'self':
        identity = repo.actual
    else:
        declared = (repo.config or {}).get('shared', {})
        identity = declared.get(alias, {}).get('id') if isinstance(declared, dict) and isinstance(declared.get(alias), dict) else None
    return bool(identity) and identity == project.id


def select(project, task, paths, symbols, refs, tags):
    shared = project.shared()
    candidates = [(e, project.root, None) for e in project.entries() if e.kind in KNOWLEDGE]
    for repo in shared.values():
        candidates += [(e, repo.root, repo) for e in repo.entries if e.kind in KNOWLEDGE]
    picks = {}

    def add(entry, root, tier, reason, specificity=0):
        pick = picks.setdefault(entry.label, Pick(entry, root, tier))
        pick.tier = min(pick.tier, tier)
        pick.specificity = max(pick.specificity, specificity)
        if reason not in pick.reasons:
            pick.reasons.append(reason)

    wanted = {explicit_label(r) for r in refs or ()}
    wanted_tags = {textmatch.normalize(t) for t in tags or ()}
    vocabulary = defaultdict(set)
    for entry, root, repo in candidates:
        if entry.label in wanted:
            add(entry, root, EXPLICIT, '指定条目')
        for symbol in set(symbols or ()) & set(entry.values('symbols')):
            add(entry, root, EXPLICIT, f'符号 {symbol}')
        for alias, pattern in entry.scopes():
            if applies_here(project, repo, alias):
                for path in paths:
                    if globs.matches(pattern, path):
                        add(entry, root, SCOPE, f'路径 {path}', globs.specificity(pattern))
        for tag in entry.values('tags'):
            if textmatch.normalize(tag) in wanted_tags:
                add(entry, root, SCOPE, f'标签 {tag}')
        for phrase in textmatch.title_phrases(entry.title) | textmatch.slug_words(entry.ref):
            vocabulary[phrase].add(entry.label)
        for value in entry.values('tags') + entry.values('symbols'):
            phrase = textmatch.term(value)
            if phrase:
                vocabulary[phrase].add(entry.label)
    terms = glossary_terms(project, shared)
    term_vocabulary = defaultdict(set)
    for index, term in enumerate(terms):
        for name in [term['term'], *term['aliases']]:
            phrase = textmatch.term(name)
            if phrase:
                term_vocabulary[phrase].add(index)
    abandoned_vocabulary = defaultdict(set)
    for entry, root, repo in candidates:
        if entry.kind in KNOWLEDGE:
            for index, item in enumerate(entries.abandoned(entry.body) or []):
                head = item.split('\n', 1)[0]
                keywords = entries.label_value(item, '关键词')
                # Short fragments of a listed head ("盘点、暂存、恢复") match too much; short terms go in 关键词.
                heads = {phrase for phrase in textmatch.title_phrases(head) if len(phrase) >= 4}
                for phrase in heads | {textmatch.term(k) for k in keywords.replace('，', '、').replace(',', '、').split('、') if textmatch.term(k)}:
                    abandoned_vocabulary[phrase].add((entry.label, index))
    hits = textmatch.find(task, set(vocabulary) | set(term_vocabulary) | set(abandoned_vocabulary))
    by_label = {entry.label: (entry, root) for entry, root, _ in candidates}
    for phrase in sorted(hits):
        for label in sorted(vocabulary.get(phrase, ())):
            add(*by_label[label], TEXT, f'词组“{phrase}”')
    matched_terms = sorted({i for phrase in hits for i in term_vocabulary.get(phrase, ())})
    abandoned_hits = sorted({x for phrase in hits for x in abandoned_vocabulary.get(phrase, ())})
    for pick in sorted(picks.values(), key=Pick.key):
        if pick.tier == RELATED:
            continue
        for value in pick.entry.values('related'):
            label = related_label(pick.entry, value)
            if label in by_label:
                entry, root = by_label[label]
                add(entry, root, RELATED, f'由 {pick.entry.label} 关联')
    missing = sorted(wanted - set(by_label))
    for label, index in abandoned_hits:
        entry, root = by_label[label]
        if label not in picks:
            add(entry, root, TEXT, '命中放弃过的做法')
    return sorted(picks.values(), key=Pick.key), [terms[i] for i in matched_terms], abandoned_hits, missing


def related_label(entry, value):
    repo, sep, ref = value.partition(':')
    if not sep:
        repo, ref = 'self', value
    if ref.startswith(KB + '/'):
        ref = ref[len(KB) + 1:]
    if repo == 'self':
        return ref if entry.repo == 'self' else f'{entry.repo}:{ref}'
    return f'{repo}:{ref}' if entry.repo == 'self' else None


def glossary_terms(project, shared):
    terms = []
    sources = [(project.entries(), None)] + [(repo.entries, repo.alias) for repo in shared.values()]
    for loaded, alias in sources:
        for entry in loaded:
            if entry.kind == 'glossary':
                for term in entries.glossary_terms(entry.body):
                    terms.append({**term, 'repo': alias or 'self'})
    return terms


def drift(pick, memo, dirty):
    """How much code in the entry's own scope changed since its verification baseline."""
    info = pick.entry.verified('self')
    if not info:
        return {'state': 'none', 'commits': None, 'text': '未记录核实基线'}
    day, commit = info.get('date'), info.get('commit')
    if not commit:
        return {'state': 'no-commit', 'commits': None, 'text': f'核实于 {day}（无提交基线）'}
    key = (str(pick.root), commit)
    if key not in memo:
        memo[key] = cache.changes(pick.root, commit)
    commits = memo[key]
    if commits is None:
        return {'state': 'unknown', 'commits': None, 'text': f'核实于 {day}，之后的变化未知（基线不在当前历史中）'}
    patterns = [p for alias, p in pick.entry.scopes() if alias == 'self']
    count = sum(1 for _, paths in commits if any(globs.matches(p, x) for p in patterns for x in paths))
    if str(pick.root) not in dirty:
        dirty[str(pick.root)] = gitutil.dirty_paths(pick.root)
    changed = any(globs.matches(p, x) for p in patterns for x in dirty[str(pick.root)])
    text = f'核实于 {day}，之后 scope 内有 {count} 个提交' + ('，另有未提交修改' if changed else '')
    return {'state': 'ok', 'commits': count, 'dirty': changed, 'text': text}


def body_for(entry):
    """Entry text for the brief; inner headings drop one level below the entry title."""
    if entry.kind == 'decision' and entry.fields.get('status') == 'rejected':
        reason = entries.sections(entry.body).get('理由')
        text = reason or entry.text().split('\n\n', 1)[0]
    else:
        text = entry.text()
    return re.sub(r'^(#{2,5}) ', r'#\1 ', text, flags=re.M)


def paragraphs_within(text, limit):
    out, used = [], 0
    for paragraph in text.split('\n\n'):
        if used + len(paragraph) + 2 > limit:
            return '\n\n'.join(out), True
        out.append(paragraph)
        used += len(paragraph) + 2
    return '\n\n'.join(out), False


def build(project, task, paths=(), symbols=(), refs=(), tags=(), budget=6000, index_only=False):
    if not task or not task.strip():
        raise Invalid('需要 --task 描述当前任务')
    if budget < 1000:
        raise Invalid('--budget 不能小于 1000 个字符')
    paths = relative_paths(project.root, paths)
    picks, terms, abandoned_hits, missing = select(project, task, paths, symbols, refs, tags)
    parts, left = [], budget

    def put(text):
        nonlocal left
        parts.append(text)
        left -= len(text)

    put(f'# 任务：{task.strip()}\n\n')
    overview = next((e for e in project.entries() if e.kind == 'overview'), None)
    if overview:
        text, cut = paragraphs_within(overview.text(), OVERVIEW_LIMIT)
        put(f'{text}\n' + ('（总览较长，完整内容：tw read overview.md）\n' if cut else '') + '\n')
    else:
        put('（项目尚无 overview.md）\n\n')
    if terms:
        lines, used = [], 0
        for term in terms:
            avoid = f'（避免：{"、".join(term["aliases"])}）' if term['aliases'] else ''
            line = f'- **{term["term"]}**：{term["text"]}{avoid}\n'
            if used + len(line) > GLOSSARY_LIMIT:
                break
            lines.append(line)
            used += len(line)
        if lines:
            put('## 术语\n' + ''.join(lines) + '\n')
    memo, dirty = {}, {}
    rendered, indexed = [], []
    content_left = left - NAV_LIMIT
    overflow = index_only
    for pick in picks:
        status = drift(pick, memo, dirty)['text']
        block = (f'## {pick.entry.title}{"（已拒绝）" if pick.entry.fields.get("status") == "rejected" else ""}\n'
                 f'{body_for(pick.entry)}\n'
                 f'来源：{"、".join(pick.entry.values("source")) or "未写"} · {status}\n→ {pick.entry.label}\n\n')
        if not overflow and len(block) <= content_left:
            put(block)
            content_left -= len(block)
            rendered.append((pick, status))
        else:
            overflow = True
            indexed.append((pick, status))
    full = {p.entry.label for p, _ in rendered}
    reminders = []
    for label, index in abandoned_hits:
        if label in full:
            continue
        pick = next(p for p in picks if p.entry.label == label)
        item = entries.abandoned(pick.entry.body)[index]
        reminders.append(f'- {item.split(chr(10), 1)[0]} — 放弃原因：{entries.label_value(item, "放弃原因")} → {label}\n')
    nav = []
    if reminders:
        nav.append('## 曾放弃的方向\n' + ''.join(reminders) + '\n')
    if indexed:
        nav.append('## 继续阅读\n' + ''.join(f'- {p.entry.title} → {p.entry.label}（{"；".join(p.reasons[:2])}）\n' for p, _ in indexed) + '\n')
    shared = project.shared()
    if shared:
        nav.append('## 共享仓\n' + ''.join(f'- {alias}：{repo.describe()}\n' for alias, repo in sorted(shared.items())) + '\n')
    commits = gitutil.recent_commits(project.root, paths)
    if commits:
        nav.append('## 相关提交\n' + ''.join(f'- {h} {s}\n' for h, s in commits) + '\n')
    if missing:
        nav.append('## 未找到的条目\n' + ''.join(f'- {m}\n' for m in missing) + '\n')
    omitted = 0
    for section in nav:
        if len(section) <= left:
            put(section)
        else:
            omitted += section.count('\n- ')
    if omitted:
        put(f'（篇幅已满，另有 {omitted} 行未列出；用 `tw brief --index` 或 `--entry` 查看）\n')
    markdown = ''.join(parts).rstrip('\n') + '\n'
    return {
        'task': task.strip(), 'paths': paths, 'chars': len(markdown), 'budget': budget,
        'entries': [{'label': p.entry.label, 'title': p.entry.title, 'kind': p.entry.kind, 'tier': p.tier,
                     'reasons': p.reasons, 'rendered': p.entry.label in full, 'status': status}
                    for p, status in rendered + indexed],
        'terms': [t['term'] for t in terms], 'abandoned': [label for label, _ in abandoned_hits],
        'repositories': {alias: {'status': repo.status, 'description': repo.describe()} for alias, repo in shared.items()},
        'missing': missing, 'omitted_lines': omitted, 'markdown': markdown,
    }


def dumps(result):
    return json.dumps({k: v for k, v in result.items() if k != 'markdown'}, ensure_ascii=False, indent=2)
