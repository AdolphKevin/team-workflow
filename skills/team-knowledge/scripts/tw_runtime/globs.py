"""Scope globs: `*` and `?` stay inside one directory, `**` spans directories.

`fnmatch` is not used because its `*` crosses `/`.
"""
from functools import lru_cache
import re

WILDCARDS = frozenset('*?')
ALIAS = re.compile(r'^[A-Za-z0-9._-]+$')


def problem(pattern):
    if not pattern or pattern.startswith('/') or '\\' in pattern:
        return '路径必须是仓库内的相对 POSIX 路径'
    parts = pattern.rstrip('/').split('/')
    if any(part in ('', '.', '..') for part in parts):
        return '路径不能包含空段、. 或 ..'
    if any(ch in pattern for ch in '[]{}'):
        return '不支持 [] 或 {} 语法'
    if any('**' in part and part != '**' for part in parts):
        return '** 必须单独作为一段'
    return None


@lru_cache(maxsize=4096)
def compiled(pattern):
    parts = pattern.rstrip('/').split('/')
    out = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == '**':
            out.append('.*' if last else '(?:[^/]+/)*')
            continue
        segment = ''.join('[^/]*' if ch == '*' else '[^/]' if ch == '?' else re.escape(ch) for ch in part)
        out.append(segment if last else segment + '/')
    return re.compile('^' + ''.join(out) + '$')


def matches(pattern, path):
    """A pattern without wildcards also matches everything below it as a directory."""
    if compiled(pattern).match(path):
        return True
    return not (WILDCARDS & set(pattern)) and path.startswith(pattern.rstrip('/') + '/')


def specificity(pattern):
    return sum(1 for part in pattern.rstrip('/').split('/') if not (WILDCARDS & set(part)))


def split(value):
    """`repo:pattern` -> (repo, pattern, problem)."""
    if not isinstance(value, str) or ':' not in value:
        return None, None, '应写成 `仓库:路径`，本仓用 self'
    repo, pattern = value.split(':', 1)
    if not ALIAS.match(repo):
        return None, None, f'仓库别名不合法：{repo}'
    return repo, pattern, problem(pattern)
