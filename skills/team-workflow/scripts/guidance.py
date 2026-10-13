"""Maintain marked guidance blocks in project and per-user agent instruction files."""
import os
from pathlib import Path
import tempfile

from common import Invalid, require

SKILL = Path(__file__).resolve().parents[1]
REFERENCE = SKILL / 'references/business-acceptance.md'
SCOPES = ('project', 'global', 'all')
PROJECT_FILE, CLAUDE_FILE = 'AGENTS.md', 'CLAUDE.md'
GLOBAL_FILES = (('claude-code', '.claude', 'CLAUDE.md'), ('codex', '.codex', 'AGENTS.md'))


def markers(kind):
    return f'<!-- team-workflow:guidance:{kind} start -->', f'<!-- team-workflow:guidance:{kind} end -->'


def render(kind, agents=PROJECT_FILE):
    body = (SKILL / 'templates' / f'guidance-{kind}.md').read_text(encoding='utf-8').strip('\n')
    body = body.replace('__REFERENCE__', str(REFERENCE)).replace('__AGENTS__', agents)
    start, end = markers(kind)
    return f'{start}\n{body}\n{end}\n'


def merge(existing, kind, block):
    """Return (new_text, action). The marked block is the only part this tool owns."""
    start, end = markers(kind)
    if existing is None:
        return block, 'create'
    first, last = existing.find(start), existing.find(end)
    require(first == -1 and last == -1 or (first != -1 and last > first), f'Damaged guidance markers for {kind}')
    if first == -1:
        nl = '\r\n' if '\r\n' in existing else '\n'
        separator = '' if not existing or existing.endswith(nl * 2) else nl if existing.endswith(nl) else nl * 2
        return existing + separator + block, 'append'
    tail = last + len(end)
    for newline in ('\r\n', '\n'):
        if existing.startswith(newline, tail):
            tail += len(newline)
            break
    current = existing[first:tail]
    if current == block:
        return existing, 'unchanged'
    return existing[:first] + block + existing[tail:], 'update'


def strip_block(existing, kind):
    start, end = markers(kind)
    first, last = existing.find(start), existing.find(end)
    return existing if first == -1 or last < first else existing[:first] + existing[last + len(end):]


def project_target(root, name):
    name = name or PROJECT_FILE
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts, f'Expected project-relative file: {name}')
    return root / path


def global_targets(home):
    for client, directory, name in GLOBAL_FILES:
        base = home / directory
        yield client, base / name, base.is_dir()


def read_text(path):
    """Keep the file's own line endings so untouched content stays byte-identical."""
    with path.open(encoding='utf-8', newline='') as stream:
        return stream.read()


def write_text(path, text):
    """Write through symlinks, keep the existing mode, and never leave a partial file."""
    target = path.resolve() if path.exists() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o666 & ~current_umask()
    descriptor, temporary = tempfile.mkstemp(prefix='.writing-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def current_umask():
    value = os.umask(0)
    os.umask(value)
    return value


def plan_target(kind, path, available=True, client=None, agents=PROJECT_FILE):
    row = {'kind': kind, 'path': str(path), 'exists': path.is_file()}
    if client:
        row['client'] = client
    if not available:
        return {**row, 'action': 'skipped', 'reason': f'{client} is not installed on this machine'}
    existing = read_text(path) if path.is_file() else None
    if kind == 'claude' and existing is not None and any(f'@{prefix}{agents}' in strip_block(existing, kind) for prefix in ('', './')):
        return {**row, 'action': 'unchanged', 'reason': f'already imports {agents}'}
    block = render(kind, agents)
    if existing and '\r\n' in existing:
        block = block.replace('\n', '\r\n')
    try:
        text, action = merge(existing, kind, block)
    except Invalid as exc:
        return {**row, 'action': 'blocked', 'reason': str(exc)}
    return {**row, 'action': action, 'text': text}


def run(root, scope='all', apply=False, home=None, file=None):
    require(scope in SCOPES, f'Expected --scope in {SCOPES}')
    require(REFERENCE.is_file(), 'Installed skill is missing references/business-acceptance.md')
    home = Path(home).expanduser().resolve() if home else Path.home()
    targets = []
    if scope in ('project', 'all'):
        agents_path = project_target(root, file)
        agents = agents_path.relative_to(root).as_posix()
        targets.append(plan_target('project', agents_path))
        if agents != CLAUDE_FILE:
            targets.append(plan_target('claude', root / CLAUDE_FILE, agents=agents))
    if scope in ('global', 'all'):
        for client, path, available in global_targets(home):
            targets.append(plan_target('global', path, available, client))
    blocked = [t for t in targets if t['action'] == 'blocked']
    changes = [t for t in targets if t['action'] in ('create', 'append', 'update')]
    if apply:
        require(not blocked, 'Repair the damaged guidance markers before applying: ' + '; '.join(f"{t['path']}: {t['reason']}" for t in blocked))
        for target in changes:
            write_text(Path(target['path']), target['text'])
            target['applied'] = True
    for target in targets:
        if target['action'] not in ('create', 'append', 'update') or apply:
            target.pop('text', None)
        elif target['action'] != 'create':
            target['block'] = render(target['kind'], agents if target['kind'] == 'claude' else PROJECT_FILE)
            target.pop('text')
    if blocked:
        summary, next_action = '指引标记损坏', 'Repair or remove the damaged markers by hand, then rerun guidance.'
    elif not changes:
        summary, next_action = '指引已是最新', 'Nothing to write; rerun after upgrading the skill.'
    elif apply:
        summary, next_action = '指引已写入', 'Commit the project file with the task; per-user files stay out of the repository.'
    else:
        summary, next_action = '指引预览', 'Review each target, then run guidance --apply to write only the marked blocks.'
    return {'ok': not blocked, 'read_only': not apply, 'scope': scope, 'summary': summary,
            'reference': str(REFERENCE), 'targets': targets,
            'actions': {'create': 'file will be created with the block', 'append': 'block added after existing content',
                        'update': 'block between markers replaced', 'unchanged': 'block already current',
                        'skipped': 'client not installed', 'blocked': 'markers damaged; nothing written'},
            'gaps': [f"{t['path']}: {t['reason']}" for t in blocked], 'next_action': next_action}
