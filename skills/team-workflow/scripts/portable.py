"""Portable execution manifests and provider-bound imports. No command execution."""
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import stat
import uuid
import zipfile

from common import (Invalid, artifact, artifact_valid, digest, git, inside, now, obj, read,
                    require, reserved, sha, snapshot, text, tool_identity, write)
import github_read as github


def during(start, value, end):
    def instant(raw):
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        require(value.tzinfo is not None, 'Timestamp needs a timezone')
        return value
    return instant(start) <= instant(value) <= instant(end)


def repository_id(root):
    try:
        remote = git(root, 'remote', 'get-url', 'origin').decode().strip()
    except Invalid as exc:
        raise Invalid('Cross-machine records need a shared github.com origin; configure the project remote first') from exc
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?', remote)
    require(bool(match), 'Portable evidence needs a github.com origin')
    return github.repository(match[1])


def source_state(root, profile):
    repositories, files = {}, {}

    def capture(path, inputs):
        repo = repository_id(path)
        state = snapshot(path, {'inputs': inputs})
        changes = git(path, 'diff', 'HEAD', '--name-only', '-z').split(b'\0')
        changes += git(path, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
        clean = not any(n and not reserved(n.decode()) for n in changes)
        # Explicit ignored input files are not represented by the commit.
        tracked = {n.decode() for n in git(path, 'ls-files', '-z').split(b'\0') if n}
        clean = clean and set(state['files']) <= tracked
        require(repo not in repositories, 'Duplicate repository identity in external inputs')
        repositories[repo] = {'commit': state['head'], 'content': digest(state['files']), 'clean': clean}

    capture(root, profile['inputs'])
    for name, item in profile.get('external_inputs', {}).items():
        from common import external_path
        path = external_path(root, name, item)
        if item['kind'] == 'repository':
            capture(path, [])
        else:
            require(path.is_file(), 'Missing external input: ' + name)
            files[name] = sha(path)
    return {'repositories': repositories, 'files': files}


def capture_result(directory, check, row, before, after, environment, started, finished, producer_before, producer_after):
    """Called by the execution runner with snapshots taken around actual execution."""
    artifacts = {}
    for name in ('stdout.txt', 'stderr.txt'):
        path = directory / name
        artifacts[name] = {'path': name, 'sha256': sha(path)}
    for value in ([check['report']] if check.get('report') else []) + check.get('artifacts', []):
        name = value[len('{output}/'):]
        path = inside(directory, name, exists=False)
        if path.is_file() and not path.is_symlink():
            artifacts[name] = {'path': name, 'sha256': sha(path)}
    record = {'schema_version': 3, 'kind': 'portable-result', 'check': row['id'], 'contract': digest(check),
              'producer': producer_before, 'producer_after': producer_after, 'source_before': before, 'source_after': after,
              'run_context': ({'repository': os.environ.get('GITHUB_REPOSITORY'),
                               'run_id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                               'job': os.environ.get('GITHUB_JOB')} if os.environ.get('GITHUB_ACTIONS') == 'true' else None),
              'started_at': started, 'finished_at': finished, 'environment': environment,
              'state': row['state'], 'exit_code': row['exit_code'], 'artifacts': artifacts}
    write(directory / 'result.json', record)
    return record


def validate_result(root, profile, manifest, directory):
    obj(manifest, {'schema_version', 'kind', 'check', 'contract', 'producer', 'producer_after', 'source_before', 'source_after', 'run_context',
                  'started_at', 'finished_at', 'environment', 'state', 'exit_code', 'artifacts'})
    require(manifest['schema_version'] == 3 and manifest['kind'] == 'portable-result', 'Expected v3 portable result')
    require(manifest['producer'] == manifest['producer_after'] and isinstance(manifest['producer'], dict)
            and manifest['producer'], 'Workflow producer changed during execution or is missing')
    key = manifest['check']
    require(key in profile['checks'], 'Unknown imported check')
    check = profile['checks'][key]
    require(manifest['contract'] == digest(check), 'Imported check definition changed')
    require(manifest['source_before'] == manifest['source_after'], 'Sources changed during external execution')
    require(manifest['source_after'] == source_state(root, profile), 'Imported source version/content is stale')
    require(all(s['clean'] for s in manifest['source_before']['repositories'].values()), 'Portable result contains unshared working changes')
    try:
        started = datetime.fromisoformat(manifest['started_at'])
        finished = datetime.fromisoformat(manifest['finished_at'])
        require(started.tzinfo is not None and finished.tzinfo is not None and started <= finished,
                'Invalid external execution times')
    except (TypeError, ValueError) as exc:
        raise Invalid('Invalid external execution times') from exc
    require(isinstance(manifest['environment'], dict), 'Missing execution environment')
    for name in profile['environment_versions']:
        value = manifest['environment'].get(name)
        require(isinstance(value, dict) and value.get('state') == 'finished' and value.get('exit_code') == 0
                and value.get('stdout', '').strip(), 'Missing or failed environment capture: ' + name)
    paths = {}
    for name, item in manifest['artifacts'].items():
        obj(item, {'path', 'sha256'})
        path = inside(directory, item['path'])
        require(path.is_file() and not path.is_symlink() and sha(path) == item['sha256'], 'Imported artifact changed: ' + name)
        paths[name] = path
    expected = ['stdout.txt', 'stderr.txt'] + [v[len('{output}/'):] for v in check.get('artifacts', [])]
    if check.get('report'):
        expected.append(check['report'][len('{output}/'):])
    require(set(expected) <= paths.keys(), 'External result lacks original outputs')
    from execution import decode
    status, cases, detail = decode(check, {'state': manifest['state'], 'exit_code': manifest['exit_code'],
                                  'stdout': paths['stdout.txt'].read_text()},
                                  paths[check['report'][len('{output}/'):]] if check.get('report') else None)
    require(status == 'passed', 'External check incomplete: ' + detail)
    if 'review' in check:
        from verification import scenario_review
        captured = {p.relative_to(root).as_posix(): sha(p) for p in paths.values()}
        scenario_review(root, directory, check, captured)
    return {'id': key, 'status': status, 'cases': cases, 'detail': detail}


def provider(locator):
    obj(locator, {'kind', 'repository', 'run_id', 'attempt', 'job_id', 'artifact_id'})
    require(locator['kind'] == 'github-actions', 'Only GitHub Actions has a verified external provider; other files are reference material')
    repo = github.repository(locator['repository'])
    for key in ('run_id', 'attempt', 'job_id', 'artifact_id'):
        require(type(locator[key]) is int and locator[key] > 0, 'Expected positive provider ID: ' + key)
    run = github.api(f'repos/{repo}/actions/runs/{locator["run_id"]}')
    require(run.get('run_attempt') == locator['attempt'], 'A newer run attempt exists')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'Actions run has not succeeded')
    job = github.api(f'repos/{repo}/actions/jobs/{locator["job_id"]}')
    require(job.get('run_id') == locator['run_id'] and job.get('run_attempt') == locator['attempt'], 'Job belongs to another attempt')
    require(job.get('status') == 'completed' and job.get('conclusion') == 'success', 'Actions job has not succeeded')
    artifact_info = github.api(f'repos/{repo}/actions/artifacts/{locator["artifact_id"]}')
    require(not artifact_info.get('expired', True), 'Actions artifact expired')
    origin = artifact_info.get('workflow_run', {})
    require(origin.get('id') == locator['run_id'] and origin.get('head_sha') == run.get('head_sha'), 'Artifact belongs to another run/source')
    require(bool(re.fullmatch(r'sha256:[a-f0-9]{64}', artifact_info.get('digest', ''))), 'Provider did not supply an artifact digest')
    # A rerun may leave old artifacts on the same run: match actual job times too.
    require(during(job['started_at'], artifact_info['created_at'], job['completed_at']), 'Artifact is not from the selected job attempt')
    return {'run': run, 'job': job, 'artifact': artifact_info}


def provider_binding(locator, receipt, manifest):
    context = manifest.get('run_context')
    require(isinstance(context, dict), 'No provider context captured during execution')
    require(context.get('repository') == locator['repository'] and context.get('run_id') == str(locator['run_id'])
            and context.get('attempt') == str(locator['attempt']), 'Execution belongs to another provider attempt')
    key, name = context.get('job', ''), receipt['job'].get('name', '')
    require(bool(key) and (name == key or name.startswith(key + ' (')), 'Captured job differs from selected Actions job; keep the workflow job ID as its display name')
    require(during(receipt['job']['started_at'], manifest['started_at'], receipt['job']['completed_at'])
            and during(receipt['job']['started_at'], manifest['finished_at'], receipt['job']['completed_at']),
            'Execution was not captured during the selected job')


def unpack(data, directory):
    require(len(data) <= 64 * 1024 * 1024, 'Artifact archive exceeds 64 MiB')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            require(len(entries) <= 2000 and sum(i.file_size for i in entries) <= 128 * 1024 * 1024, 'Artifact expands beyond limits')
            seen = set()
            for entry in entries:
                path = inside(directory, entry.filename.rstrip('/'), exists=False)
                require(entry.filename not in seen and not stat.S_ISLNK(entry.external_attr >> 16), 'Duplicate or symlink archive entry')
                seen.add(entry.filename)
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(entry))
    except zipfile.BadZipFile as exc:
        raise Invalid('Invalid artifact ZIP') from exc


def import_result(root, profile, locator, directory=None):
    receipt = provider(locator)
    repo = locator['repository']
    data = github.api(f'repos/{repo}/actions/artifacts/{locator["artifact_id"]}/zip', binary=True)
    import hashlib
    require('sha256:' + hashlib.sha256(data).hexdigest() == receipt['artifact']['digest'], 'Downloaded archive differs from provider digest')
    if directory is None:
        from artifacts import directory as request_directory
        directory = request_directory(root, locator['repository'] + '/actions/' + str(locator['run_id'])) / 'import'
    directory.mkdir(parents=True)
    (directory / 'archive.zip').write_bytes(data)
    unpack(data, directory / 'content')
    manifest_path = inside(directory, 'content/result.json')
    manifest = read(manifest_path)
    require(manifest['source_before']['repositories'].get(repo, {}).get('commit') == receipt['run']['head_sha'],
            'Actions head does not match actual checkout; import a run of the delivered commit')
    provider_binding(locator, receipt, manifest)
    result = validate_result(root, profile, manifest, manifest_path.parent)
    record = {'schema_version': 3, 'kind': 'imported-result', 'locator': locator, 'retrieved_at': now(),
              'archive': artifact(root, directory / 'archive.zip'), 'manifest': artifact(root, manifest_path),
              'provider_digest': receipt['artifact']['digest'], 'result': result,
              'assurance': 'provider-linked original outputs; not a signature or exhaustive business proof'}
    path = directory / 'import.json'
    write(path, record)
    return path, record


def validate_import(root, profile, record):
    require(record.get('schema_version') == 3 and record.get('kind') == 'imported-result', 'Expected imported result')
    receipt = provider(record['locator'])
    archive = artifact_valid(root, record['archive'])
    require('sha256:' + sha(archive) == record['provider_digest'] == receipt['artifact']['digest'], 'Provider evidence changed')
    manifest_path = artifact_valid(root, record['manifest'])
    manifest = read(manifest_path)
    # Bind extracted outputs to the provider ZIP as well as their local hashes.
    with zipfile.ZipFile(archive) as original:
        require(original.read('result.json') == manifest_path.read_bytes(), 'Manifest differs from provider archive')
        for item in manifest['artifacts'].values():
            require(original.read(item['path']) == inside(manifest_path.parent, item['path']).read_bytes(), 'Output differs from provider archive')
    repo = record['locator']['repository']
    require(manifest['source_before']['repositories'].get(repo, {}).get('commit') == receipt['run']['head_sha'], 'Provider source mismatch')
    provider_binding(record['locator'], receipt, manifest)
    result = validate_result(root, profile, manifest, manifest_path.parent)
    require(result == record['result'], 'Imported summary differs from original outputs')
    return result, manifest
