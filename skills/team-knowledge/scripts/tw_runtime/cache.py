"""Optional cache of commit changes since each verification baseline.

Reading never writes: a missing or stale cache is computed in memory. Only `tw cache --rebuild` writes.
"""
import json
from pathlib import Path
import shutil

from . import KB, gitutil

DIRECTORY = f'{KB}/local/cache'
CHANGES = f'{DIRECTORY}/changes.json'
_loaded = {}


def _read(root):
    key = str(root)
    if key not in _loaded:
        _loaded[key] = None
        path = Path(root) / CHANGES
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get('head') == gitutil.head(root) and isinstance(data.get('bases'), dict):
                _loaded[key] = data['bases']
    return _loaded[key]


def changes(root, base):
    cached = _read(root)
    if cached is not None and base in cached:
        value = cached[base]
        return None if value is None else [(commit, set(paths)) for commit, paths in value]
    return gitutil.changes_since(root, base)


def rebuild(project):
    bases = sorted({info['commit'] for entry in project.entries() for info in [entry.verified('self')]
                    if info and isinstance(info.get('commit'), str)})
    data = {'head': gitutil.head(project.root), 'bases': {}}
    for base in bases:
        commits = gitutil.changes_since(project.root, base)
        data['bases'][base] = None if commits is None else [[commit, sorted(paths)] for commit, paths in commits]
    path = project.root / CHANGES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) + '\n', encoding='utf-8')
    _loaded.pop(str(project.root), None)
    return {'path': CHANGES, 'bases': len(bases), 'head': data['head']}


def clear(project):
    path = project.root / DIRECTORY
    existed = path.exists()
    if existed:
        shutil.rmtree(path)
    _loaded.pop(str(project.root), None)
    return {'path': DIRECTORY, 'removed': existed}
