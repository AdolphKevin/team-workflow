"""Front matter as `---`, one `key: JSON value` per line, `---`. Parsed without a YAML library."""
import json
import re

KEY = re.compile(r'^([a-z][a-z0-9_]*):[ \t]?(.*)$')
ORDER = ('title', 'scope', 'source', 'verified', 'status', 'guards', 'symbols', 'tags', 'related', 'owner')


def parse(text):
    """Return (fields, body, errors). Never raises: problems are reported for `check`."""
    lines = text.replace('\r\n', '\n').split('\n')
    if lines[0] != '---':
        return {}, '\n'.join(lines), ['缺少文件头：第一行必须是 ---']
    fields, errors = {}, []
    for number, line in enumerate(lines[1:], start=2):
        if line == '---':
            return fields, '\n'.join(lines[number:]), errors
        if not line.strip():
            continue
        match = KEY.match(line)
        if not match:
            errors.append(f'文件头第 {number} 行应为 `字段: JSON值`')
            continue
        key, raw = match.groups()
        if key in fields:
            errors.append(f'重复字段：{key}')
            continue
        try:
            fields[key] = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f'字段 {key} 不是合法 JSON：{exc.msg}')
    return fields, '', errors + ['文件头缺少结束行 ---']


def dump(fields, body):
    keys = [k for k in ORDER if k in fields] + sorted(k for k in fields if k not in ORDER)
    head = ''.join(f'{key}: {json.dumps(fields[key], ensure_ascii=False)}\n' for key in keys)
    return f'---\n{head}---\n{body}'
