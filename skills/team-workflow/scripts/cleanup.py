"""Explicit cleanup of unreferenced requests belonging to completed v4 tasks."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import time

from common import Invalid, create, digest, inside, now, read, require, sha


@contextmanager
def guard(root):
    lock = inside(root, '.team-workflow/.maintenance-lock', exists=False)
    deadline = time.monotonic() + 5
    while True:
        try:
            create(lock, {'pid': os.getpid(), 'at': now()})
            break
        except FileExistsError as exc:
            try:
                owner = read(lock)
                os.kill(owner['pid'], 0)
            except ProcessLookupError:
                raise Invalid('Workflow maintenance was interrupted; inspect .team-workflow/.maintenance-lock') from exc
            except (Invalid, OSError, KeyError, TypeError):
                pass  # A competing create may not have finished writing its claim yet.
            if time.monotonic() >= deadline:
                raise Invalid('Workflow maintenance is active or interrupted; inspect .team-workflow/.maintenance-lock before retrying') from exc
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.unlink()


def running(claim, directory):
    if (directory / 'response.json').is_file():
        return False
    try:
        os.kill(claim['pid'], 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, KeyError, TypeError):
        return True


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if key != 'covered_requests':
                yield from strings_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings_in(child)


def preview(root):
    root = root.resolve()
    runtime = root / '.team-workflow'
    contents, documents, issues = {}, {}, []
    for path in sorted(runtime.rglob('*')) if runtime.exists() else []:
        if path.name == '.maintenance-lock':
            continue
        if path.is_symlink():
            issues.append('Symlink prevents safe cleanup: ' + str(path.relative_to(root)))
        elif path.is_file():
            relative = path.relative_to(root).as_posix()
            contents[relative] = sha(path)
            if path.suffix == '.json':
                try:
                    documents[relative] = read(path)
                except Invalid:
                    issues.append('Unreadable references in ' + relative)
    claims = {p: d for p, d in documents.items() if p.endswith('/request.json') and '/requests/' in p}
    finished_tasks = set()
    for record in documents.values():
        if not (isinstance(record, dict) and record.get('schema_version') == 5
                and record.get('kind') == 'delivery-verification' and record.get('ok') is True
                and record.get('delivery_complete') is True and isinstance(record.get('covered_requests'), list)):
            continue
        covered = {item.get('path'): item.get('sha256') for item in record['covered_requests'] if isinstance(item, dict)}
        task_claims = [name for name, claim in claims.items() if isinstance(claim, dict) and claim.get('task_id') == record.get('task_id')]
        if task_claims and all(covered.get(name) == contents[name] for name in task_claims):
            finished_tasks.add(record['task_id'])
    candidates, protected, active = [], [], []
    for name, claim in claims.items():
        directory = (root / name).parent
        relative = directory.relative_to(root).as_posix()
        if not isinstance(claim, dict):
            issues.append('Invalid request claim: ' + name)
            continue
        if running(claim, directory):
            active.append(relative)
        referenced = any(path != name and not path.startswith(relative + '/')
                         and any(v == relative or v.startswith(relative + '/') for v in strings_in(doc))
                         for path, doc in documents.items())
        owned_docs = [d for p, d in documents.items() if p.startswith(relative + '/') and isinstance(d, dict)]
        preserve_kind = any(d.get('kind') in ('prepared-context', 'design-record', 'approval-record',
                                              'handoff', 'progress', 'delivery-verification') for d in owned_docs)
        preserve_review = any(p.startswith(relative + '/') and p.endswith('/review-input.json') for p in documents)
        if claim.get('task_id') not in finished_tasks or referenced or preserve_kind or preserve_review or relative in active:
            protected.append(relative)
        else:
            candidates.append(relative)
    return {'schema_version': 1, 'kind': 'cleanup-plan', 'ok': not issues, 'read_only': True,
            'root': str(root), 'state': digest(contents), 'candidates': sorted(candidates),
            'protected': sorted(protected), 'active': active, 'gaps': issues,
            'summary': f'{len(candidates)} 个已完成任务的无引用请求可清理；其他材料保留。',
            'next_action': 'Save this plan outside the project, review it, then use cleanup --apply --plan PATH.'}


def apply(root, plan):
    require(isinstance(plan, dict) and plan.get('kind') == 'cleanup-plan' and plan.get('root') == str(root.resolve()),
            'Cleanup plan belongs to another project')
    with guard(root):
        current = preview(root)
        require(current['ok'] and not current['active'], 'Cleanup needs readable references and no active requests')
        require(plan.get('state') == current['state'] and plan.get('candidates') == current['candidates'],
                'Cleanup plan changed; preview and review again')
        for name in current['candidates']:
            path = inside(root, name)
            require('/requests/' in name and path.is_relative_to(root / '.team-workflow/tasks'), 'Unsafe cleanup candidate')
            shutil.rmtree(path)
    return {'ok': True, 'kind': 'cleanup-result', 'removed': current['candidates'],
            'summary': f'已清理 {len(current["candidates"])} 个无引用请求。'}
