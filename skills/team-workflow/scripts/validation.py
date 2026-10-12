"""Version 4 execution: reusable content-bound results, separate task acceptance."""
import os
from pathlib import Path
import platform
import sys
import uuid

from common import (Invalid, artifact, artifact_valid, create, digest, external_path, git,
                    inside, now, read, require, sha, snapshot, task_valid)
from execution import decode, execute, output_path, redact


def check_root(root, profile, check):
    repository = check.get('repository')
    if not repository:
        return root
    entries = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == repository]
    require(len(entries) == 1, 'Check repository must be a declared external input: ' + repository)
    return external_path(root, repository, entries[0])


def source(root, profile, revision_sensitive=False):
    """Content excludes workflow policy; each check binds its own policy separately."""
    state = snapshot(root, profile)
    def content(value, primary=False):
        if 'files' not in value:
            return value
        result = {'files': {k: v for k, v in value['files'].items()
                            if (k != '.team-workflow.json' or (primary and k in profile['inputs'])) and not v.get('deleted')}}
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


def source_digest(root, profile):
    return digest(source(root, profile))


def changed_paths(root, task):
    names = set()
    for args in [('diff', '--name-only', '--no-renames', '-z', task['base']),
                 ('ls-files', '--others', '--exclude-standard', '-z')]:
        names.update(os.fsdecode(n) for n in git(root, *args).split(b'\0') if n)
    return sorted(n for n in names if n.split('/')[0] not in ('.team-workflow', '.codestable')
                  and n != '.team-workflow.json')


def producer():
    directory = Path(__file__).parent
    return {name: sha(directory / name) for name in ('execution.py', 'validation.py')}


def environment(root, profile, check):
    spec = check.get('environment')
    require(isinstance(spec, dict) and spec.get('kind') in ('stateless', 'fixture'),
            'Declare a stateless or fixture environment before v4 execution/reuse')
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


def check_binding(root, profile, check, remote=False):
    expected = check.get('environment', {}).get('target') if remote else None
    return {'source': digest(source(root, profile, check.get('revision_sensitive', False))),
            'definition': digest(check), 'environment': expected if expected is not None else environment(root, profile, check),
            'producer': producer()}


def capture(root, profile, key, directory, portable=False):
    check = profile['checks'][key]
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
    row = {'id': key, 'binding': before, 'source_unchanged': before == after,
            'argv': argv, 'cwd': check['cwd'], 'repository': check.get('repository'),
            'status': status, 'cases': cases, 'detail': detail, 'state': result['state'],
            'exit_code': result['exit_code'], 'seconds': result['seconds'], 'artifacts': artifacts}
    if portable:
        import portable_v4
        portable_v4.capture(directory, profile, row, portable_before, source_state(root, profile), started, now())
        row['portable'] = artifact(root, directory / 'result.json')
    return row


def run_batch(root, profile, tasks, selected=None, directory=None, portable=False):
    require(bool(tasks), 'Batch requires at least one task')
    require(len({t['id'] for t in tasks}) == len(tasks), 'Duplicate batch task')
    required = {t['id']: task_valid(t, profile, root) for t in tasks}
    require(all(t['schema_version'] == 4 for t in tasks), 'Batch execution requires explicitly adopted v4 tasks')
    checks = sorted(set(selected) if selected is not None else {c for ids in required.values() for c in ids})
    require(set(checks) <= profile['checks'].keys(), 'Unknown selected check')
    identifier = uuid.uuid4().hex
    directory = directory or root / '.team-workflow/batches' / identifier
    directory.mkdir(parents=True, exist_ok=False)
    before = source_digest(root, profile)
    started = now()
    rows = [capture(root, profile, key, directory / key, portable) for key in checks]
    record = {'schema_version': 4, 'kind': 'execution', 'id': identifier, 'project': profile['project'],
              'tasks': required, 'task_digests': {t['id']: digest(t) for t in tasks},
              'started_at': started, 'finished_at': now(),
              'provenance': {'head': git(root, 'rev-parse', 'HEAD').decode().strip()},
              'source_unchanged': before == source_digest(root, profile) and all(r['source_unchanged'] for r in rows),
              'results': rows}
    path = directory / 'run.json'
    create(path, record)
    return path, record


def verify_runs(root, profile, task, paths):
    required = set(task_valid(task, profile, root))
    results, records = {}, []
    for name in paths:
        record = read(inside(root, name))
        if record.get('schema_version') == 4 and record.get('kind') == 'imported-execution':
            import portable_v4
            row, manifest = portable_v4.validate_import(root, profile, record)
            key = row['id']
            if key in required:
                require(key not in results, 'Duplicate result; select one current result for each check')
                results[key] = row
                records.append(record)
            continue
        require(record.get('schema_version') == 4 and record.get('kind') == 'execution', 'Expected v4 execution record')
        require(record.get('project') == profile['project'], 'Execution project mismatch')
        require(record.get('source_unchanged') is True, 'Execution source changed while running')
        for row in record.get('results', []):
            key = row.get('id')
            if key not in required:
                continue
            require(key not in results, 'Duplicate result; select one current result for each check')
            check = profile['checks'][key]
            current = check_binding(root, profile, check)
            for part in ('definition', 'source', 'environment', 'producer'):
                require(row.get('binding', {}).get(part) == current[part], 'Execution ' + part + ' changed: ' + key)
            require(row.get('source_unchanged') is True and row.get('status') == 'passed'
                    and row.get('state') == 'finished' and row.get('exit_code') == 0, 'Check did not pass: ' + key)
            artifacts = row.get('artifacts', [])
            for item in artifacts:
                artifact_valid(root, item)
            stdout = [a for a in artifacts if a['path'].endswith('/stdout.txt')]
            require(len(stdout) == 1, 'Missing original stdout: ' + key)
            out = inside(root, stdout[0]['path']).parent
            require(row.get('argv') == [a.replace('{output}', str(out)) for a in check['argv']]
                    and row.get('cwd') == check['cwd'] and row.get('repository') == check.get('repository'),
                    'Recorded command or repository mismatch')
            expected = ['stdout.txt', 'stderr.txt'] + [v[len('{output}/'):] for v in check.get('artifacts', [])]
            if check.get('report'):
                expected.append(check['report'][len('{output}/'):])
            captured = {a['path']: a['sha256'] for a in artifacts}
            require(all((out / n).relative_to(root).as_posix() in captured for n in expected), 'Missing original artifact')
            native = out / check['report'][len('{output}/'):] if check.get('report') else None
            decoded = decode(check, {'state': row['state'], 'exit_code': row['exit_code'],
                                    'stdout': (out / 'stdout.txt').read_text()}, native)
            require(decoded[0] == 'passed' and decoded[1] == row.get('cases'), 'Original report does not confirm result')
            if check.get('review'):
                from verification import scenario_review
                scenario_review(root, out, check, captured)
            results[key] = row
        records.append(record)
    require(required <= results.keys(), 'Required execution missing: ' + ', '.join(sorted(required - results.keys())))
    return {'checks': sorted(required), 'records': records, 'results': results}
