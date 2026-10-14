"""Write a new entry skeleton. Placeholders stay until the author replaces them; `check` reports them."""
from datetime import date
import re

from . import KB, Invalid, entries, frontmatter, gitutil, globs, require

DIRS = {'rule': 'rules', 'decision': 'decisions', 'lesson': 'lessons'}
BODIES = {
    'rule': '（待填写：必须保持的行为，条件与例外写在一起）\n\n## 依据\n（待填写：业务来源）\n',
    'decision': '（待填写：背景与决定）\n\n## 备选\n- （待填写：真实备选及不采用的理由）\n\n## 后果\n（待填写）\n',
    'lesson': ('现象：（待填写）\n根因：（待填写）\n修复与防护：（待填写）\n'
               '发现方法：（待填写）\n适用条件：（待填写）\n'),
}


def run(root, kind, slug, title, scopes, sources, tags=(), status='accepted', verified_at_head=False, today=None):
    require(kind in DIRS, f'种类只能是 {"、".join(DIRS)}')
    require(re.fullmatch(entries.SLUG, slug or ''), 'slug 只能用小写字母、数字和连字符')
    require(title and title.strip(), '需要 --title')
    require(scopes, '至少需要一个 --scope（如 self:internal/biz/**）')
    require(sources, '至少需要一个 --source（Issue、PR、提交链接或 仓库:原文路径）')
    for value in scopes:
        issue = globs.split(value)[2]
        require(not issue, f'--scope {value}：{issue}')
    require(kind == 'decision' or status == 'accepted', '--status 只用于 decision')
    require(status in ('accepted', 'rejected'), '--status 只能是 accepted 或 rejected')
    today = today or date.today().isoformat()
    name = f'{slug}.md' if kind == 'rule' else f'{today}-{slug}.md'
    relative = f'{KB}/{DIRS[kind]}/{name}'
    path = root / relative
    fields = {'title': title.strip(), 'scope': list(scopes), 'source': list(sources)}
    if kind == 'decision':
        fields['status'] = status
    if tags:
        fields['tags'] = list(tags)
    if verified_at_head:
        head = gitutil.head(root)
        require(head, '仓库还没有提交，无法使用 --verified-at-head')
        fields['verified'] = {'self': {'commit': head, 'date': today}}
    text = frontmatter.dump(fields, f'# {title.strip()}\n\n{BODIES[kind]}')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise Invalid(f'{relative} 已存在') from exc
    note = '' if verified_at_head else '；核对代码后填写 verified（或重新生成时加 --verified-at-head）'
    return {'path': relative, 'next': f'把（待填写）替换为实际内容{note}，然后运行 tw check'}
