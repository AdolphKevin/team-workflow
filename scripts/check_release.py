#!/usr/bin/env python3
"""Offline release checks, including byte-for-byte upstream reconstruction."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root=ROOT):
    manifest = json.loads((root / 'plugin.json').read_text())
    version = (root / 'VERSION').read_text().strip()
    assert manifest['name'] == 'team-workflow' and manifest['version'] == version
    assert f"VERSION = '{version}'" in (root / 'skills/team-workflow/scripts/common.py').read_text()
    for required in ('LICENSE', 'licenses/MATT-MIT.txt', 'dependencies.json', 'README.md'):
        assert (root / required).is_file(), required
    dependency = json.loads((root / 'dependencies.json').read_text())['cs']
    assert dependency['version'] == '2.1.0'
    assert re.fullmatch(r'[a-f0-9]{40}', dependency['source_commit']), 'Pin a published CS commit'
    assert all(re.fullmatch(r'[a-f0-9]{64}', value) for value in dependency['files'].values())
    lock = json.loads((root / 'upstream/matt.lock.json').read_text())
    assert len(lock['files']) == 41 and len({Path(row['path']).parts[1] for row in lock['files']}) == 15
    with tempfile.TemporaryDirectory(prefix='upstream-check-') as directory:
        temp = Path(directory)
        for row in lock['files']:
            path = root / row['path']
            assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(), row['path']
            assert sha(path) == row['sha256'], f"local MATT file differs from reviewed patch: {row['path']}"
            dest = temp / row['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        result = subprocess.run(['git', 'apply', '--reverse', str(root / 'upstream/matt.patch')],
                                cwd=temp, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        for row in lock['files']:
            assert sha(temp / row['path']) == row['upstream_sha256'], row['source']
    files = [p for p in root.rglob('*') if p.is_file() and not any(
        name in p.relative_to(root).parts for name in ('.git', '.codestable', '.team-workflow', '__pycache__', 'dist'))]
    for path in files:
        assert not path.is_symlink(), f'symlink in release source: {path.name}'
        if path.suffix == '.py':
            compile(path.read_text(), path.relative_to(root).as_posix(), 'exec')
        if path.suffix not in ('.md', '.py', '.json', '.yaml', '.yml', '.patch', '.txt'):
            continue
        text = path.read_text()
        for pattern in (r'/' + r'Users/[^/\s]+/', r'/private/' + 'var/folders/', r'gh[pousr]_[A-Za-z0-9]{30,}',
                        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'):
            assert not re.search(pattern, text), f'private material in {path.relative_to(root)}'
        if path.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', re.sub(r'```.*?```', '', text, flags=re.DOTALL)):
                if '://' in link or link.startswith(('#', '<')):
                    continue
                target = link.split('#')[0]
                assert (path.parent / target).is_file(), f'broken file link: {path.relative_to(root)} -> {link}'
    assert not (root / 'skills/cs').exists(), 'CS must remain an independent dependency'
    return {'ok': True, 'version': version, 'upstream_files': len(lock['files']), 'source_files_checked': len(files)}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
