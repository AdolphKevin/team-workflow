"""Literal repository paths shared by task scopes and knowledge queries."""
from pathlib import Path, PureWindowsPath
import os

from . import Invalid


class RelativePath(str):
    """Keep an explicit directory hint when removing a query's trailing slash."""
    def __new__(cls, value, directory=False):
        result = super().__new__(cls, value)
        result.directory = directory
        return result


def normalize(value, *, root=None, scope=False):
    """Normalize a literal path; only queries supplying root accept in-repo absolutes.

    Directory intent survives repeated calls, including a not-yet-created `src/`.
    Committed scopes/task paths use scope=True and remain relative and literal.
    Queries retain their existing literal wildcard characters without expansion.
    """
    raw = os.fspath(value)
    if not isinstance(raw, str) or '\\' in raw or '\0' in raw or '..' in raw.split('/'):
        raise Invalid(f'路径必须是仓库内的相对路径，不能包含 ..、反斜杠或 NUL：{raw!r}')
    if scope and any(char in raw for char in '*?[]'):
        raise Invalid(f'路径必须是具体路径，不能包含通配符：{raw}')
    directory = getattr(value, 'directory', False) or raw.endswith('/')
    if raw.startswith('/'):
        if root is None or scope:
            raise Invalid(f'路径必须是仓库内的相对路径：{raw}')
        try:
            raw = Path(raw).resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError as exc:
            raise Invalid(f'路径不在仓库内：{raw}') from exc
    elif PureWindowsPath(raw).is_absolute():
        raise Invalid(f'路径必须是仓库内的相对路径：{raw}')
    result = '/'.join(part for part in raw.split('/') if part not in ('', '.')) or '.'
    directory = directory or result == '.' or (root is not None and (Path(root) / result).is_dir())
    return RelativePath(result, directory)


def covers(scope, path):
    """A literal task scope covers itself and descendants; `.` covers the repository."""
    scope, path = normalize(scope), normalize(path)
    return scope == '.' or path == scope or path.startswith(scope + '/')
