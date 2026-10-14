"""Explicit cleanup of unreferenced local material; nothing outside the managed roots is ever removed."""
from contextlib import contextmanager
import os
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


MANAGED = ('tasks', 'batches', 'imports', 'validation-active', 'agents')
KEEP = ('local.json', '.maintenance-lock', 'agents')


def size(path):
    return path.stat().st_size if path.is_file() else sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def referenced_elsewhere(relative, documents):
    return any(not path.startswith(relative + '/') and any(v == relative or v.startswith(relative + '/') for v in strings_in(doc))
               for path, doc in documents.items())


def preview(root, scope='requests', older_than=14):
    require(scope in ('requests', 'all') and isinstance(older_than, int) and older_than >= 0, 'Invalid cleanup scope')
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
        if not (isinstance(record, dict) and record.get('schema_version') in (5, 6)
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
    reasons = {name: 'request of a delivered task, not referenced' for name in candidates}
    unmanaged = []
    if scope == 'all':
        cutoff = time.time() - older_than * 86400
        for kind in ('batches', 'imports'):
            for directory in sorted((runtime / kind).iterdir()) if (runtime / kind).is_dir() else []:
                relative = directory.relative_to(root).as_posix()
                if not directory.is_dir() or directory.is_symlink():
                    continue
                if referenced_elsewhere(relative, documents):
                    protected.append(relative)
                elif max((p.stat().st_mtime for p in directory.rglob('*')), default=directory.stat().st_mtime) > cutoff:
                    protected.append(relative)
                else:
                    candidates.append(relative)
                    reasons[relative] = f'unreferenced {kind[:-1]} older than {older_than} days'
        for lease in sorted((runtime / 'validation-active').glob('*.json')) if (runtime / 'validation-active').is_dir() else []:
            relative = lease.relative_to(root).as_posix()
            value = documents.get(relative)
            if isinstance(value, dict) and not running(value, lease.parent / '__no_response__'):
                candidates.append(relative)
                reasons[relative] = 'validation lease of a finished process'
        for entry in sorted(runtime.iterdir()) if runtime.is_dir() else []:
            if entry.name not in MANAGED + KEEP:
                unmanaged.append({'path': entry.relative_to(root).as_posix(), 'bytes': size(entry)})
    details = [{'path': name, 'reason': reasons[name], 'bytes': size(root / name)} for name in sorted(candidates)]
    largest = sorted(({'path': name, 'bytes': (root / name).stat().st_size} for name in contents), key=lambda r: -r['bytes'])[:20]
    reclaim = sum(row['bytes'] for row in details)
    return {'schema_version': 2, 'kind': 'cleanup-plan', 'ok': not issues, 'read_only': True,
            'root': str(root), 'scope': scope, 'older_than': older_than,
            'state': digest(contents), 'candidates': sorted(candidates), 'details': details,
            'protected': sorted(protected), 'active': active, 'gaps': issues, 'unmanaged': unmanaged,
            'totals': {'files': len(contents), 'bytes': sum((root / n).stat().st_size for n in contents),
                       'reclaimable_bytes': reclaim, 'largest': largest},
            'summary': f'{len(candidates)} 项无引用材料可清理，约 {reclaim // (1024 * 1024)} MiB；其他材料保留。'
                       + (f'另有 {len(unmanaged)} 项手工输出不归工具管理，只列出大小，不会删除。' if unmanaged else ''),
            'next_action': 'Save this plan outside the project, review it, then use cleanup --apply --plan PATH.'}


def apply(root, plan):
    require(isinstance(plan, dict) and plan.get('kind') == 'cleanup-plan' and plan.get('root') == str(root.resolve()),
            'Cleanup plan belongs to another project')
    with guard(root):
        current = preview(root, plan.get('scope', 'requests'), plan.get('older_than', 14))
        require(current['ok'] and not current['active'], 'Cleanup needs readable references and no active requests')
        require(plan.get('state') == current['state'] and plan.get('candidates') == current['candidates'],
                'Cleanup plan changed; preview and review again')
        runtime = root / '.team-workflow'
        for name in current['candidates']:
            path = inside(root, name)
            request = '/requests/' in name and path.is_relative_to(runtime / 'tasks')
            material = path.parent in (runtime / 'batches', runtime / 'imports')
            lease = path.parent == runtime / 'validation-active' and path.suffix == '.json'
            require(request or material or lease, 'Unsafe cleanup candidate')
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    return {'ok': True, 'kind': 'cleanup-result', 'removed': current['candidates'],
            'summary': f'已清理 {len(current["candidates"])} 项无引用材料（请求、批次、导入或已结束的验证标记）。'}
