"""Read-only helpers around the git command line."""
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from . import Invalid


def run(root, *args, check=True, stdin=None):
    result = subprocess.run(['git', '-C', str(root), '-c', 'core.quotepath=off', *args], input=stdin,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode != 0:
        raise Invalid(f"git {args[0]} 失败：{result.stderr.strip() or result.returncode}")
    return result


def output(root, *args):
    return run(root, *args).stdout


def toplevel(path):
    result = run(path, 'rev-parse', '--show-toplevel', check=False)
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 and result.stdout.strip() else None


def head(root):
    return run(root, 'rev-parse', '--verify', '-q', 'HEAD^{commit}', check=False).stdout.strip() or None


def files(root):
    """Existing tracked files plus untracked files that are not ignored."""
    out = output(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    return sorted({name for name in out.split('\0') if name and os.path.lexists(Path(root) / name)})


def index_files(root):
    return sorted(name for name in output(root, 'ls-files', '-z').split('\0') if name)


def show_index(root, name):
    return output(root, 'show', f':{name}')


def tracked_under(root, prefix):
    return [name for name in output(root, 'ls-files', '-z', '--', prefix).split('\0') if name]


def ignored(root, name):
    """Whether ignore rules match `name`, regardless of whether it is tracked."""
    result = run(root, 'check-ignore', '-q', '--no-index', '--', name, check=False)
    if result.returncode not in (0, 1):
        raise Invalid(f'git check-ignore 失败：{result.stderr.strip()}')
    return result.returncode == 0


def remote_identity(root):
    url = run(root, 'config', '--get', 'remote.origin.url', check=False).stdout.strip()
    return normalize_remote(url) if url else None


def normalize_remote(url):
    """Normalize SSH and HTTP(S) remotes to host/path, without credentials or a port."""
    url = url.strip()
    if '://' in url:
        parts = urlsplit(url)
        host, path = (parts.hostname or ''), parts.path
    else:
        match = re.match(r'^(?:[^@/]+@)?([^:/]+):(.+)$', url)
        if not match:
            return 'local:' + url.strip('/')
        host, path = match.groups()
    path = path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    return f'{host.lower()}/{path}' if host else 'local:' + path


def dirty_paths(root):
    """Paths with uncommitted changes, including both sides of a rename."""
    entries = output(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all').split('\0')
    paths, index = set(), 0
    while index < len(entries):
        item = entries[index]
        if item:
            paths.add(item[3:])
            if item[0] in 'RC' or item[1] in 'RC':
                index += 1
                if index < len(entries) and entries[index]:
                    paths.add(entries[index])
        index += 1
    return paths


def changes_since(root, base):
    """[(commit, paths)] for non-merge commits in base..HEAD, or None when the range cannot be computed."""
    if not base or run(root, 'cat-file', '-e', f'{base}^{{commit}}', check=False).returncode != 0:
        return None
    if run(root, 'merge-base', '--is-ancestor', base, 'HEAD', check=False).returncode != 0:
        return None
    commits = []
    for line in output(root, 'log', '--no-merges', '-M', '--name-status', '--format=%x01%H', f'{base}..HEAD').splitlines():
        if line.startswith('\x01'):
            commits.append((line[1:], set()))
        elif line.strip() and commits:
            commits[-1][1].update(line.split('\t')[1:])
    return commits


def changed_since_ref(root, base):
    """Paths changed between `base` and the working tree, plus untracked files."""
    require_commit = run(root, 'rev-parse', '--verify', '-q', f'{base}^{{commit}}', check=False)
    if require_commit.returncode != 0:
        raise Invalid(f'找不到提交：{base}')
    changed = {n for n in output(root, 'diff', '--name-only', '-z', base).split('\0') if n}
    untracked = {n for n in output(root, 'ls-files', '-z', '--others', '--exclude-standard').split('\0') if n}
    return changed | untracked


def recent_commits(root, paths, limit=5):
    if not paths:
        return []
    out = output(root, 'log', f'-n{limit}', '--format=%h%x09%s', '--', *paths)
    return [tuple(line.split('\t', 1)) for line in out.splitlines() if '\t' in line]


def shallow(root):
    return output(root, 'rev-parse', '--is-shallow-repository').strip() == 'true'
