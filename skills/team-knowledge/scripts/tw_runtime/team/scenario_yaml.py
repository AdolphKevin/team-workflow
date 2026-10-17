"""带原文位置的 YAML 子集与 JSON 读取器；仅依赖标准库。"""
from dataclasses import dataclass
import json
import re
from pathlib import Path

from common import Invalid


def fail(line, message):
    raise Invalid(f'第 {line} 行：{message}', line=line)


@dataclass
class Document:
    value: object
    locations: dict

    def line(self, path=()):
        path = tuple(path)
        while path not in self.locations and path:
            path = path[:-1]
        return self.locations.get(path, 1)


def uncomment(raw, number):
    quote, escaped, index = None, False, 0
    while index < len(raw):
        char = raw[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == quote:
                if index + 1 < len(raw) and raw[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "\"'" and (index == 0 or raw[index - 1] in ' :,[{'):
            quote = char
        elif char == '#' and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip()
        index += 1
    if quote:
        fail(number, '引号字符串在本行闭合')
    return raw.rstrip()


def colon(raw):
    """块映射的冒号在引号外，后接空白或行尾。"""
    quote, escaped, depth, index = None, False, 0, 0
    while index < len(raw):
        char = raw[index]
        if quote:
            if quote == '"' and not escaped and char == '\\':
                escaped = True
                index += 1
                continue
            if char == quote and not escaped:
                if quote == "'" and index + 1 < len(raw) and raw[index + 1] == quote:
                    index += 1
                else:
                    quote = None
            escaped = False
        elif char in "\"'" and (index == 0 or raw[index - 1] in ' :,[{'):
            quote = char
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
        elif char == ':' and depth == 0 and (index + 1 == len(raw) or raw[index + 1].isspace()):
            return index
        index += 1
    return None


class Flow:
    def __init__(self, raw, number, locations, *, json_mode=False):
        self.raw, self.number, self.locations = raw, number, locations
        self.pos, self.json_mode = 0, json_mode

    def line(self):
        return self.number + self.raw[:self.pos].count('\n')

    def space(self):
        while self.pos < len(self.raw) and self.raw[self.pos].isspace():
            self.pos += 1

    def quoted(self):
        start, quote = self.pos, self.raw[self.pos]
        self.pos += 1
        value = ''
        escapes = {'"': '"', '\\': '\\', 'n': '\n'}
        while self.pos < len(self.raw):
            char = self.raw[self.pos]
            self.pos += 1
            if char == quote:
                if quote == "'" and self.pos < len(self.raw) and self.raw[self.pos] == "'":
                    self.pos += 1
                    value += "'"
                    continue
                if self.json_mode:
                    try:
                        return json.loads(self.raw[start:self.pos])
                    except ValueError as exc:
                        fail(self.line(), 'JSON 字符串格式：' + str(exc))
                return value
            if char == '\\' and quote == '"':
                if self.pos >= len(self.raw):
                    break
                char = self.raw[self.pos]
                self.pos += 1
                if self.json_mode:
                    value += '\\' + char
                    continue
                if char not in escapes:
                    fail(self.line(), '双引号转义支持 \\"、\\\\ 与 \\n')
                char = escapes[char]
            value += char
        fail(self.line(), '引号字符串需要闭合')

    def value(self, path=(), key=False):
        self.space()
        self.locations[path] = self.line()
        if self.pos >= len(self.raw):
            fail(self.line(), '填写标量或集合')
        char = self.raw[self.pos]
        if char in "\"'":
            result = self.quoted()
        elif char in '[{':
            mapping, closing = char == '{', '}' if char == '{' else ']'
            result = {} if mapping else []
            self.pos += 1
            self.space()
            while self.pos < len(self.raw) and self.raw[self.pos] != closing:
                if mapping:
                    number = self.line()
                    name = self.value(path, key=True)
                    if not isinstance(name, str):
                        name = str(name)
                    self.space()
                    if self.pos >= len(self.raw) or self.raw[self.pos] != ':':
                        fail(self.line(), '流式映射用冒号分隔键和值')
                    self.pos += 1
                    if name in result:
                        fail(number, '重复键：' + name)
                    result[name] = self.value(path + (name,))
                else:
                    result.append(self.value(path + (len(result),)))
                self.space()
                if self.pos < len(self.raw) and self.raw[self.pos] == closing:
                    break
                if self.pos >= len(self.raw) or self.raw[self.pos] != ',':
                    fail(self.line(), '流式集合用逗号分隔各项')
                self.pos += 1
                self.space()
            if self.pos >= len(self.raw):
                fail(self.line(), '流式集合需要闭合 ' + closing)
            self.pos += 1
        else:
            start = self.pos
            delimiters = ',]}:' if key else ',]}'
            while self.pos < len(self.raw) and self.raw[self.pos] not in delimiters:
                self.pos += 1
            word = self.raw[start:self.pos].strip()
            if not word:
                fail(self.line(), '填写标量')
            if '\n' in word:
                fail(self.line(), '普通标量写在同一行')
            if re.match(r'^[|>](?:[+-]?\d*|\d*[+-]?)$', word):
                fail(self.line(), '块标量请改写为引号字符串或字符串数组')
            if re.match(r'[&*!]', word):
                fail(self.line(), '锚点、别名与标签请展开为普通值')
            result = int(word) if re.fullmatch(r'[-+]?\d+', word) else word
        return result

    def complete(self, path):
        result = self.value(path)
        self.space()
        if self.pos != len(self.raw):
            fail(self.line(), '本行值之后出现多余内容')
        return result


def flow_open(raw):
    quote, escaped, depth, index = None, False, 0, 0
    while index < len(raw):
        char = raw[index]
        if quote:
            if quote == '"' and not escaped and char == '\\':
                escaped = True
                index += 1
                continue
            if char == quote and not escaped:
                if quote == "'" and index + 1 < len(raw) and raw[index + 1] == quote:
                    index += 1
                else:
                    quote = None
            escaped = False
        elif char in "\"'" and (index == 0 or raw[index - 1] in ' :,[{'):
            quote = char
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
        index += 1
    return depth > 0


class Block:
    def __init__(self, raw):
        self.lines, self.locations, self.pos = [], {(): 1}, 0
        for number, original in enumerate(raw.splitlines(), 1):
            prefix = original[:len(original) - len(original.lstrip())]
            if '\t' in prefix:
                fail(number, '缩进使用空格')
            line = uncomment(original, number)
            if line in ('---', '...'):
                fail(number, '文件保存一个文档，移除文档分隔符')
            if line.strip():
                self.lines.append((len(line) - len(line.lstrip(' ')), line.lstrip(' '), number))

    def scalar(self, raw, number, path):
        # 块普通标量里的逗号和括号属于文字。
        if raw and raw[0] not in "[{'\"":
            if colon(raw) is not None:
                fail(number, '含冒号分隔的文字请加引号')
            if re.match(r'^[|>](?:[+-]?\d*|\d*[+-]?)$', raw) or re.match(r'[&*!]', raw):
                return Flow(raw, number, self.locations).complete(path)
            self.locations[path] = number
            return int(raw) if re.fullmatch(r'[-+]?\d+', raw) else raw
        previous = number
        while raw.startswith(('[', '{')) and flow_open(raw) and self.pos < len(self.lines):
            _, more, line = self.lines[self.pos]
            self.pos += 1
            raw += '\n' * (line - previous) + more
            previous = line
        return Flow(raw, number, self.locations).complete(path)

    def nested(self, raw, indent, number, path, *, indentless=False):
        self.locations[path] = number
        if raw:
            return self.scalar(raw, number, path)
        if self.pos < len(self.lines):
            depth, next_raw, _ = self.lines[self.pos]
            if depth > indent or indentless and depth == indent and (next_raw == '-' or next_raw.startswith('- ')):
                return self.block(depth, path)
        # 空值按 YAML 的空标量读取；字段检查负责说明业务要求。
        return None

    def mapping_item(self, result, raw, indent, number, path):
        split = colon(raw)
        if split is None:
            fail(number, '块映射使用 key: value；普通标量写在同一行')
        name = self.scalar(raw[:split].strip(), number, path)
        if not isinstance(name, (str, int)):
            fail(number, '映射键使用字符串')
        name = str(name)
        if name in result:
            fail(number, '重复键：' + name)
        result[name] = self.nested(raw[split + 1:].strip(), indent, number, path + (name,), indentless=True)

    def block(self, indent, path):
        first = self.lines[self.pos]
        sequence = first[1] == '-' or first[1].startswith('- ')
        result = [] if sequence else {}
        self.locations[path] = first[2]
        while self.pos < len(self.lines):
            depth, raw, number = self.lines[self.pos]
            if depth < indent:
                break
            if depth > indent:
                fail(number, '普通标量写在同一行；子项按所属集合缩进')
            if sequence and raw != '-' and not raw.startswith('- '):
                break
            self.pos += 1
            if sequence:
                item_path, tail = path + (len(result),), raw[1:].strip()
                self.locations[item_path] = number
                if colon(tail) is not None:
                    item = {}
                    item_indent = indent + len(raw) - len(raw[1:].lstrip())
                    self.mapping_item(item, tail, item_indent, number, item_path)
                    while self.pos < len(self.lines) and self.lines[self.pos][0] > indent:
                        depth, entry, line = self.lines[self.pos]
                        if depth != item_indent:
                            fail(line, '序列中的映射字段保持相同缩进')
                        self.pos += 1
                        self.mapping_item(item, entry, depth, line, item_path)
                else:
                    item = self.nested(tail, indent, number, item_path)
                result.append(item)
            else:
                self.mapping_item(result, raw, indent, number, path)
        return result


def json_locations(raw):
    """JSON 值由标准库解码，递归扫描只保存键和数组项的位置。"""
    decoder, positions = json.JSONDecoder(), {(): 1}
    def scan(pos, path):
        while raw[pos].isspace():
            pos += 1
        positions[path] = raw[:pos].count('\n') + 1
        if raw[pos] in '[{':
            mapping, closing = raw[pos] == '{', '}' if raw[pos] == '{' else ']'
            pos, index, seen = pos + 1, 0, set()
            while True:
                while raw[pos].isspace():
                    pos += 1
                if raw[pos] == closing:
                    return pos + 1
                if mapping:
                    name, end = decoder.raw_decode(raw, pos)
                    number = raw[:pos].count('\n') + 1
                    if name in seen:
                        fail(number, '重复键：' + name)
                    seen.add(name)
                    pos = end
                    while raw[pos].isspace():
                        pos += 1
                    pos += 1
                    pos = scan(pos, path + (name,))
                    positions[path + (name,)] = number
                else:
                    pos = scan(pos, path + (index,))
                    index += 1
                while raw[pos].isspace():
                    pos += 1
                if raw[pos] == ',':
                    pos += 1
        return decoder.raw_decode(raw, pos)[1]
    scan(0, ())
    return positions


def loads(raw, suffix='.yaml'):
    if suffix.lower() == '.json':
        try:
            value = json.loads(raw)
        except ValueError as exc:
            fail(getattr(exc, 'lineno', 1), 'JSON 格式：' + str(exc))
        return Document(value, json_locations(raw))
    parser = Block(raw)
    if not parser.lines:
        return Document(None, {(): 1})
    first = parser.lines[0]
    if first[1].startswith(('[', '{')):
        raw_flow, previous = first[1], first[2]
        for _, more, number in parser.lines[1:]:
            raw_flow += '\n' * (number - previous) + more
            previous = number
        return Document(Flow(raw_flow, first[2], parser.locations).complete(()), parser.locations)
    value = parser.block(first[0], ())
    if parser.pos != len(parser.lines):
        fail(parser.lines[parser.pos][2], '顶层字段保持相同缩进')
    return Document(value, parser.locations)


def read(path):
    path = Path(path)
    try:
        return loads(path.read_text(encoding='utf-8'), path.suffix)
    except (OSError, UnicodeError) as exc:
        fail(1, '读取文件失败：' + str(exc))
