"""技能文字发布规则的数据与通用检查；仅使用标准库。"""
import re
from pathlib import Path
from urllib.parse import unquote

DOC_ROOTS = ('skills/team-knowledge',)
RULES = (
    {'name': 'versions', 'scope': DOC_ROOTS,
     'forbidden': (r'兼容旧|第[一二三四五六七八九十]版|行为不变|原行为|不再',)},
    {'name': 'negative-chains', 'scope': DOC_ROOTS,
     'forbidden': (r'只有[^。；]{0,100}才',
                   r'没有[^。；]{0,80}前\s*不',
                   # 否定条件推出否定结论；可跨硬换行，止于句末、列表项、表格行与标题
                   r'(?:未|没有|缺(?!陷|口))(?:(?!\n\s*[-|#*]|\n\s*\d+\.)[^。；，,]){0,60}时'
                   r'(?:(?!\n\s*[-|#*]|\n\s*\d+\.)[^。；]){0,40}?(?:仍未|未完成|未通过|未执行|不(?:能|得|可|会|应|算)|无法)')},
    {'name': 'links', 'scope': ('skills',), 'links': True},

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
        files = sorted({p for scope in rule['scope'] for p in (root / scope).rglob('*.md')})
        texts = {p: p.read_text(encoding='utf-8') for p in files}
        errors = []
        for path, text in texts.items():
            checked = text
            for pattern in rule.get('forbidden', ()):
                for m in re.finditer(pattern, checked, re.M):
                    errors.append(issue(root, path, text, m.start(), '按发布规则调整正文：' + rule['name']))
            if rule.get('links'):
                errors += links(root, path, text)[0]
        results.append({'name': rule['name'], 'errors': errors})
    return results
