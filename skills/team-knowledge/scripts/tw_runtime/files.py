"""Atomic writes and tool-owned marked blocks in user files."""
import os
from pathlib import Path
import tempfile

from . import require


def markers(kind):
    return f'<!-- team-workflow:guidance:{kind} start -->', f'<!-- team-workflow:guidance:{kind} end -->'


def block(kind, body):
    start, end = markers(kind)
    return f'{start}\n{body.strip(chr(10))}\n{end}\n'


def strip_block(text, kind):
    start, end = markers(kind)
    first, last = text.find(start), text.find(end)
    return text if first == -1 or last < first else text[:first] + text[last + len(end):]


def merge(existing, kind, new_block):
    """Return (text, action). Only the marked block belongs to the tool; everything else is kept byte for byte."""
    start, end = markers(kind)
    if existing is None:
        return new_block, 'create'
    first, last = existing.find(start), existing.find(end)
    require(first == -1 and last == -1 or (first != -1 and last > first), f'{kind} 指引块的标记已损坏，请手工修复')
    newline = '\r\n' if '\r\n' in existing else '\n'
    new_block = new_block.replace('\n', newline) if newline != '\n' else new_block
    if first == -1:
        separator = '' if not existing or existing.endswith(newline * 2) else newline if existing.endswith(newline) else newline * 2
        return existing + separator + new_block, 'append'
    tail = last + len(end)
    if existing.startswith(newline, tail):
        tail += len(newline)
    if existing[first:tail] == new_block:
        return existing, 'unchanged'
    return existing[:first] + new_block + existing[tail:], 'update'


def read_text(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return stream.read()


def write_text(path, text):
    """Write through symlinks, keep the file mode, never leave a partial file."""
    path = Path(path)
    target = path.resolve() if path.exists() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix='.writing-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
