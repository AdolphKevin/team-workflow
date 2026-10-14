"""Read-only bridge to the independently installed CS CLI. Never learns or rebuilds."""
import os
from pathlib import Path
import subprocess
import sys
import json

from common import RECORD_SCHEMA, Invalid, artifact, artifact_valid, digest, inside, now, read, require, tool_gate


def skill_path(value=None):
    path = Path(value or os.environ.get('TEAM_WORKFLOW_CS_SKILL', '')).expanduser().resolve()
    require((path / 'SKILL.md').is_file() and (path / 'scripts/cs_knowledge.py').is_file()
            and (path / 'scripts/bootstrap.py').is_file(),
            'CS unavailable: discover its installed skill and pass --cs-skill or TEAM_WORKFLOW_CS_SKILL')
    return path


def call(skill, root, command, bootstrap=False, input_data=None):
    label = command[0] if command else 'bootstrap'
    script = skill / 'scripts' / ('bootstrap.py' if bootstrap else 'cs_knowledge.py')
    try:
        result = subprocess.run([sys.executable, str(script), '--root', str(root), *command],
                                capture_output=True, text=True, timeout=90,
                                input=json.dumps(input_data) if input_data is not None else None)
        data = json.loads(result.stdout)
        require(isinstance(data, dict), 'CS command returned an invalid object')
        require(result.returncode == 0 and data.get('ok', True), f'CS check incomplete: {label}: {json.dumps(data, ensure_ascii=False)[:1600]}')
        return data
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise Invalid(f'CS command unavailable/incomplete: {label}: {exc}') from exc


CONTRACT_VERSION = 1
CAPABILITIES = {'documents', 'receipt-check', 'task-files', 'task-external-refs', 'exclusive-plan-file',
                'review-actions', 'task-source-acceptances', 'install-integrity'}


def supported(preflight):
    require(preflight.get('contract_version') == CONTRACT_VERSION,
            f'CS contract {preflight.get("contract_version")!r} is not supported; install a CS release with contract {CONTRACT_VERSION}')
    missing = CAPABILITIES - set(preflight.get('capabilities', []))
    require(not missing, 'CS interface missing: ' + ', '.join(sorted(missing)))
    integrity = preflight.get('integrity') or {}
    changed = integrity.get('changed', []) + integrity.get('missing', []) + integrity.get('unexpected', [])
    if integrity.get('status') != 'intact':
        from common import ToolModified
        raise ToolModified(f'Installed CS differs from its release ({integrity.get("status", "unknown")}: '
                           f'{", ".join(changed[:5])}); reinstall CS instead of patching the installed copy')


def receipt_check(skill, root, brief):
    result = call(skill, root, ['receipt-check', '--file', '-'], input_data=brief['receipt'])
    require(result.get('kind') == 'receipt-check' and result.get('read_only') is True
            and isinstance(result.get('query_state'), dict) and not result.get('changed'),
            'CS receipt-check did not confirm relevant sources')
    return result['query_state']


def brief(root, task, skill, paths, symbols):
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    paths = paths or task.get('paths', [])
    symbols = symbols or task.get('symbols', [])
    command = ['brief', '--task', task['goal'], '--format', 'json']
    for value in paths:
        command += ['--path', value]
    for value in symbols:
        command += ['--symbol', value]
    for value in task.get('scopes', []):
        scope = value['repository'] + ':' + value['path']
        if value.get('symbol'):
            scope += '#' + value['symbol']
        command += ['--scope', scope]
    data = call(skill, root, command)
    require(isinstance(data.get('receipt', {}).get('query_state'), dict), 'CS brief must include scoped source state')
    record = {'schema_version': RECORD_SCHEMA, 'kind': 'knowledge-brief', 'task_id': task['id'],
              'at': now(), 'cs_version': preflight.get('skill_version'),
              'task_digest': digest(task), 'paths': paths, 'symbols': symbols,
              'query_state': data['receipt']['query_state'], 'brief': data}
    return record


def external_ref(task):
    from github_read import issue_ref
    if task['id'].startswith('https://github.com/'):
        repository, number = issue_ref(task['id'])
        return {'system': 'github', 'id': f'https://github.com/{repository.lower()}/issues/{number}'}
    return {'system': 'team-workflow', 'id': task['id']}


def finish(root, profile, task, skill, task_id, brief_path, disposition, reason,
              acceptance_path, final_brief_path=None):
    """Capture actual CS completion after business acceptance, without writing knowledge."""
    from common import artifact_valid
    from validation import source_digest
    require(disposition in ('none', 'reused', 'updated', 'added') and reason.strip(), 'Describe actual knowledge disposition')
    tool = tool_gate()
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    acceptance = read(acceptance_path)
    require(acceptance.get('schema_version') == RECORD_SCHEMA and acceptance.get('kind') == 'acceptance'
            and acceptance.get('ok') is True and acceptance.get('task_digest') == digest(task)
            and acceptance.get('source_digest') == source_digest(root, profile),
            'Current business acceptance is required before recording CS completion')
    validate_acceptance(root, profile, task, acceptance)
    initial = read(brief_path)
    latest_path = final_brief_path or brief_path
    latest = read(latest_path)
    for value in (initial, latest):
        require(value.get('schema_version') == RECORD_SCHEMA and value.get('kind') == 'knowledge-brief'
                and value.get('task_digest') == digest(task), 'Knowledge brief belongs to another task/version')
    from datetime import datetime
    require(datetime.fromisoformat(initial['at']) <= datetime.fromisoformat(acceptance['at']),
            'Initial knowledge reading was captured after acceptance; report and repeat the affected review')
    sources = receipt_check(skill, root, latest['brief'])
    files = call(skill, root, ['task-files', '--task-id', task_id, '--format', 'json'])
    require(files.get('task_status') == 'completed' and files.get('canonical_task_id') == task_id,
            'CS canonical task must be completed')
    require(external_ref(task) in files.get('external_refs', []), 'CS task needs an exact structured external_refs association')
    existing = call(skill, root, ['template', '--task-id', task_id])['task']
    require(acceptance_entry(root, task, acceptance_path) in existing.get('source', {}).get('workflow_acceptances', []),
            'CS completion must reference the actual current business acceptance')
    expected = task.get('scopes') or [{'repository': 'self', 'path': p} for p in task.get('paths', [])]
    actual = files.get('scopes') or [{'repository': 'self', 'path': p} for p in files.get('paths', [])]
    require(bool(expected) and any(a.get('repository') == e.get('repository') and
            (a['path'] == e['path'] or a['path'].startswith(e['path'].rstrip('/') + '/') or
             e['path'].startswith(a['path'].rstrip('/') + '/')) for a in actual for e in expected),
            'CS knowledge scope does not match the actual task repository and paths')
    related = [artifact(root, inside(root, name)) for name in files['files']]
    require(bool(related), 'Missing actual CS task files')
    require(receipt_check(skill, root, latest['brief']) == sources, 'Knowledge sources changed during capture')
    return {'schema_version': RECORD_SCHEMA, 'kind': 'knowledge-completion', 'task_id': task['id'],
            'task_digest': digest(task), 'at': now(), 'brief': artifact(root, brief_path),
            'final_brief': artifact(root, latest_path), 'acceptance': artifact(root, acceptance_path),
            'cs_task_id': task_id, 'cs_task_revision': files['task_revision'],
            'external_refs': files['external_refs'], 'files': related, 'query_state': sources,
            'disposition': disposition, 'reason': reason, 'tool': tool,
            'cs': {'version': preflight.get('skill_version'), 'contract_version': preflight.get('contract_version'),
                   'integrity': preflight.get('integrity', {}).get('status')}}


def acceptance_entry(root, task, path):
    entry = {**artifact(root, path), 'task_id': task['id']}
    if task['id'].startswith('https://github.com/'):
        entry['issue'] = external_ref(task)['id']
    return entry


def completion_template(root, profile, task, skill, acceptance_paths=(), task_id=None, siblings=()):
    """Generate only a CS payload; CS still owns all writes and its preview/apply protocol.

    Sibling tasks that share one implementation share one CS task record. Each keeps its own
    business acceptance; the record is completed only when every task sharing it is accepted.
    """
    tasks = [task, *siblings]
    require(len({t['id'] for t in tasks}) == len(tasks), 'Duplicate task sharing one knowledge record')
    command = ['template', '--task-id', task_id] if task_id else ['template', '--title', task['goal'], '--kind', 'task']
    payload = call(skill, root, command)
    value = payload['task']
    value['external_refs'] = list(value.get('external_refs', []))
    scopes = []
    for item in tasks:
        if external_ref(item) not in value['external_refs']:
            value['external_refs'].append(external_ref(item))
        for scope in item.get('scopes') or [{'repository': 'self', 'path': p} for p in item.get('paths', [])]:
            if scope not in scopes:
                scopes.append(scope)
    value['scopes'] = scopes
    require(bool(value['scopes']), 'Knowledge template needs actual repository scopes')
    value['status'] = 'in-progress'
    payload['items'] = []
    source = value.setdefault('source', {})
    source.pop('workflow_acceptance', None)
    accepted = {}
    # Siblings accepted earlier stay accepted while their stored acceptance is still current.
    stored = {row.get('task_id'): row for row in source.get('workflow_acceptances', []) if isinstance(row, dict)}
    for item in tasks:
        row = stored.get(item['id'])
        if row:
            try:
                path = artifact_valid(root, {'path': row['path'], 'sha256': row['sha256']})
                validate_acceptance(root, profile, item, read(path))
                accepted[item['id']] = acceptance_entry(root, item, path)
            except (Invalid, KeyError):
                pass  # stale or missing: this task must supply a current acceptance
    supplied = set()
    for path in acceptance_paths:
        acceptance = read(path)
        owners = [t for t in tasks if t['id'] == acceptance.get('task_id')]
        require(len(owners) == 1, 'Acceptance belongs to a task that is not sharing this knowledge record; add it with --with-task')
        require(owners[0]['id'] not in supplied, 'Two acceptances supplied for one task: ' + owners[0]['id'])
        supplied.add(owners[0]['id'])
        validate_acceptance(root, profile, owners[0], acceptance)
        accepted[owners[0]['id']] = acceptance_entry(root, owners[0], path)
    if accepted:
        source['workflow_acceptances'] = sorted(accepted.values(), key=lambda row: row['path'])
    else:
        source.pop('workflow_acceptances', None)
    if accepted and not pending_acceptance(payload, tasks):
        value['status'] = 'completed'
    return payload


def pending_acceptance(payload, tasks):
    """Tasks sharing the record that still lack a current acceptance in this payload."""
    present = {row['task_id'] for row in payload['task'].get('source', {}).get('workflow_acceptances', [])}
    return [item['id'] for item in tasks if item['id'] not in present]


def validate_acceptance(root, profile, task, value):
    from validation import source_digest
    require(value.get('schema_version') == RECORD_SCHEMA and value.get('kind') == 'acceptance'
            and value.get('ok') is True and value.get('business_accepted') is True
            and value.get('task_digest') == digest(task)
            and value.get('source_digest') == source_digest(root, profile),
            'Current business acceptance is required before CS completion')
    for ref in value.get('materials', []):
        artifact_valid(root, ref)
    require(bool(value.get('materials')), 'Business acceptance must include original materials')
    require(isinstance(value.get('report'), dict), 'Acceptance must retain its original verification inputs')
    import delivery
    # The environment was checked when this acceptance was made; only recheck what can be read offline.
    fresh = delivery.verify(root, profile, task, value['report'], phase='acceptance', live=False)
    require(all(fresh.get(key) == value.get(key) for key in ('task_digest', 'source_digest', 'sections', 'checks', 'acceptance_scope', 'issues', 'observations')),
            'Business acceptance inputs or dispositions changed')
