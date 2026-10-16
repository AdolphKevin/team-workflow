"""Execution records: reusable content-bound results, separate task acceptance."""
import os
import hashlib
import posixpath
import platform
import sys
import uuid

from common import (Invalid, RECORD_SCHEMA, artifact, artifact_valid, create, digest,
                    explicit_input, external_path, git, inside, local_write_guard, now, read, require, reserved, sha, snapshot, task_valid, text)
from execution import decode, execute, output_path, redact


def check_root(root, profile, check):
    repository = check.get('repository')
    if not repository:
        return root
    entries = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == repository]
    require(len(entries) == 1, 'Check repository must be a declared external input: ' + repository)
    return external_path(root, repository, entries[0])


def revision_files(root, profile, revision):
    """Read committed bytes and attributes without a checkout, platform access or lazy fetch."""
    try:
        commit = git(root, 'rev-parse', '--verify', revision + '^{commit}', local_only=True).decode().strip()
        require(commit.lower() == revision.lower(), 'Expected the commit object itself')
        tree = git(root, 'ls-tree', '-r', '-z', '--full-tree', commit, local_only=True)
    except Invalid as exc:
        raise Invalid('本地没有批准的提交 ' + revision + '；请先补齐本地提交，工具不会访问平台。') from exc
    entries = {}
    for row in tree.split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        require(kind == 'blob', 'Submodules must be verified as separate participating repositories')
        entries[os.fsdecode(name)] = (mode, oid)
    oids = sorted({oid for _, oid in entries.values()})
    raw = git(root, 'cat-file', '--batch', input=''.join(oid + '\n' for oid in oids).encode(), local_only=True)
    blobs, offset = {}, 0
    for oid in oids:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', '本地缺少批准提交的源码对象：' + oid)
        size = int(header[2])
        blobs[oid] = raw[end + 1:end + 1 + size]
        offset = end + 2 + size

    def content(name, seen=()):
        require(name in entries and name not in seen, '无法核对批准提交中的文件链接：' + name)
        mode, oid = entries[name]
        if mode != '120000':
            return blobs[oid]
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), os.fsdecode(blobs[oid])))
        require(not target.startswith(('../', '/')), '无法核对批准提交中越出仓库的链接：' + name)
        return content(target, (*seen, name))

    files = {}
    for name, (mode, oid) in sorted(entries.items()):
        if reserved(name, profile['inputs']):
            continue
        value = {'sha256': hashlib.sha256(content(name)).hexdigest()}
        value.update({'link': os.fsdecode(blobs[oid])} if mode == '120000' else {'executable': mode == '100755'})
        files[name] = value
    return files


def source(root, profile, revision_sensitive=False, *, revision=None):
    """Content excludes workflow policy; each check binds its own policy separately."""
    state = snapshot(root, profile)
    if revision is not None:
        state['files'] = revision_files(root, profile, revision)
        state['head'] = revision
    def content(value, primary=False):
        if 'files' not in value:
            return value
        result = {'files': {k: v for k, v in value['files'].items()
                            if (k != '.tw/config.json' or (primary and explicit_input(k, profile['inputs']))) and not v.get('deleted')}}
        if revision_sensitive:
            result['head'] = value['head']
        if value.get('external_inputs'):
            result['external_inputs'] = {k: content(v) for k, v in value['external_inputs'].items()}
        return result
    try:
        remote = git(root, 'remote', 'get-url', 'origin').decode().strip()
    except Invalid:
        repository = 'local:' + profile['project']
    else:
        from portable import repository_id
        try:
            repository = repository_id(root).lower()
        except Invalid:
            from urllib.parse import urlsplit
            parts = urlsplit(remote)
            public = (parts.hostname or '') + parts.path if parts.scheme else remote.rsplit('@', 1)[-1]
            repository = 'origin:' + digest(public)
    result = content(state, True)
    result['repositories'] = {'self': repository, **{name: item['repository'].lower()
        for name, item in profile.get('external_inputs', {}).items() if item['kind'] == 'repository'}}
    return result


def source_digest(root, profile, *, revision=None):
    return digest(source(root, profile, revision=revision))


def effective_base(root, base):
    """Where the task last met the remote default branch, like a pull request's diff; else the recorded base.

    Merging the default branch into a task must not make its changes look like the task's own.
    """
    import subprocess
    run = lambda *args: subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    target = run('symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD')
    if target.returncode or not target.stdout.strip():
        return base
    meeting = run('merge-base', 'HEAD', target.stdout.strip())
    if meeting.returncode or not meeting.stdout.strip():
        return base
    point = meeting.stdout.strip()
    contains = run('merge-base', '--is-ancestor', base, point)
    return point if contains.returncode == 0 else base


def changed_paths(root, task, profile=None, design=None):
    """The task's own design file is process material committed with it, not a change needing a task scope."""
    names = set()
    for args in [('diff', '--name-only', '--no-renames', '-z', effective_base(root, task['base'])),
                 ('ls-files', '--others', '--exclude-standard', '-z')]:
        names.update(os.fsdecode(n) for n in git(root, *args).split(b'\0') if n)
    inputs = (profile or {}).get('inputs', [])
    if design is not None:
        from design_files import declares
        names = {n for n in names if not (n.endswith('.md') and declares(os.path.join(root, n), design))}
    return sorted(n for n in names if not reserved(n, inputs) and
                  (n != '.tw/config.json' or explicit_input(n, inputs)))


EVALUATION_FIELDS = ('required_cases', 'purpose', 'timeout')


def execution_definition(check):
    """What was executed. Which cases are required is evaluated later from the original report."""
    return digest({k: v for k, v in check.items() if k not in EVALUATION_FIELDS})


def producer():
    from execution import DECODER_VERSION
    return {'schema': RECORD_SCHEMA, 'decoder': DECODER_VERSION}


def environment(root, profile, check):
    spec = check.get('environment')
    require(isinstance(spec, dict) and spec.get('kind') in ('stateless', 'fixture'),
            'Declare a stateless or fixture environment before current-format execution/reuse')
    require(not check['required_env'] or spec['kind'] == 'fixture',
            'Checks using required environment values need a public fixture/configuration identity')
    result = {'runtime': {'python': sys.version, 'platform': platform.system(), 'machine': platform.machine()},
              'kind': spec['kind'], 'versions': {}}
    commands = [(name, argv, False) for name, argv in sorted(profile['environment_versions'].items())]
    if spec['kind'] == 'fixture':
        commands.append(('fixture', spec['identity'], True))
    cwd = check_root(root, profile, check)
    for name, argv, fixture in commands:
        require(all(redact(a) == a for a in argv), 'Environment identity must not contain credentials')
        value = execute(argv, cwd, 15)
        require(value['state'] == 'finished' and value['exit_code'] == 0 and value['stdout'].strip(),
                'Cannot confirm environment identity: ' + name)
        require('REDACTED' not in value['stdout'], 'Environment identity must be public metadata, not a redacted credential: ' + name)
        observed = {'command': argv, 'identity': value['stdout'].strip()}
        if fixture:
            result['fixture'] = observed
        else:
            result['versions'][name] = observed
    if spec.get('target') is not None:
        require(result == spec['target'], 'Current environment differs from the explicitly required target')
    return result


def check_binding(root, profile, check, remote=False, live=True):
    """Inputs a result depends on. Offline (live=False) omits the environment, which acceptance recorded."""
    binding = {'source': digest(source(root, profile, check.get('revision_sensitive', False))),
               'definition': execution_definition(check), 'producer': producer()}
    if live:
        expected = check.get('environment', {}).get('target') if remote else None
        binding['environment'] = expected if expected is not None else environment(root, profile, check)
    return binding


def capture(root, profile, key, directory, portable=False):
    check = profile['checks'][key]
    from contracts import coverage
    coverage(check.get('coverage', {}))
    require(check['coverage']['isolation'] != 'unresolved', 'Environment isolation unresolved: ' + key)
    local_write_guard(directory)
    directory.mkdir(parents=True, exist_ok=False)
    before = check_binding(root, profile, check)
    if portable:
        from portable import source_state
        portable_before = source_state(root, profile)
    started = now()
    argv = [a.replace('{output}', str(directory)) for a in check['argv']]
    require(all(redact(a) == a for a in argv), 'Pass credentials through the environment, not arguments')
    missing = [n for n in check['required_env'] if not os.environ.get(n)]
    result = ({'state': 'unavailable', 'exit_code': None, 'seconds': 0, 'stdout': '',
               'stderr': 'Missing environment names: ' + ', '.join(missing)} if missing else
              execute(argv, inside(check_root(root, profile, check), check['cwd']), check['timeout']))
    artifacts, failures = [], []
    for name in ([check['report']] if check.get('report') else []) + check.get('artifacts', []):
        path = output_path(root, directory, name)
        try:
            require(not path.is_symlink(), 'Artifact cannot be a symlink')
            path.write_text(redact(path.read_text(encoding='utf-8')), encoding='utf-8')
            artifacts.append(artifact(root, path))
        except (Invalid, OSError, UnicodeError) as exc:
            failures.append(str(exc))
    native = output_path(root, directory, check['report']) if check.get('report') else None
    status, cases, detail = decode(check, result, native)
    if missing:
        detail = 'Missing required environment names: ' + ', '.join(missing)
    if failures:
        status, detail = 'incomplete', '; '.join(failures)
    for channel in ('stdout', 'stderr'):
        path = directory / (channel + '.txt')
        path.write_text(result[channel] or '(empty)\n', encoding='utf-8')
        artifacts.append(artifact(root, path))
    after = check_binding(root, profile, check)
    row = {'id': key, 'coverage': check['coverage'], 'binding': before, 'source_unchanged': before == after,
            'argv': list(check['argv']), 'cwd': check['cwd'], 'repository': check.get('repository'),
            'status': status, 'cases': cases, 'detail': detail, 'state': result['state'],
            'exit_code': result['exit_code'], 'seconds': result['seconds'], 'artifacts': artifacts}
    if portable:
        import portable
        portable.capture(directory, profile, row, portable_before, source_state(root, profile), started, now())
        row['portable'] = artifact(root, directory / 'result.json')
    return row


def run_batch(root, profile, tasks, selected=None, directory=None, portable=False):
    from validation_session import session
    with session(root, profile, tasks):
        return _run_batch(root, profile, tasks, selected, directory, portable)


def _run_batch(root, profile, tasks, selected=None, directory=None, portable=False):
    require(bool(tasks), 'Batch requires at least one task')
    require(len({t['id'] for t in tasks}) == len(tasks), 'Duplicate batch task')
    required = {t['id']: task_valid(t, profile, root) for t in tasks}
    require(all(t['data_version'] == 1 for t in tasks), 'Batch execution requires data_version 1 tasks')
    checks = sorted(set(selected) if selected is not None else {c for ids in required.values() for c in ids})
    require(set(checks) <= profile['checks'].keys(), 'Unknown selected check')
    identifier = uuid.uuid4().hex
    directory = directory or root / '.tw/local/batches' / identifier
    local_write_guard(directory)
    directory.mkdir(parents=True, exist_ok=False)
    before = source_digest(root, profile)
    started = now()
    rows = []
    for key in checks:
        try:
            rows.append(capture(root, profile, key, directory / key, portable))
        except (Invalid, OSError, ValueError) as exc:
            rows.append({'id': key, 'status': 'incomplete', 'state': 'unavailable', 'exit_code': None,
                         'source_unchanged': False, 'detail': str(exc), 'cases': {}, 'artifacts': []})
    record = {'data_version': RECORD_SCHEMA, 'kind': 'execution', 'id': identifier, 'project': profile['project'],
              'tasks': required, 'task_digests': {t['id']: digest(t) for t in tasks},
              'started_at': started, 'finished_at': now(),
              'provenance': {'head': git(root, 'rev-parse', 'HEAD').decode().strip()},
              'source_unchanged': before == source_digest(root, profile) and all(r['source_unchanged'] for r in rows),
              'results': rows}
    path = directory / 'run.json'
    create(path, record)
    return path, record


def verify_runs(root, profile, task, paths, live=True):
    """Select one current, passing result for every required check.

    A stale row no longer invalidates its whole batch: other rows stay usable and a focused
    re-run of only the stale check completes the set. The original report is re-evaluated
    with the current required cases, so a registration fix needs no re-run.
    """
    required = set(task_valid(task, profile, root))
    candidates = {key: [] for key in required}
    records, bindings = [], {}

    def current(key):
        if key not in bindings:
            bindings[key] = check_binding(root, profile, profile['checks'][key], live=live)
        return bindings[key]

    for name in paths:
        record = read(inside(root, name))
        require(isinstance(record, dict), 'Invalid execution record: ' + str(name))
        if record.get('data_version') == RECORD_SCHEMA and record.get('kind') == 'imported-execution':
            import portable
            key = (record.get('result') or {}).get('id')
            if key in required:
                try:
                    row, _ = portable.validate_import(root, profile, record, live=live)
                    candidates[key].append((name, record.get('started_at', ''), row, None))
                except (Invalid, OSError, ValueError, KeyError) as exc:
                    candidates[key].append((name, '', None, str(exc)))
                records.append(record)
            continue
        require(record.get('data_version') == RECORD_SCHEMA and record.get('kind') == 'execution',
                f'Expected schema {RECORD_SCHEMA} execution record')
        require(record.get('project') == profile['project'], 'Execution project mismatch')
        for row in record.get('results', []):
            key = row.get('id')
            if key not in required:
                continue
            problem = row_problem(root, profile, key, row, current, record)
            evaluated = None
            if problem is None:
                try:
                    evaluated = reevaluate(root, profile, key, row)
                except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
                    problem = str(exc)
            candidates[key].append((name, record.get('started_at', ''), evaluated, problem))
        records.append(record)
    results, selected_runs, superseded = {}, {}, []
    for key in sorted(required):
        usable = sorted((c for c in candidates[key] if c[3] is None), key=lambda c: c[1])
        reasons = [f'{c[0]}: {c[3]}' for c in candidates[key] if c[3] is not None]
        require(bool(usable), 'Required execution missing or stale: ' + key + (' (' + '; '.join(reasons) + ')' if reasons else ''))
        chosen = usable[-1]
        results[key] = chosen[2]
        selected_runs[key] = inside(root, chosen[0]).relative_to(root).as_posix()
        superseded += [{'check': key, 'path': c[0], 'reason': c[3]} for c in candidates[key] if c[3] is not None]
        superseded += [{'check': key, 'path': c[0], 'reason': 'A newer current result was selected'} for c in usable[:-1]]
    return {'checks': sorted(required), 'records': records, 'results': results,
            'selected_runs': selected_runs, 'superseded': superseded}


def row_problem(root, profile, key, row, current, record):
    """Why this row cannot stand for the current check, or None."""
    check = profile['checks'][key]
    try:
        require(record.get('source_unchanged') is True and row.get('source_unchanged') is True,
                'Execution source changed while running: ' + key)
        require(row.get('coverage') == check.get('coverage'), 'Original execution coverage differs: ' + key)
        binding = current(key)
        for part in binding:
            require(row.get('binding', {}).get(part) == binding[part], 'Execution ' + part + ' changed: ' + key)
        require(row.get('state') == 'finished' and row.get('exit_code') == 0, 'Check did not pass: ' + key)
        original_files(root, check, row)
        return None
    except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        return str(exc)


def original_files(root, check, row):
    artifacts = row.get('artifacts', [])
    for item in artifacts:
        artifact_valid(root, item)
    stdout = [a for a in artifacts if a['path'].endswith('/stdout.txt')]
    require(len(stdout) == 1, 'Missing original stdout: ' + row['id'])
    out = inside(root, stdout[0]['path']).parent
    require(row.get('argv') == check['argv']
            and row.get('cwd') == check['cwd'] and row.get('repository') == check.get('repository'),
            'Recorded command or repository mismatch')
    expected = ['stdout.txt', 'stderr.txt'] + [v[len('{output}/'):] for v in check.get('artifacts', [])]
    if check.get('report'):
        expected.append(check['report'][len('{output}/'):])
    captured = {a['path']: a['sha256'] for a in artifacts}
    require(all((out / n).relative_to(root).as_posix() in captured for n in expected), 'Missing original artifact')
    return out, captured


def reevaluate(root, profile, key, row):
    """Decode the original report under the current required cases; this, not the stored status, decides."""
    check = profile['checks'][key]
    out, captured = original_files(root, check, row)
    native = out / check['report'][len('{output}/'):] if check.get('report') else None
    status, cases, detail = decode(check, {'state': row['state'], 'exit_code': row['exit_code'],
                                           'stdout': (out / 'stdout.txt').read_text()}, native)
    require(status == 'passed', f'Original report does not confirm result: {key}: {detail}')
    require(row.get('status') != 'passed' or cases == row.get('cases'), 'Original report does not confirm result: ' + key)
    if check.get('review'):
        scenario_review(root, out, check, captured)
    if row.get('status') == 'passed':
        return row
    return {**row, 'status': 'passed', 'cases': cases, 'detail': detail,
            'evaluation': {'original_status': row.get('status'), 'original_detail': row.get('detail'),
                           'reason': 'Re-evaluated from the original report with the current required cases'}}


def inspect_record(root, profile, record, seen=None):
    """Check shared original reports without executing environment/project commands.

    Continuation uses this limited check. Final verification still checks current
    source, environment and provider provenance through verify_runs.
    """
    require(isinstance(record, dict) and record.get('data_version') == RECORD_SCHEMA,
            'Expected an original execution or acceptance record')
    seen = set(seen or ())
    identity = digest(record)
    require(identity not in seen, 'Shared verification record cycle')
    seen.add(identity)
    if record.get('kind') == 'acceptance':
        require(record.get('business_accepted') is True and bool(record.get('materials'))
                and isinstance(record.get('report'), dict), 'Acceptance lacks original verification inputs')
        for ref in record['materials']:
            artifact_valid(root, ref)
        # Re-inspect only the results the acceptance actually used; superseded runs were replaced by later ones.
        superseded = {(row.get('path'), row.get('check')) for row in record.get('superseded_execution', [])}
        checked = set()
        for name in record['report']['runs']:
            run = read(inside(root, name))
            if run.get('kind') == 'execution':
                rows = [row for row in run.get('results', []) if (name, row.get('id')) not in superseded]
                if not rows:
                    continue
                run = {**run, 'results': rows}
            elif (name, (run.get('result') or {}).get('id')) in superseded:
                continue
            checked.update(inspect_record(root, profile, run, seen))
        return checked
    require(record.get('kind') in {'execution', 'imported-execution'}, 'Expected original execution')
    rows = record.get('results') if record['kind'] == 'execution' else [record.get('result')]
    require(isinstance(rows, list) and bool(rows) and all(isinstance(r, dict) for r in rows),
            'Missing original execution results')
    require(record.get('source_unchanged') is True, 'Execution inputs changed during the original run')
    checked = set()
    for row in rows:
        key = row['id']
        require(key in profile['checks'], 'Original check is not declared by this project')
        check = profile['checks'][key]
        require(row.get('state') == 'finished' and row.get('exit_code') == 0,
                'Original check did not pass')
        require(row.get('binding', {}).get('definition') == execution_definition(check), 'Shared check definition changed')
        reevaluate(root, profile, key, row)
        checked.add(key)
    return checked


def scenario_review(root, out_path, check, captured):
    """Respect the project's separate, evidence-bound Codex scenario verdict."""
    contract = check['review']
    report_path = inside(out_path, contract['path'][len('{output}/'):])
    review = read(report_path)
    require(isinstance(review, dict), 'Invalid scenario review')
    require(review.get('schema_version') == 1 and review.get('reviewer') == 'codex', 'Unknown scenario review contract')
    require(review.get('status') == 'PASS' and review.get('scenario_run_status') == 'COMPLETED', 'Scenario review not passed')
    text(review.get('summary'))
    require(review.get('findings') == [], 'Scenario review has unresolved findings')
    reviewed = review.get('reviewed_artifacts')
    require(isinstance(reviewed, dict), 'Scenario review needs artifact hashes')
    for name in contract['required_artifacts']:
        path = inside(out_path, name)
        current = sha(path)
        require(captured.get(path.relative_to(root).as_posix()) == current, 'Scenario artifact changed after execution')
        require(reviewed.get(name) == 'sha256:' + current, 'Scenario review artifact mismatch')
    # Additional evidence cited by the reviewer must also remain current.
    for name, value in reviewed.items():
        require(value == 'sha256:' + sha(inside(out_path, name)), 'Scenario review has stale additional evidence')
    manifest = read(inside(out_path, 'manifest.json'))
    require(bool(review.get('run_id')) and review['run_id'] == manifest.get('run_id'), 'Scenario run identity mismatch')
