"""Visible cooperative validation leases; these do not intercept editor writes."""
from contextlib import contextmanager, ExitStack
import os
import uuid

from common import Invalid, create, external_path, inside, now, read, require

MARKER = '.tw/local/validation-active'


def active(root):
    directory = inside(root, MARKER, exists=False)
    running = []
    for path in sorted(directory.glob('*.json')) if directory.exists() else []:
        require(not path.is_symlink(), 'Validation marker cannot be a symlink')
        value = read(path)
        try:
            os.kill(value['pid'], 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        running.append(value)
    return {'running': running} if running else None


@contextmanager
def _lease(root, tasks):
    path = inside(root, MARKER + '/' + uuid.uuid4().hex + '.json', exists=False)
    value = {'pid': os.getpid(), 'started_at': now(), 'tasks': tasks,
             'instruction': 'Keep source, generated inputs and checkout unchanged until this run ends.'}
    try:
        create(path, value)
    except FileExistsError as exc:
        raise Invalid('Validation active or interrupted; inspect ' + str(path) + ' before retrying') from exc
    try:
        yield
        require(read(path) == value, 'Validation lease changed during execution')
    finally:
        if path.is_file() and read(path) == value:
            path.unlink()


@contextmanager
def session(root, profile, tasks):
    roots = {root.resolve()}
    for value in profile.get('external_inputs', {}).values():
        if value['kind'] == 'repository':
            roots.add(external_path(root, value['repository'], value).resolve())
    with ExitStack() as stack:
        for directory in sorted(roots, key=str):
            stack.enter_context(_lease(directory, [t['id'] for t in tasks]))
        yield
