"""Knowledge entries under `.tw/`: classification, parsing and file-local validation."""
from dataclasses import dataclass, field
from datetime import date
import json
import re

from . import KB, frontmatter, globs

KIND_DIRS = {'rules': 'rule', 'decisions': 'decision', 'lessons': 'lesson'}
SINGLE = {'overview.md': 'overview', 'glossary.md': 'glossary'}
OWN = ('.gitignore', 'config.json')
LIST_FIELDS = ('scope', 'source', 'guards', 'symbols', 'tags', 'related')
ALLOWED = {
    'overview': {'title', 'source', 'verified'},
    'glossary': {'title', 'source', 'verified'},
    'rule': {'title', 'scope', 'source', 'verified', 'guards', 'symbols', 'tags', 'related', 'owner'},
    'decision': {'title', 'scope', 'source', 'verified', 'status', 'symbols', 'tags', 'related', 'owner'},
    'lesson': {'title', 'scope', 'source', 'verified', 'guards', 'symbols', 'tags', 'related', 'owner'},
}
REQUIRED = {
    'overview': {'title', 'source'}, 'glossary': {'title', 'source'},
    'rule': {'title', 'scope', 'source', 'verified'}, 'decision': {'title', 'scope', 'source', 'status'},
    'lesson': {'title', 'scope', 'source', 'verified'},
}
LIMITS = {'overview': 1200, 'rule': 3000, 'decision': 3000, 'lesson': 3000}
SLUG = r'[a-z0-9]+(?:-[a-z0-9]+)*'
DATED = re.compile(rf'^(\d{{4}}-\d{{2}}-\d{{2}})-{SLUG}\.md$')
UNDATED = re.compile(rf'^{SLUG}\.md$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
GUARD = re.compile(r'^(?:check:[A-Za-z0-9._-]+|[A-Za-z0-9._-]+:[^#\s][^#]*#\S.*)$')
PLACEHOLDER = re.compile(r'__[A-Z][A-Z0-9_]*__|[（(]待填写[^）)]*[）)]|待补充|(?<![A-Za-z0-9_])(?:TODO|TBD)(?![A-Za-z0-9_])')
ABANDONED = '放弃过的做法'
WARNINGS = (
    (re.compile(r'本次[^。\n]{0,40}(?:通过|失败)'), '像是一次性的运行结果'),
    (re.compile(r'\d+\s*(?:项|个|条)?\s*(?:测试|用例|tests?)?[^。\n\d]{0,6}(?:全部)?(?:通过|passed|failed)'), '像是测试计数'),
    (re.compile(r'\.(?:go|py|ts|tsx|js|jsx|java|kt|rs|rb|swift|c|cc|cpp|h|hpp|cs|php|sql|proto)(?::|#L)\d+'), '含行号锚点'),
    (re.compile(r'(?:CodeStable|codestable|team-workflow)\s*v?\d+\.\d+\.\d+'), '含工具版本'),
)


@dataclass
class Entry:
    kind: str
    ref: str
    repo: str = 'self'
    fields: dict = field(default_factory=dict)
    body: str = ''
    errors: list = field(default_factory=list)

    @property
    def title(self):
        value = self.fields.get('title')
        return value.strip() if isinstance(value, str) else ''

    @property
    def path(self):
        return f'{KB}/{self.ref}'

    @property
    def label(self):
        return self.ref if self.repo == 'self' else f'{self.repo}:{self.ref}'

    def values(self, name):
        value = self.fields.get(name)
        return [x for x in value if isinstance(x, str) and x.strip()] if isinstance(value, list) else []

    def scopes(self):
        """Valid (repo, pattern) pairs; invalid ones are reported by `validate`."""
        pairs = []
        for value in self.values('scope'):
            repo, pattern, issue = globs.split(value)
            if not issue:
                pairs.append((repo, pattern))
        return pairs

    def verified(self, repo='self'):
        value = self.fields.get('verified')
        item = value.get(repo) if isinstance(value, dict) else None
        return item if isinstance(item, dict) else None

    def text(self):
        """Body without its level-one title line."""
        lines = self.body.strip('\n').split('\n')
        if lines and lines[0].startswith('# '):
            lines = lines[1:]
        return '\n'.join(lines).strip()


def classify(names):
    """Split `.tw/` paths into entry candidates [(kind, ref)] and stray files."""
    found, strays = [], []
    for name in names:
        if not name.startswith(KB + '/'):
            continue
        ref = name[len(KB) + 1:]
        if ref.startswith('local/') or ref in OWN:
            continue
        if ref in SINGLE:
            found.append((SINGLE[ref], ref))
            continue
        parts = ref.split('/')
        if len(parts) == 2 and parts[0] in KIND_DIRS and parts[1].endswith('.md'):
            found.append((KIND_DIRS[parts[0]], ref))
        else:
            strays.append(name)
    return found, strays


def load(kind, ref, text, repo='self'):
    fields, body, errors = frontmatter.parse(text)
    return Entry(kind, ref, repo, fields, body, list(errors))


def sections(body):
    """Level-two headings and their text."""
    result, current, lines = {}, None, []
    for line in body.split('\n'):
        if line.startswith('## '):
            if current is not None:
                result[current] = '\n'.join(lines).strip()
            current, lines = line[3:].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        result[current] = '\n'.join(lines).strip()
    return result


def abandoned(body):
    """Items of the `## 放弃过的做法` section; each item is a top-level `- ` bullet with indented continuation."""
    text = sections(body).get(ABANDONED)
    if text is None:
        return None
    items, current = [], None
    for line in text.split('\n'):
        if line.startswith('- '):
            current = [line[2:].strip()]
            items.append(current)
        elif current is not None and line.startswith((' ', '\t')) and line.strip():
            current.append(line.strip())
        elif line.strip():
            current = None
    return ['\n'.join(item) for item in items]


def label_value(item, name):
    match = re.search(rf'{name}\s*[:：]\s*(\S[^\n]*)', item)
    return match.group(1).strip() if match else ''


def valid_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def verified_problems(value):
    if not isinstance(value, dict) or not value:
        return ['verified 应为 {"仓库": {"commit": 完整提交哈希, "date": "YYYY-MM-DD"}}']
    problems = []
    for repo, item in value.items():
        if not isinstance(item, dict) or set(item) != {'commit', 'date'}:
            problems.append(f'verified.{repo} 只能包含 commit 和 date')
            continue
        commit = item['commit']
        if commit is not None and not (isinstance(commit, str) and HEX40.match(commit)):
            problems.append(f'verified.{repo}.commit 应为 40 位提交哈希；非 git 项目写 null')
        if not valid_date(item['date']):
            problems.append(f'verified.{repo}.date 应为 YYYY-MM-DD')
    return problems


def validate(entry):
    """File-local errors and warnings; repository-level checks live in `check`."""
    errors, warnings = list(entry.errors), []
    values = entry.fields
    for key in values:
        if key not in ALLOWED[entry.kind]:
            errors.append(f'{entry.kind} 不使用字段：{key}')
    missing = {key for key in REQUIRED[entry.kind] if values.get(key) in (None, '', [], {})}
    errors.extend(f'缺少必填字段：{key}' for key in sorted(missing))
    values = {key: value for key, value in values.items() if key not in missing}
    if 'title' in values and not entry.title:
        errors.append('title 必须是非空字符串')
    for key in LIST_FIELDS:
        value = values.get(key)
        if key in values and not (isinstance(value, list) and value and all(isinstance(x, str) and x.strip() for x in value)):
            errors.append(f'{key} 必须是非空字符串数组')
    if 'owner' in values and not (isinstance(values['owner'], str) and values['owner'].strip()):
        errors.append('owner 必须是非空字符串')
    if entry.kind == 'decision' and 'status' in values and values['status'] not in ('accepted', 'rejected'):
        errors.append('decision 的 status 只能是 accepted 或 rejected')
    if 'verified' in values:
        errors.extend(verified_problems(values['verified']))
    for value in entry.values('scope'):
        repo, pattern, issue = globs.split(value)
        if issue:
            errors.append(f'scope {value}：{issue}')
        elif pattern.rstrip('/') == '**':
            warnings.append(f'scope {value} 覆盖整个仓库，范围过宽')
    for value in entry.values('guards'):
        if not GUARD.match(value):
            errors.append(f'guards {value} 应写成 `仓库:测试路径#测试名` 或 `check:检查名`')
    errors.extend(name_problems(entry))
    first = next((line for line in entry.body.split('\n') if line.strip()), '')
    if entry.title and first.strip() != f'# {entry.title}':
        errors.append('正文第一行应为 `# 标题`，并与 title 一致')
    raw = entry.body + json.dumps(values, ensure_ascii=False)
    for hit in sorted(set(PLACEHOLDER.findall(raw))):
        errors.append(f'残留占位内容：{hit}')
    limit = LIMITS.get(entry.kind)
    size = len(entry.body.strip())
    if limit and size > limit:
        errors.append(f'正文 {size} 字符，超过上限 {limit}')
    if entry.kind in ('rule', 'decision', 'lesson'):
        errors.extend(abandoned_problems(entry.body))
    for pattern, reason in WARNINGS:
        hit = pattern.search(entry.body)
        if hit:
            warnings.append(f'{reason}：“{hit.group(0)}”，现行知识不记录一次性结果、工具版本或行号')
    return errors, warnings


def name_problems(entry):
    name = entry.ref.rsplit('/', 1)[-1]
    if entry.kind == 'rule' and not UNDATED.match(name):
        return ['文件名应为 <slug>.md（小写字母、数字、连字符）']
    if entry.kind in ('decision', 'lesson'):
        match = DATED.match(name)
        if not match:
            return ['文件名应为 YYYY-MM-DD-<slug>.md']
        if not valid_date(match.group(1)):
            return [f'文件名中的日期不合法：{match.group(1)}']
    return []


def abandoned_problems(body):
    items = abandoned(body)
    if items is None:
        return []
    if not items:
        return [f'“{ABANDONED}”一节应以 `- ` 列出每项做法']
    return [f'“{ABANDONED}”第 {index} 项缺少{name}'
            for index, item in enumerate(items, 1) for name in ('放弃原因', '来源', '关键词') if not label_value(item, name)]


TERM = re.compile(r'^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$')
AVOID = re.compile(r'^_Avoid_\s*[:：]\s*(.*)$')


def glossary_terms(body):
    """MATT GLOSSARY format: `**Term**:` line, definition lines, optional `_Avoid_: a, b`."""
    terms, current = [], None
    for line in body.split('\n'):
        stripped = line.strip()
        match = TERM.match(stripped)
        if match:
            current = {'term': match.group(1).strip(), 'aliases': [], 'text': [match.group(2).strip()] if match.group(2).strip() else []}
            terms.append(current)
        elif current is None:
            continue
        elif not stripped or stripped.startswith('#'):
            current = None
        else:
            avoid = AVOID.match(stripped)
            if avoid:
                current['aliases'] = [x.strip() for x in re.split(r'[,，、]', avoid.group(1)) if x.strip()]
            else:
                current['text'].append(stripped)
    return [{'term': t['term'], 'aliases': t['aliases'], 'text': ' '.join(t['text'])} for t in terms]
