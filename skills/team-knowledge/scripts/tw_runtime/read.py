"""Read an entry, a registered document or a repository file in full."""
import html
import re
import urllib.error
import urllib.request

from . import KB, Invalid, globs, project as projects, require
from .brief import explicit_label


def section_of(text, title):
    lines = text.split('\n')
    for index, line in enumerate(lines):
        match = re.match(r'^(#{1,6})\s+(.*)$', line)
        if match and match.group(2).strip() == title.strip():
            level, out = len(match.group(1)), [line]
            for following in lines[index + 1:]:
                deeper = re.match(r'^(#{1,6})\s', following)
                if deeper and len(deeper.group(1)) <= level:
                    break
                out.append(following)
            return '\n'.join(out).strip() + '\n'
    raise Invalid(f'找不到章节：{title}')


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'tw-read'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(2_000_000).decode(response.headers.get_content_charset() or 'utf-8', 'replace')
    except (urllib.error.URLError, OSError) as exc:
        raise Invalid(f'无法读取 {url}：{getattr(exc, "reason", exc)}') from exc
    text = re.sub(r'<(script|style)\b.*?</\1>', '', raw, flags=re.S | re.I)
    return html.unescape(re.sub(r'<[^>]+>', '', text)).strip() + '\n'


def documents(project):
    docs = (project.config or {}).get('documents', [])
    return [d for d in docs if isinstance(d, dict)] if isinstance(docs, list) else []


def repo_root(project, alias):
    if alias == 'self':
        return project.root, project.source.names
    repo = project.shared().get(alias)
    require(repo is not None, f'未声明的仓库：{alias}')
    require(repo.status in ('ok', 'not-migrated'), f'仓库 {alias}：{repo.describe()}')
    return repo.root, repo.names


def run(project, target=None, section=None, online=False, list_documents=False):
    if list_documents:
        return {'documents': [{'id': d.get('id'), 'title': d.get('title'), 'source': d.get('source')} for d in documents(project)]}
    require(target, '需要指定条目、文档编号或文件路径；用 --list 列出已登记的原文')
    docs = {d.get('id'): d for d in documents(project)}
    if target in docs:
        doc = docs[target]
        source = projects.document_source(doc.get('source'))
        require(source, f'documents {target} 的 source 不合法')
        if source[0] == 'url':
            if not online:
                return {'target': target, 'title': doc.get('title'), 'url': source[1],
                        'text': f'{doc.get("title")}：{source[1]}\n（外部链接；加 --online 读取正文）\n'}
            text = fetch(source[1])
            return {'target': target, 'url': source[1], 'text': section_of(text, section) if section else text}
        root, names = repo_root(project, source[0])
        matched = [n for n in names if globs.matches(source[1], n)]
        require(matched, f'documents {target} 的原文不存在：{doc.get("source")}')
        if len(matched) > 1 and not section:
            return {'target': target, 'files': matched,
                    'text': ''.join(f'- {source[0]}:{n}\n' for n in matched) + '（逐个读取：tw read <仓库:路径>）\n'}
        text = (root / matched[0]).read_text(encoding='utf-8')
        return {'target': target, 'path': f'{source[0]}:{matched[0]}', 'text': section_of(text, section) if section else text}
    label = explicit_label(target)
    alias, sep, ref = label.partition(':') if ':' in label else ('self', '', label)
    root, names = repo_root(project, alias)
    for name in (f'{KB}/{ref}', ref):
        if name in names:
            text = (root / name).read_text(encoding='utf-8')
            return {'target': target, 'path': f'{alias}:{name}', 'text': section_of(text, section) if section else text}
    raise Invalid(f'找不到：{target}（可以是条目如 rules/x.md、文档编号或仓库内文件路径）')
