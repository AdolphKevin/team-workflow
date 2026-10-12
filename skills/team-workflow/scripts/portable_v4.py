"""Content-bound v4 results with original CI provenance and portable paths.

Capture happens at execution time. Imports retain the original tested commits;
matching present-day content never rewrites a historical execution version.
"""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import uuid
import zipfile

from common import (Invalid, artifact, artifact_valid, create, inside, now, obj,
                    profile_valid, read, require, sha, text)
import github_read as github
import portable


def _artifact_names(check):
    values = ['stdout.txt', 'stderr.txt']
    values += [value[len('{output}/'):] for value in check.get('artifacts', [])]
    if check.get('report'):
        values.append(check['report'][len('{output}/'):])
    require(len(values) == len(set(values)), 'Duplicate portable output artifact')
    return values


def capture(directory, profile, row, before_source, after_source, started, finished):
    """Publish the execution-time snapshot next to the actual command outputs."""
    directory = Path(directory)
    key = row['id']
    require(profile.get('schema_version') == 4 and key in profile['checks'], 'Portable v4 capture needs a v4 check')
    check = profile['checks'][key]
    require(row['argv'] == [arg.replace('{output}', str(directory)) for arg in check['argv']],
            'Captured command differs from the executed check')
    standard = [value for value in row['artifacts'] if value['path'].endswith('/stdout.txt')]
    require(len(standard) == 1, 'Capture requires actual stdout artifact')
    prefix = standard[0]['path'][:-len('stdout.txt')]
    captured = {}
    allowed = set(_artifact_names(check))
    for value in row['artifacts']:
        require(value['path'].startswith(prefix), 'Captured output is outside its check directory')
        name = value['path'][len(prefix):]
        require(name in allowed and name not in captured, 'Unexpected or duplicate captured output')
        path = inside(directory, name)
        require(path.is_file() and not path.is_symlink() and sha(path) == value['sha256'],
                'Original output changed before portable capture: ' + name)
        captured[name] = {'path': name, 'sha256': value['sha256']}
    execution = {**row, 'argv': list(check['argv']), 'artifacts': list(captured.values())}
    execution.pop('portable', None)
    manifest = {'schema_version': 4, 'kind': 'portable-execution', 'project': profile['project'],
                'execution': execution, 'source_before': before_source, 'source_after': after_source,
                'started_at': started, 'finished_at': finished,
                'run_context': ({'repository': os.environ.get('GITHUB_REPOSITORY'),
                                 'run_id': os.environ.get('GITHUB_RUN_ID'),
                                 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                                 'job': os.environ.get('GITHUB_JOB')}
                                if os.environ.get('GITHUB_ACTIONS') == 'true' else None)}
    create(directory / 'result.json', manifest)
    return manifest


def _source(value):
    obj(value, {'repositories', 'files'})
    require(isinstance(value['repositories'], dict) and value['repositories'], 'Missing portable source repositories')
    require(isinstance(value['files'], dict), 'Portable external inputs must be a map')
    for repo, row in value['repositories'].items():
        github.repository(repo)
        obj(row, {'commit', 'content', 'clean'})
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(row['commit'])), 'Expected original full commit')
        require(re.fullmatch(r'[a-f0-9]{64}', text(row['content'])), 'Expected source content fingerprint')
        require(row['clean'] is True, 'Portable source contains unshared changes: ' + repo)
    for value in value['files'].values():
        require(re.fullmatch(r'[a-f0-9]{64}', text(value)), 'Expected external file fingerprint')


def _time(start, finish):
    try:
        left = datetime.fromisoformat(text(start).replace('Z', '+00:00'))
        right = datetime.fromisoformat(text(finish).replace('Z', '+00:00'))
        require(left.tzinfo is not None and right.tzinfo is not None and left <= right,
                'Execution timestamps must have timezones and increase')
    except (ValueError, TypeError) as exc:
        raise Invalid('Invalid portable execution timestamps') from exc


def validate_result(root, profile, manifest, directory, *, remote=False):
    """Re-decode originals and return a normalized local view, without changing them."""
    import validation
    from execution import decode
    profile_valid(profile, root)
    obj(manifest, {'schema_version', 'kind', 'project', 'execution', 'source_before', 'source_after',
                   'started_at', 'finished_at', 'run_context'})
    require(manifest['schema_version'] == 4 and manifest['kind'] == 'portable-execution',
            'Expected portable execution schema version 4')
    require(profile.get('schema_version') == 4 and manifest['project'] == profile['project'], 'Portable project mismatch')
    _time(manifest['started_at'], manifest['finished_at'])
    _source(manifest['source_before'])
    _source(manifest['source_after'])
    require(manifest['source_before'] == manifest['source_after'], 'Sources changed during portable execution')
    row = manifest['execution']
    obj(row, {'id', 'binding', 'source_unchanged', 'argv', 'cwd', 'repository', 'status', 'cases',
              'detail', 'state', 'exit_code', 'seconds', 'artifacts'})
    key = row['id']
    require(key in profile['checks'], 'Unknown imported check')
    check = profile['checks'][key]
    require(row['source_unchanged'] is True, 'Source or environment changed during execution')
    require(row['argv'] == check['argv'] and row['cwd'] == check['cwd']
            and row['repository'] == check.get('repository'), 'Portable command or repository mismatch')
    current_sources = portable.source_state(root, profile)
    _source(current_sources)
    require(set(current_sources['repositories']) == set(manifest['source_after']['repositories'])
            and current_sources['files'] == manifest['source_after']['files'], 'Portable source inputs differ')
    current = validation.check_binding(root, profile, check, remote=remote)
    obj(row['binding'], {'source', 'definition', 'environment', 'producer'})
    for part in current:
        require(row['binding'][part] == current[part], 'Imported execution ' + part + ' changed: ' + key)
    require(row['status'] == 'passed' and row['state'] == 'finished' and row['exit_code'] == 0,
            'Original execution did not pass: ' + key)
    require(isinstance(row['artifacts'], list), 'Missing original artifact list')
    paths, artifacts = {}, []
    for value in row['artifacts']:
        obj(value, {'path', 'sha256'})
        name = value['path']
        require(name not in paths, 'Duplicate portable output')
        path = inside(directory, name)
        require(path.is_file() and not path.is_symlink() and sha(path) == value['sha256'],
                'Original portable output changed: ' + name)
        paths[name] = path
        artifacts.append(artifact(root, path))
    expected = set(_artifact_names(check))
    require(set(paths) == expected, 'Portable execution lacks original outputs or contains unexpected outputs')
    native = paths[check['report'][len('{output}/'):]] if check.get('report') else None
    decoded = decode(check, {'state': row['state'], 'exit_code': row['exit_code'],
                            'stdout': paths['stdout.txt'].read_text(encoding='utf-8')}, native)
    require(decoded[0] == 'passed' and decoded[1] == row['cases'],
            'Original reports do not confirm the claimed cases: ' + decoded[2])
    if check.get('review'):
        from verification import scenario_review
        scenario_review(root, directory, check, {value['path']: value['sha256'] for value in artifacts})
    return {**row, 'artifacts': artifacts,
            'argv': [arg.replace('{output}', str(directory)) for arg in check['argv']]}


def _provider_source(locator, receipt, manifest):
    repo = locator['repository']
    require(manifest['source_before']['repositories'].get(repo, {}).get('commit') == receipt['run']['head_sha'],
            'Provider head differs from the actually tested checkout')
    portable.provider_binding(locator, receipt, manifest)
    for identity, source in manifest['source_before']['repositories'].items():
        github.commit(identity, source['commit'])


def _archive_matches(archive, directory, manifest):
    try:
        require(archive.stat().st_size <= 64 * 1024 * 1024, 'Artifact archive exceeds 64 MiB')
        with zipfile.ZipFile(archive) as original:
            entries = original.infolist()
            require(len(entries) <= 2000 and sum(row.file_size for row in entries) <= 128 * 1024 * 1024,
                    'Artifact expands beyond limits')
            require(len({row.filename for row in entries}) == len(entries), 'Duplicate archive entry')
            require(original.read('result.json') == (directory / 'result.json').read_bytes(),
                    'Manifest differs from original provider archive')
            for value in manifest['execution']['artifacts']:
                require(original.read(value['path']) == inside(directory, value['path']).read_bytes(),
                        'Output differs from original provider archive')
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise Invalid('Missing or invalid original provider archive') from exc


def import_result(root, profile, locator, directory=None):
    receipt = portable.provider(locator)
    data = github.api(f'repos/{locator["repository"]}/actions/artifacts/{locator["artifact_id"]}/zip', binary=True)
    expected_digest = receipt['artifact']['digest']
    require('sha256:' + hashlib.sha256(data).hexdigest() == expected_digest,
            'Downloaded archive differs from provider digest')
    directory = Path(directory) if directory is not None else root / '.team-workflow/imports' / uuid.uuid4().hex
    if not directory.is_absolute():
        directory = root / directory
    try:
        inside(root, directory.relative_to(root).as_posix(), exists=False)
    except ValueError as exc:
        raise Invalid('Import directory must be inside the project') from exc
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'archive.zip').write_bytes(data)
    portable.unpack(data, directory / 'content')
    manifest_path = inside(directory, 'content/result.json')
    manifest = read(manifest_path)
    row = validate_result(root, profile, manifest, manifest_path.parent, remote=True)
    _provider_source(locator, receipt, manifest)
    fresh = portable.provider(locator)
    require(fresh == receipt, 'Provider run or artifact changed during import')
    record = {'schema_version': 4, 'kind': 'imported-execution', 'project': profile['project'],
              'locator': locator, 'retrieved_at': now(), 'started_at': manifest['started_at'],
              'finished_at': manifest['finished_at'], 'source_unchanged': True,
              'archive': artifact(root, directory / 'archive.zip'), 'manifest': artifact(root, manifest_path),
              'provider_digest': expected_digest,
              'result': {**row, 'argv': list(profile['checks'][row['id']]['argv'])},
              'tested_source': manifest['source_before'],
              'import_source': portable.source_state(root, profile),
              'assurance': 'provider-bound original reports; tested commits retained; not signed business proof'}
    path = directory / 'import.json'
    create(path, record)
    return path, record


def validate_import(root, profile, record):
    obj(record, {'schema_version', 'kind', 'project', 'locator', 'retrieved_at', 'started_at', 'finished_at',
                 'source_unchanged', 'archive', 'manifest', 'provider_digest', 'result', 'tested_source',
                 'import_source', 'assurance'})
    require(record['schema_version'] == 4 and record['kind'] == 'imported-execution', 'Expected imported execution version 4')
    require(record['project'] == profile['project'] and record['source_unchanged'] is True, 'Imported execution identity changed')
    receipt = portable.provider(record['locator'])
    archive = artifact_valid(root, record['archive'])
    require('sha256:' + sha(archive) == record['provider_digest'] == receipt['artifact']['digest'],
            'Provider evidence changed')
    path = artifact_valid(root, record['manifest'])
    manifest = read(path)
    _archive_matches(archive, path.parent, manifest)
    result = validate_result(root, profile, manifest, path.parent, remote=True)
    _provider_source(record['locator'], receipt, manifest)
    require(record['started_at'] == manifest['started_at'] and record['finished_at'] == manifest['finished_at']
            and record['tested_source'] == manifest['source_before'], 'Imported provenance differs from original execution')
    stable = {**result, 'argv': list(profile['checks'][result['id']]['argv'])}
    require(stable == record['result'], 'Imported summary differs from original execution')
    return result, manifest


def _joint_results(root, profile, report, required):
    """Obtain execution-time source coverage; a report link alone proves nothing."""
    found = {}
    for name in report['runs']:
        record = read(inside(root, name))
        if record.get('schema_version') == 4 and record.get('kind') == 'imported-execution':
            row, manifest = validate_import(root, profile, record)
            if row['id'] not in required:
                continue
            require(row['id'] not in found, 'Duplicate joint check evidence')
            found[row['id']] = manifest
            continue
        require(record.get('schema_version') == 4 and record.get('kind') == 'execution', 'Joint evidence must use v4 execution')
        for row in record['results']:
            if row['id'] not in required:
                continue
            require(row['id'] not in found, 'Duplicate joint check evidence')
            require(bool(row.get('portable')), 'Joint source versions were not captured during execution')
            path = artifact_valid(root, row['portable'])
            manifest = read(path)
            normalized = validate_result(root, profile, manifest, path.parent)
            require(normalized == {key: value for key, value in row.items() if key != 'portable'},
                    'Joint portable snapshot differs from the actual execution row')
            require(portable.during(record['started_at'], manifest['started_at'], record['finished_at'])
                    and portable.during(record['started_at'], manifest['finished_at'], record['finished_at']),
                    'Joint source capture was not inside the recorded execution')
            found[row['id']] = manifest
    require(set(found) == set(required), 'Joint check execution is missing')
    return found


def aggregate(root, manifest, repositories, cs_skill):
    """Verify every delivery and one source-complete joint run against pinned checkouts."""
    from common import git, profile_valid
    import delivery
    obj(manifest, {'schema_version', 'task_id', 'joint', 'participants', 'dependencies'})
    require(manifest['schema_version'] == 4, 'Expected joint schema version 4; legacy records are not upgraded')
    text(manifest['task_id'])
    github.repository(manifest['joint'])
    require(isinstance(manifest['participants'], list) and len(manifest['participants']) >= 2,
            'Joint delivery needs at least two participating repositories')
    require(isinstance(manifest['dependencies'], list), 'Joint dependencies must be a list')
    require(isinstance(repositories, dict), 'Repository locations must be a map')
    locations = {name: Path(path).expanduser().resolve() for name, path in repositories.items()}
    locations.setdefault(portable.repository_id(root), Path(root).resolve())
    expected, starts, materials = {}, {}, {}
    for row in manifest['participants'] + manifest['dependencies']:
        require(isinstance(row, dict), 'Expected a participant or dependency object')
        repo = github.repository(row['repository'])
        require(repo not in expected, 'Duplicate participant or dependency repository: ' + repo)
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(row['commit'])), 'Expected pinned full commit')
        require(repo in locations, 'Missing local checkout mapping: ' + repo)
        checkout = locations[repo]
        require(portable.repository_id(checkout) == repo
                and git(checkout, 'rev-parse', 'HEAD').decode().strip() == row['commit'],
                'Participant or dependency commit differs: ' + repo)
        github.commit(repo, row['commit'])
        state = portable.source_state(checkout, {'inputs': []})
        _source(state)
        starts[repo] = state
        expected[repo] = row['commit']
    participant_ids = {row['repository'] for row in manifest['participants']}
    require(manifest['joint'] in participant_ids, 'Joint owner must be a participating repository')
    for row in manifest['dependencies']:
        obj(row, {'repository', 'commit'})
    output, joint_records, platform_states = [], {}, {}
    for row in manifest['participants']:
        obj(row, {'repository', 'commit', 'profile', 'task', 'report'})
        repo, checkout = row['repository'], locations[row['repository']]
        paths = {name: inside(checkout, row[name]) for name in ('profile', 'task', 'report')}
        materials[repo] = [artifact(checkout, path) for path in paths.values()]
        profile = profile_valid(read(paths['profile']), checkout)
        require(profile['schema_version'] == 4, 'Joint delivery requires explicitly adopted v4 profiles')
        task, report = read(paths['task']), read(paths['report'])
        require(task.get('schema_version') == 4 and report.get('schema_version') == 4,
                'Joint delivery requires v4 task and report records')
        if task['id'].startswith('https://github.com/'):
            from coordination import load
            platform = load(task['id'])
            require(platform['task'] == task and not platform['gaps'], 'Joint task changed or has unresolved platform records')
            platform_states[task['id']] = platform
            parent = platform['parent'] or task['id']
        else:
            parent = task.get('parent') or task['id']
        require(parent == manifest['task_id'], 'Participant belongs to another parent task')
        declared = portable.source_state(checkout, profile)
        _source(declared)
        require(not declared['files'], 'Joint external inputs need versioned repositories')
        for identity, source in declared['repositories'].items():
            require(expected.get(identity) == source['commit'],
                    'Joint manifest omits or mismatches a declared repository: ' + identity)
        for dependency in profile.get('external_inputs', {}).values():
            if dependency.get('role', 'build') in ('modified', 'joint'):
                require(dependency.get('repository') in participant_ids,
                        'Modified or joint repository has no verified participant delivery')
        result = delivery.verify(checkout, profile, task, report, cs_skill)
        require(result.get('business_accepted') is True and result.get('delivery_complete') is True,
                'A participant has not completed actual delivery verification')
        output.append({'repository': repo, **result})
        if repo == manifest['joint']:
            require('cross-service' in task['risks'], 'Joint owner must declare cross-service risk')
            required = set(profile['risk_checks'].get('cross-service', []))
            require(bool(required), 'Joint owner has no declared cross-service checks')
            joint_records = _joint_results(checkout, profile, report, required)
            for check, capture_ in joint_records.items():
                tested = capture_['source_before']
                require(set(tested['repositories']) == set(expected) and not tested['files'],
                        'Joint execution omits or adds a participating/shared repository')
                # validate_result checked the whole current content binding.
                # Keep original tested commits even when only commit metadata changed.
                for identity, source in tested['repositories'].items():
                    github.commit(identity, source['commit'])
    require(bool(joint_records), 'Joint execution is missing')
    for repo, start in starts.items():
        require(portable.source_state(locations[repo], {'inputs': []}) == start, 'Sources changed during aggregation: ' + repo)
    for repo, refs in materials.items():
        for ref in refs:
            artifact_valid(locations[repo], ref)
    for url, before in platform_states.items():
        from coordination import load
        after = load(url)
        fields = ('requirements', 'history_digest', 'design_history_digest', 'owners')
        require(not after['gaps'] and all(after[key] == before[key] for key in fields),
                'Platform requirements, assignments or progress changed during joint verification')
    return {'schema_version': 4, 'kind': 'joint-delivery', 'ok': True, 'scope': 'joint-team-delivery',
            'status': 'complete', 'task_id': manifest['task_id'], 'versions': expected,
            'tested_versions': [{'check': key, 'repositories': {repo: value['commit']
                for repo, value in captured['source_before']['repositories'].items()}}
                for key, captured in sorted(joint_records.items())],
            'participants': output, 'business_accepted': True, 'delivery_complete': True, 'closable': False,
            'assurance': 'original execution plus individual delivery checks; closing still needs authorization'}
