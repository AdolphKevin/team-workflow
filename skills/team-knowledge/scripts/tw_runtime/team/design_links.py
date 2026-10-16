"""Rewrite relative Markdown destinations without touching inline or fenced code."""
import posixpath
import re
from urllib.parse import unquote, urlsplit, urlunsplit


def _protected(source, index):
    if index == 0 or source[index - 1] == '\n':
        fence = re.match(r' {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)', source[index:])
        if fence:
            marker = fence[1]
            close = re.search(r'^ {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}[ \t]*(?:\n|$)',
                              source[index + fence.end():], re.M)
            return index + fence.end() + close.end() if close else len(source)
    if source[index] == '`':
        marker = re.match(r'`+', source[index:])[0]
        close = re.search(r'(?<!`)' + re.escape(marker) + r'(?!`)', source[index + len(marker):])
        if close:
            return index + len(marker) + close.end()
        return index + len(marker)
    return None


def _bracket_end(source, start):
    depth, index = 1, start + 1
    while index < len(source):
        char = source[index]
        if char == '\\':
            index += 2
            continue
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _destination(source, start):
    index = start
    while index < len(source) and source[index].isspace():
        index += 1
    angle = index < len(source) and source[index] == '<'
    begin = index + 1 if angle else index
    index = begin
    depth = 0
    while index < len(source):
        char = source[index]
        if char == '\\':
            index += 2
            continue
        if angle and char == '>':
            return begin, index, index + 1
        if not angle:
            if char == '(':
                depth += 1
            elif char == ')':
                if depth == 0:
                    break
                depth -= 1
            elif char.isspace() and depth == 0:
                break
        index += 1
    return (begin, index, index) if not angle and index > begin else None


def _resolve(target, reference, file_url):
    parts = urlsplit(target)
    if parts.scheme or target.startswith(('#', '/')):
        return None, None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(reference['path']), unquote(parts.path)))
    display = path + ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
    inside = not posixpath.isabs(path) and path != '..' and not path.startswith('../')
    if inside and file_url:
        url = file_url(path + ('#' + parts.fragment if parts.fragment else ''))
        if parts.query:
            value = urlsplit(url)
            url = urlunsplit((value.scheme, value.netloc, value.path, parts.query, value.fragment))
        return url, display
    return '', display


def _key(label):
    return ' '.join(label.split()).casefold()


def _definitions(source, reference, file_url):
    definitions, labels, index = {}, {}, 0
    while index < len(source):
        protected = _protected(source, index)
        if protected is not None:
            index = protected
            continue
        match = re.match(r' {0,3}\[([^\]\n]+)\]:[ \t]*', source[index:]) if index == 0 or source[index - 1] == '\n' else None
        if match:
            destination = _destination(source, index + match.end())
            if destination:
                begin, finish, _ = destination
                stop = source.find('\n', finish)
                stop = stop + 1 if stop >= 0 else len(source)
                target = source[begin:finish]
                resolved = _resolve(target, reference, file_url)
                definitions[index] = (begin, finish, stop, *resolved)
                labels.setdefault(_key(match[1]), (*resolved, target))
                index = stop
                continue
        index += 1
    return definitions, labels


def _plain(label, target, path):
    return '`' + path + '`' if label in (target, path) else label + '（`' + path + '`）'


def rewrite(source, reference, file_url=None):
    definitions, labels = _definitions(source, reference, file_url)
    output, index = [], 0
    while index < len(source):
        protected = _protected(source, index)
        if protected is not None:
            output.append(source[index:protected])
            index = protected
            continue
        if index in definitions:
            begin, finish, stop, url, _ = definitions[index]
            if url is None:
                output.append(source[index:stop])
            elif url:
                output.append(source[index:begin] + url + source[finish:stop])
            index = stop
            continue
        if source[index] == '\\':
            output.append(source[index:index + 2])
            index += 2
            continue
        start = index + 1 if source.startswith('![', index) else index
        if source[start:start + 1] == '[':
            end = _bracket_end(source, start)
            if end is not None and source[end + 1:end + 2] == '(':
                destination = _destination(source, end + 2)
                if destination:
                    begin, finish, after = destination
                    tail = re.match(r'\s*(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\([^)]*\))?\s*\)', source[after:])
                    if tail:
                        stop = after + tail.end()
                        target = re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', source[begin:finish])
                        url, path = _resolve(target, reference, file_url)
                        if url is None:
                            output.append(source[index:stop])
                        elif url:
                            output.append(source[index:begin] + url + source[finish:stop])
                        else:
                            label = source[start + 1:end]
                            output.append(_plain(label, target, path))
                        index = stop
                        continue
            if end is not None:
                label, stop = source[start + 1:end], end + 1
                reference_label = label
                if source[stop:stop + 1] == '[':
                    reference_end = _bracket_end(source, stop)
                    if reference_end is not None:
                        reference_label = source[stop + 1:reference_end] or label
                        stop = reference_end + 1
                resolved = labels.get(_key(reference_label))
                if resolved is not None:
                    url, path, target = resolved
                    output.append(source[index:stop] if url is None or url else _plain(label, target, path))
                    index = stop
                    continue
        output.append(source[index])
        index += 1
    return ''.join(output)
