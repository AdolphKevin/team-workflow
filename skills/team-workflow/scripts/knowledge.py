"""Read-only bridge to the independently installed CS CLI. Never learns or rebuilds."""
import os
from pathlib import Path
import subprocess
import sys
import json

from common import Invalid, artifact, digest, inside, now, read, require, sha, write


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


def supported(preflight):
    required = {'documents', 'receipt-check', 'task-files'}
    missing = required - set(preflight.get('capabilities', []))
    require(not missing, 'CS interface missing: ' + ', '.join(sorted(missing)))


def receipt_check(skill, root, brief):
    result = call(skill, root, ['receipt-check', '--file', '-'], input_data=brief['receipt'])
    require(result.get('kind') == 'receipt-check' and result.get('read_only') is True
            and isinstance(result.get('query_state'), dict) and not result.get('changed'),
            'CS receipt-check did not confirm relevant sources')
    return result['query_state']


def brief(root, task, skill, paths, symbols):
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    command = ['brief', '--task', task['goal'], '--format', 'json']
    for value in paths:
        command += ['--path', value]
    for value in symbols:
        command += ['--symbol', value]
    data = call(skill, root, command)
    require(isinstance(data.get('receipt', {}).get('query_state'), dict), 'CS brief must include scoped source state')
    record = {'schema_version': 2, 'kind': 'knowledge-brief', 'task_id': task['id'],
              'at': now(), 'cs_version': preflight.get('skill_version'),
              'task_digest': digest(task), 'paths': paths, 'symbols': symbols,
              'query_state': data['receipt']['query_state'], 'brief': data}
    return record


def finish(root, task, skill, task_id, brief_path, disposition, reason):
    require(disposition in ('none', 'reused', 'updated', 'added'), 'Unknown knowledge disposition')
    require(bool(reason.strip()), 'Knowledge disposition needs a concrete reason')
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    previous = read(brief_path)
    sources = receipt_check(skill, root, previous['brief'])
    files = call(skill, root, ['task-files', '--task-id', task_id, '--format', 'json'])
    require(files.get('task_status') == 'completed', 'CS task must be completed')
    require(files.get('canonical_task_id') == task_id, 'Use the canonical CS task ID')
    related = [artifact(root, inside(root, name)) for name in files['files']]
    task_rows = [row for row in files['records'] if row['id'] == task_id and 'task-note' in row['relations']]
    require(len(task_rows) == 1, 'CS task record not found')
    # CS owns note parsing and semantics. Require a concrete backlink to this logical workflow task.
    note = inside(root, task_rows[0]['path']).read_text(encoding='utf-8')
    require(task['id'] in note, 'CS task note must reference this workflow task ID or issue URL')
    require(receipt_check(skill, root, previous['brief']) == sources, 'Relevant sources changed while capturing completion')
    return {'schema_version': 2, 'kind': 'knowledge-completion', 'task_id': task['id'],
            'task_digest': digest(task), 'at': now(), 'cs_version': preflight.get('skill_version'),
            'brief': artifact(root, brief_path),
            'cs_task_id': task_id, 'cs_task_revision': files['task_revision'],
            'files': related, 'query_state': sources,
            'disposition': disposition, 'reason': reason}
