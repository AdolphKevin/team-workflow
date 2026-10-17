"""Structural checks of `.tw/`. Zero writes, no tests executed, no judgement of business truth."""
from collections import defaultdict
import re

from . import KB, Invalid, entries, files, gitutil, globs, project as projects, textmatch

KNOWLEDGE = ('rule', 'decision', 'lesson')
LOCAL_MANAGED = {'tasks', 'batches', 'imports', 'validation-active', 'agents', 'cache', 'repositories.json'}
LOCAL_REFERENCE = re.compile(r'''\.tw/local/([^\s/`<>"'\[\](){}*?，。；：、]+)''')


def local_reference_problems(text):
    """Report concrete unmanaged names; a bare root, glob or placeholder names no material."""
    return [f'第 {number} 行引用了仅在本机的材料：{match.group(0)}；请写明结论和关键数据，原件留在执行者本机'
            for number, line in enumerate(text.splitlines(), 1)
            for match in LOCAL_REFERENCE.finditer(line) if match.group(1) not in LOCAL_MANAGED]


def run(project, base=None):
    errors, warnings = [], []

    def error(path, message):
        errors.append({'path': path, 'message': message})

    def warn(path, message):
        warnings.append({'path': path, 'message': message})

    root, names = project.root, project.source.names
    if project.config is None and not project.config_errors:
        error(projects.CONFIG, 'config.json 尚待创建')
    for message in project.config_errors:
        error(projects.CONFIG, message)
    for name in projects.legacy_paths(root):
        error(name, '旧系统目录仍存在：按 team-knowledge 的迁移指南整理后删除，并卸载旧技能')
    ignore_file = root / KB / '.gitignore'
    lines = [x.strip() for x in ignore_file.read_text(encoding='utf-8').splitlines()] if ignore_file.is_file() else []
    if 'local/' not in lines:
        error(f'{KB}/.gitignore', '应包含一行 local/')
    if not gitutil.ignored(root, f'{KB}/local/probe'):
        error(f'{KB}/local/', '没有被 git 忽略')
    tracked = gitutil.tracked_under(root, f'{KB}/local')
    if tracked:
        error(f'{KB}/local/', f'有已跟踪的文件（{", ".join(tracked[:3])}{"…" if len(tracked) > 3 else ""}），用 git rm --cached 移出')
    if gitutil.ignored(root, projects.CONFIG):
        error(KB + '/', '整个目录被忽略规则覆盖，入库知识会丢失；删除根 .gitignore 中的相应条目')
    loaded = project.entries()
    for name in project.strays:
        error(name, '不是知识条目：知识只放在 overview.md、glossary.md、rules/、decisions/、lessons/')
    shared = project.shared()
    config = project.config or {}
    declared = config.get('shared', {}) if isinstance(config.get('shared'), dict) else {}
    checks = config.get('checks', {}) if isinstance(config.get('checks'), dict) else {}
    code = [n for n in names if scope_target(n)]
    labels = {e.label for e in loaded}
    for entry in loaded:
        problems, notes = entries.validate(entry)
        for message in problems:
            error(entry.path, message)
        for message in notes:
            warn(entry.path, message)
        try:
            raw = project.source.read(entry.path)
        except (OSError, UnicodeError, Invalid):
            pass  # load_entries already reports unreadable entries.
        else:
            for message in local_reference_problems(raw):
                error(entry.path, message)
        if entry.kind not in KNOWLEDGE:
            continue
        for alias, pattern in entry.scopes():
            files = scope_files(alias, code, declared, shared)
            if files is None:
                if alias != 'self' and alias not in declared:
                    error(entry.path, f'scope 使用了未在 config.shared 中声明的仓库：{alias}')
                else:
                    warn(entry.path, f'无法读取仓库 {alias}，scope {alias}:{pattern} 未核对')
            elif not any(globs.matches(pattern, f) for f in files):
                (warn if entry.kind == 'decision' else error)(entry.path, f'scope {alias}:{pattern} 匹配不到任何文件')
        for value in entry.values('guards'):
            guard_problem(value, root, project.source, declared, shared, checks, entry, error, warn)
        for value in entry.values('related'):
            repo, sep, ref = value.partition(':')
            if not sep:
                repo, ref = 'self', value
            if repo == 'self':
                if ref.removeprefix(KB + '/') not in labels:
                    error(entry.path, f'related 指向不存在的条目：{value}')
            elif repo not in declared:
                error(entry.path, f'related 使用了未声明的仓库：{repo}')
            elif shared[repo].status != 'ok':
                warn(entry.path, f'无法读取仓库 {repo}，related {value} 未核对')
            elif f'{repo}:{ref.removeprefix(KB + "/")}' not in {e.label for e in shared[repo].entries}:
                error(entry.path, f'related 指向不存在的条目：{value}')
        verified = entry.fields.get('verified')
        if isinstance(verified, dict):
            for alias, info in verified.items():
                if alias != 'self' and alias not in declared:
                    error(entry.path, f'verified 使用了未声明的仓库：{alias}')
                elif alias == 'self' and isinstance(info, dict) and isinstance(info.get('commit'), str) and entries.HEX40.match(info['commit']):
                    if gitutil.run(root, 'cat-file', '-e', f'{info["commit"]}^{{commit}}', check=False).returncode != 0:
                        warn(entry.path, '核实基线提交不在当前历史中（浅克隆或历史被改写），变化情况无法计算')
        if entry.kind == 'lesson' and not entry.values('guards'):
            warn(entry.path, '没有守护测试；能写测试时请补上，并填写 guards')
    titles = defaultdict(list)
    for entry in loaded:
        if entry.kind in KNOWLEDGE and entry.title:
            titles[textmatch.normalize(entry.title)].append(entry.path)
    for paths in titles.values():
        if len(paths) > 1:
            for path in paths:
                warn(path, '与其他条目标题相同，疑似重复：' + '、'.join(p for p in paths if p != path))
    documents(config, code, declared, shared, error, warn, project.source)
    for value in config.get('context', []) if isinstance(config.get('context'), list) else []:
        if isinstance(value, str) and not any(globs.matches(value, f) for f in code):
            error(projects.CONFIG, f'context 中的路径不存在：{value}')
    for alias, repo in sorted(shared.items()):
        if repo.status == 'mismatch':
            error(projects.MAPPING, f'{alias}：{repo.describe()}')
        elif repo.status != 'ok':
            warn(projects.CONFIG, f'共享仓 {alias}：{repo.describe()}')
    legacy_guidance(root, warn)
    if base:
        branch_hints(project, base, loaded, warn)
    return {'ok': not errors, 'entries': len(loaded), 'errors': errors, 'warnings': warnings}


def scope_target(name):
    """Scopes name code and project files; knowledge entries and local state under .tw/ are not targets."""
    if not name.startswith(KB + '/'):
        return True
    return not name.endswith('.md') and not name.startswith(KB + '/local/')


def scope_files(alias, code, declared, shared):
    if alias == 'self':
        return code
    repo = shared.get(alias)
    if alias not in declared or repo is None or repo.status not in ('ok', 'not-migrated'):
        return None
    return [n for n in repo.names if scope_target(n)]


def guard_problem(value, root, source, declared, shared, checks, entry, error, warn):
    if value.startswith('check:'):
        if value[6:] not in checks:
            error(entry.path, f'guards 引用了未配置的检查：{value[6:]}')
        return
    alias, _, rest = value.partition(':')
    path, _, name = rest.partition('#')
    if alias == 'self':
        names, read = source.names, source.read
    elif alias in declared and shared[alias].status in ('ok', 'not-migrated'):
        repo = shared[alias]
        names, read = repo.names, lambda n: (repo.root / n).read_text(encoding='utf-8')
    elif alias in declared:
        warn(entry.path, f'无法读取仓库 {alias}，守护测试 {value} 未核对')
        return
    else:
        error(entry.path, f'guards 使用了未声明的仓库：{alias}')
        return
    if path not in names:
        error(entry.path, f'守护测试文件不存在：{alias}:{path}')
        return
    try:
        found = name in read(path)
    except (OSError, UnicodeDecodeError):
        found = False
    if not found:
        error(entry.path, f'守护测试 {name} 不在 {alias}:{path} 中')


def documents(config, code, declared, shared, error, warn, self_source):
    owners = defaultdict(list)
    docs = config.get('documents', []) if isinstance(config.get('documents'), list) else []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        source = projects.document_source(doc.get('source'))
        if not source or source[0] == 'url':
            continue
        alias, pattern = source
        files = scope_files(alias, code, declared, shared)
        if files is None:
            (warn if alias in declared else error)(projects.CONFIG, f'documents {doc.get("id")}：仓库 {alias} 无法读取或未声明')
            continue
        matched = [f for f in files if globs.matches(pattern, f)]
        if not matched:
            error(projects.CONFIG, f'documents {doc.get("id")} 的原文不存在：{doc.get("source")}')
        for name in matched:
            owners[(alias, name)].append(doc.get('id'))
    for (alias, name), ids in sorted(owners.items()):
        if len(ids) > 1:
            error(projects.CONFIG, f'同一份原文被登记了 {len(ids)} 次（{", ".join(ids)}）：{alias}:{name}')
        label = name if alias == 'self' else f'{alias}:{name}'
        try:
            raw = self_source.read(name) if alias == 'self' else (shared[alias].root / name).read_text(encoding='utf-8')
        except (OSError, UnicodeError, Invalid) as exc:
            error(label, f'无法读取原文：{exc}')
        else:
            for message in local_reference_problems(raw):
                error(label, message)


LEGACY_TEXT = re.compile(r'\.codestable|cs_knowledge|CodeStable|\$cs\b|(?<![A-Za-z])CS(?![A-Za-z])')
GUIDANCE_FILES = ('AGENTS.md', 'CLAUDE.md')


def legacy_guidance(root, warn):
    """Instruction files that still send agents to the old CS outside tool-owned blocks."""
    for name in GUIDANCE_FILES:
        path = root / name
        if not path.is_file():
            continue
        text = files.strip_block(path.read_text(encoding='utf-8'), 'knowledge')
        for number, line in enumerate(text.split('\n'), 1):
            if LEGACY_TEXT.search(line):
                warn(name, f'第 {number} 行仍要求使用旧 CS：“{line.strip()[:60]}”，请改为 team-knowledge 或删除')
                break


def branch_hints(project, base, loaded, warn):
    changed = gitutil.changed_since_ref(project.root, base)
    touched = {n for n in changed if n.startswith(KB + '/')}
    code = sorted(changed - touched)
    for entry in loaded:
        if entry.kind not in KNOWLEDGE or entry.path in touched:
            continue
        patterns = [p for alias, p in entry.scopes() if alias == 'self']
        hits = [c for c in code if any(globs.matches(p, c) for p in patterns)]
        if hits:
            warn(entry.path, f'本分支改动了它的 scope 内代码（{"、".join(hits[:3])}{"…" if len(hits) > 3 else ""}），请确认这条知识是否仍成立')


def render(result):
    lines = [f'检查 {result["entries"]} 个条目：{len(result["errors"])} 个错误，{len(result["warnings"])} 个警告']
    lines += [f'错误 {x["path"]}：{x["message"]}' for x in result['errors']]
    lines += [f'警告 {x["path"]}：{x["message"]}' for x in result['warnings']]
    return '\n'.join(lines) + '\n'
