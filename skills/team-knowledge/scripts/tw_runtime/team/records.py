"""The only platform data syntax: reversible JSON inside a safe HTML comment."""
import json
import html
import re

from common import Invalid, require

COMMENT = re.compile(r'<!-- tw-record\s+(.*?)\s+-->', re.S)
LEGACY = re.compile(r'(?m)^\s*```team-workflow-[a-z-]+\b')


def comment(value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    # Escape JSON string tokens, including keys; negative JSON numbers remain valid.
    raw = re.sub(r'"(?:\\.|[^"\\])*"', lambda match: match[0].replace('-', r'\u002d')
                 .replace('<', r'\u003c').replace('>', r'\u003e'), raw)
    return '<!-- tw-record ' + raw + ' -->'


def kind(value):
    if 'kind' not in value and {'parent', 'task', 'data_version'} <= value.keys():
        return 'task'
    if 'draft_id' in value and 'format_version' in value:
        return 'review'
    return {'design-record': 'design', 'approval-record': 'approval', 'handoff': 'handoff',
            'progress': 'progress'}.get(value.get('kind'))


def prose(value):
    """Keep literal HTML/comment syntax visible in generated Markdown."""
    return html.escape(value, quote=False)


def source(body):
    lines, fence = [], None
    for line in body.split('\n'):
        found = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        was_fenced = fence is not None
        if found:
            token = found[1]
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not line[found.end():].strip():
                fence = None
        lines.append(re.sub(r'[^\r\n]', ' ', line) if was_fenced or fence is not None else line)
    return '\n'.join(lines)


def matches(body):
    return list(COMMENT.finditer(source(body)))


def read(body, required=True):
    body = body or ''
    require(not LEGACY.search(body), '旧 team-workflow 代码块已停用，请重新生成草稿，使用隐藏的 tw-record 注释')
    found = matches(body)
    require(len(found) <= 1, 'Multiple structured tw-record records; one platform record is allowed per comment')
    if not found:
        require('<!-- tw-record' not in source(body), 'tw-record 注释不完整，请重新生成草稿')
        require(not required, 'Missing tw-record comment；请重新生成草稿')
        return None
    raw = found[0][1]
    require('--' not in raw and '<!--' not in raw, 'tw-record 注释含不安全字符，请重新生成草稿')
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise Invalid('Invalid tw-record JSON；请重新生成草稿') from exc
    require(isinstance(value, dict), 'Expected a tw-record object')
    return value


def block(body, name, required=True):
    value = read(body, required=False)
    if value is not None and kind(value) == name:
        return value
    require(not required, 'Missing tw-record ' + name + ' comment；请重新生成草稿')
    return None
