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


def call(skill, root, command, bootstrap=False):
    label = command[0] if command else 'bootstrap'
    script = skill / 'scripts' / ('bootstrap.py' if bootstrap else 'cs_knowledge.py')
    try:
        result = subprocess.run([sys.executable, str(script), '--root', str(root), *command],
                                capture_output=True, text=True, timeout=90)
        data = json.loads(result.stdout)
        require(isinstance(data, dict), 'CS command returned an invalid object')
        require(result.returncode == 0 and data.get('ok', True), f'CS check incomplete: {label}: {json.dumps(data, ensure_ascii=False)[:1600]}')
        return data
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise Invalid(f'CS command unavailable/incomplete: {label}: {exc}') from exc


def supported(preflight):
    require(preflight.get('skill_version') == '2.1.0', 'This release requires the tested CS 2.1.0 dependency; update the shared skill, never rebuild project knowledge for an update')


def document_state(skill, root):
    data = call(skill, root, ['documents', 'list'])
    state = data.get('state')
    require(isinstance(state, str) and len(state) == 64, 'CS did not return source document versions')
    require(not data.get('findings'), 'Source documents or their references need review: ' + json.dumps(data.get('findings'), ensure_ascii=False))
    return state


def identity(skill):
    return {name: sha(skill / name) for name in ('SKILL.md', 'scripts/bootstrap.py', 'scripts/cs_knowledge.py')}


def wiki_state(root):
    paths = [root / '.codestable/config.json']
    wiki = root / '.codestable/wiki'
    require(wiki.is_dir(), 'CS Wiki is missing')
    paths.extend(p for p in wiki.rglob('*') if p.is_file())
    return digest({p.relative_to(root).as_posix(): sha(inside(root, p.relative_to(root).as_posix())) for p in sorted(paths)})


def brief(root, task, skill, paths, symbols):
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    command = ['brief', '--task', task['goal'], '--format', 'json']
    for value in paths:
        command += ['--path', value]
    for value in symbols:
        command += ['--symbol', value]
    data = call(skill, root, command)
    require('document_state' in data.get('receipt', {}), 'CS brief must include source document versions')
    record = {'schema_version': 2, 'kind': 'knowledge-brief', 'task_id': task['id'],
              'at': now(), 'cs_version': preflight.get('skill_version'), 'cs_identity': identity(skill),
              'task_digest': digest(task), 'paths': paths, 'symbols': symbols,
              'wiki_digest': wiki_state(root), 'document_state': data['receipt']['document_state'], 'brief': data}
    return record


def finish(root, task, skill, task_id, brief_path, disposition, reason):
    require(disposition in ('none', 'reused', 'updated', 'added'), 'Unknown knowledge disposition')
    require(bool(reason.strip()), 'Knowledge disposition needs a concrete reason')
    preflight = call(skill, root, ['--check'], bootstrap=True)
    supported(preflight)
    documents = document_state(skill, root)
    previous = read(brief_path)
    require(previous.get('document_state') == documents, 'Source documents changed since brief; read the unified knowledge entry again')
    require(previous.get('cs_identity') == identity(skill), 'CS changed since brief; read again')
    files = call(skill, root, ['task-files', '--task-id', task_id, '--format', 'json'])
    require(files.get('task_status') == 'completed', 'CS task must be completed')
    require(files.get('canonical_task_id') == task_id, 'Use the canonical CS task ID')
    doctor = call(skill, root, ['doctor', '--check-current-references'])
    related = [artifact(root, inside(root, name)) for name in files['files']]
    task_rows = [row for row in files['records'] if row['id'] == task_id and 'task-note' in row['relations']]
    require(len(task_rows) == 1, 'CS task record not found')
    # CS owns note parsing and semantics. Require a concrete backlink to this logical workflow task.
    note = inside(root, task_rows[0]['path']).read_text(encoding='utf-8')
    require(task['id'] in note, 'CS task note must reference this workflow task ID or issue URL')
    require(document_state(skill, root) == documents, 'Source documents changed while capturing completion')
    return {'schema_version': 2, 'kind': 'knowledge-completion', 'task_id': task['id'],
            'task_digest': digest(task), 'at': now(), 'cs_version': preflight.get('skill_version'),
            'cs_identity': identity(skill), 'brief': artifact(root, brief_path),
            'cs_task_id': task_id, 'cs_task_revision': files['task_revision'],
            'files': related, 'wiki_digest': wiki_state(root), 'document_state': documents, 'doctor': doctor,
            'disposition': disposition, 'reason': reason}
