"""技能文字发布规则的数据与通用检查；仅使用标准库。"""
import re
from pathlib import Path
from urllib.parse import unquote

DOC_ROOTS = ('skills/team-workflow', 'skills/team-knowledge')
EXCLUDED = ('guidance-global.md', 'guidance-project.md')
RULES = (
    {'name': 'concepts', 'scope': DOC_ROOTS,
     'forbidden': (r'工具不执行关闭', r'团队约定，工具不强制'),
     'unique': ((r'仅一位平台负责人', 'skills/team-workflow/references/coordination.md'),
                (r'未指明用例', 'skills/team-workflow/references/contracts.md'),
                (r'简单任务：短方案', 'skills/team-workflow/references/designs.md'),
                (r'^## 工具做什么', 'skills/team-workflow/references/contracts.md')),
     'reachable': ('skills/team-workflow/SKILL.md',
                   ('skills/team-workflow/references/coordination.md',
                    'skills/team-workflow/references/designs.md',
                    'skills/team-workflow/references/contracts.md'))},
    {'name': 'versions', 'scope': DOC_ROOTS,
     'forbidden': (r'兼容旧|第[一二三四五六七八九十]版|行为不变|原行为|不再',)},
    {'name': 'negative-chains', 'scope': DOC_ROOTS,
     'forbidden': (r'只有[^。；]{0,100}才',
                   r'没有[^。；]{0,80}前\s*不',
                   # 否定条件推出否定结论；可跨硬换行，止于句末、列表项、表格行与标题
                   r'(?:未|没有|缺(?!陷|口))(?:(?!\n\s*[-|#*]|\n\s*\d+\.)[^。；，,]){0,60}时'
                   r'(?:(?!\n\s*[-|#*]|\n\s*\d+\.)[^。；]){0,40}?(?:仍未|未完成|未通过|未执行|不(?:能|得|可|会|应|算)|无法)')},
    {'name': 'links', 'scope': ('skills',), 'links': True},
    {'name': 'retest-board', 'scope': DOC_ROOTS,
     'required': (('skills/team-workflow/references/scenarios.md',
                   ('项目代理按本节搭建看板', '读取场景文件与', '按 `pending` 展示待执行项',
                    '让人填写状态、实际结果、执行者、时间、证据与缺陷链接',
                    '导出结果契约文件与证据目录', '用 `scenarios submit` 登记', '登记到 `context`')) ,),
     'source_forbidden': (('skills/team-knowledge/scripts/tw_runtime/team',
          r'http\.server|socketserver|\b(?:HTTPServer|ThreadingHTTPServer|TCPServer|serve_forever|FastAPI|Flask|uvicorn)\b'),),
     'commands': ('skills/team-knowledge/scripts/tw_runtime/team/workflow.py',
                  r"actions.add_parser\('([^']+)'", ('check', 'import-cases', 'coverage', 'pending', 'submit', 'carry'))},
)


def issue(root, path, text, offset, message):
    return {'path': path.relative_to(root).as_posix(), 'line': text.count('\n', 0, offset) + 1, 'problem': message}


def links(root, path, text, *, skills_only=True):
    errors, edges = [], []
    # Keep offsets intact when removing fenced examples.
    body = re.sub(r'```.*?```', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
    for m in re.finditer(r'\]\(([^)]+)\)', body):
        link = m[1].strip().removeprefix('<').removesuffix('>')
        if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', link) or link.startswith('//'):
            continue
        local = unquote(link.split('#')[0])
        target = (path.parent / local).resolve() if local else path.resolve()
        edges.append(target)
        if skills_only and not target.is_relative_to((root / 'skills').resolve()):
            errors.append(issue(root, path, text, m.start(), '相对链接的目标位于 skills/ 内：' + link))
        elif not target.is_file():
            errors.append(issue(root, path, text, m.start(), '相对链接的目标文件可读取：' + link))
        elif '#' in link and target.suffix == '.md':
            import unicodedata
            def slug(value):
                value = ''.join(c for c in value.strip().lower() if c in ' -_' or unicodedata.category(c)[0] in 'LN')
                return value.replace(' ', '-')
            headings = {slug(h[1]) for h in re.finditer(r'^#{1,6}\s+(.+?)\s*$', target.read_text(), re.M)}
            anchor = unquote(link.partition('#')[2]).lower()
            if anchor and anchor not in headings:
                errors.append(issue(root, path, text, m.start(), '相对链接引用已有标题：' + link))
    return errors, edges


def check(root):
    root = Path(root).resolve()
    results = []
    for rule in RULES:
        files = sorted({p for scope in rule['scope'] for p in (root / scope).rglob('*.md') if p.name not in EXCLUDED})
        texts = {p: p.read_text(encoding='utf-8') for p in files}
        errors = []
        for path, text in texts.items():
            checked = text
            for pattern in rule.get('forbidden', ()):
                for m in re.finditer(pattern, checked, re.M):
                    errors.append(issue(root, path, text, m.start(), '按发布规则调整正文：' + rule['name']))
            if rule.get('links'):
                errors += links(root, path, text)[0]
        for pattern, owner in rule.get('unique', ()):
            found = [(p, text, m.start()) for p, text in texts.items() for m in re.finditer(pattern, text, re.M)]
            if len(found) != 1 or found[0][0] != root / owner:
                errors += [issue(root, p, text, offset, '概念正文集中在 ' + owner) for p, text, offset in found]
                if not found:
                    errors.append({'path': owner, 'line': 1, 'problem': '填写概念的唯一正文：' + pattern})
        for name, tokens in rule.get('required', ()):
            path = root / name
            text = texts.get(path, '')
            for token in tokens:
                if token not in text:
                    errors.append({'path': name, 'line': 1, 'problem': '补齐说明：' + token})
        if rule.get('reachable'):
            entry, targets = rule['reachable']
            todo, seen = [root / entry], set()
            while todo:
                path = todo.pop().resolve()
                if path in seen:
                    continue
                seen.add(path)
                if path in texts:
                    todo += [p for p in links(root, path, texts[path])[1] if p in texts]
            for target in targets:
                if root / target not in seen:
                    errors.append({'path': entry, 'line': 1, 'problem': '技能入口通过链接可到达：' + target})
        for directory, pattern in rule.get('source_forbidden', ()):
            for path in sorted((root / directory).rglob('*.py')):
                text = path.read_text(encoding='utf-8')
                for m in re.finditer(pattern, text):
                    errors.append(issue(root, path, text, m.start(), '场景服务职责按规则保留在项目中：' + rule['name']))
        if rule.get('commands'):
            name, pattern, expected = rule['commands']
            path = root / name
            actual = re.findall(pattern, path.read_text()) if path.is_file() else []
            if actual != list(expected):
                errors.append({'path': name, 'line': 1, 'problem': '场景命令与结果契约一致：' + ', '.join(expected)})
        results.append({'name': rule['name'], 'errors': errors})
    return results
