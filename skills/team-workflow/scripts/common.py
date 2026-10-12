"""Shared v2 contracts and content binding. Standard library, Python 3.9+."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from contextvars import ContextVar
from datetime import datetime, timezone

VERSION = '0.6.0-rc.1'
RISKS = {'authorization', 'persistence', 'concurrency', 'messaging', 'public-contract', 'cross-service'}
KINDS = {'code', 'docs'}
LOCATIONS = ContextVar('workflow_locations', default={'repositories': {}, 'inputs': {}})


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def obj(value, required, optional=()):
    require(isinstance(value, dict), 'Expected an object')
    require(set(required) <= value.keys(), 'Missing fields: ' + ', '.join(sorted(set(required) - value.keys())))
    require(value.keys() <= set(required) | set(optional), 'Unknown fields: ' + ', '.join(sorted(value.keys() - set(required) - set(optional))))
    return value


def text(value):
    require(isinstance(value, str) and bool(value.strip()), 'Expected non-empty text')
    require('__REPLACE__' not in value, 'Unfilled template')
    return value


def strings(value, nonempty=False):
    require(isinstance(value, list), 'Expected an array')
    for item in value:
        text(item)
    require(not nonempty or bool(value), 'Expected a non-empty array')
    require(len(set(value)) == len(value), 'Duplicate values')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Invalid(f'Cannot read JSON: {path}: {exc}') from exc


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create(path, value):
    """Publish a complete file without replacing any concurrently created file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.publishing-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def location_settings(root):
    path = root / '.team-workflow/local.json'
    settings = read(path) if path.exists() else {}
    obj(settings, (), {'repositories', 'inputs'})
    result = {}
    for kind in ('repositories', 'inputs'):
        values = settings.get(kind, {})
        require(isinstance(values, dict), f'Local {kind} must be an object')
        result[kind] = {**values, **LOCATIONS.get()[kind]}
        for name, value in result[kind].items():
            text(name)
            text(value)
    return result


def external_path(root, name, item):
    settings = location_settings(root)
    kind = 'repositories' if item['kind'] == 'repository' else 'inputs'
    key = item['repository'] if kind == 'repositories' else name
    require(key in settings[kind], f'Missing local {kind} mapping: {key}')
    value = Path(settings[kind][key]).expanduser()
    path = (root / value).resolve()
    require(path != root.resolve(), 'External input cannot refer to this project itself')
    if kind == 'repositories':
        from portable import repository_id
        require(repository_id(path) == key, f'Local checkout identity differs from {key}')
    return path


def now():
    return datetime.now(timezone.utc).isoformat()


def inside(root, name, exists=True):
    text(name)
    rel = Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name, f'Expected project-relative path: {name}')
    path = root / rel
    require(path.resolve().is_relative_to(root.resolve()), f'Path escapes project: {name}')
    if exists:
        require(path.exists(), f'Missing path: {name}')
    return path


def git(root, *args):
    try:
        p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=30,
                           env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
        require(p.returncode == 0, 'Cannot read Git state: ' + p.stderr.decode(errors='replace')[:300])
        return p.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid(f'Cannot read Git: {exc}') from exc


def reserved(name):
    return name.split('/')[0] in {'.team-workflow', '.codestable'}


def snapshot(root, profile):
    root = root.resolve()
    require(Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == root, '--root must be the Git root')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    staged = {}
    for line in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not line:
            continue
        header, raw_name = line.split(b'\t', 1)
        mode, oid, stage = header.decode().split()
        name = os.fsdecode(raw_name)
        require(mode != '160000', 'Submodules must be verified as separate participating repositories')
        require(stage == '0', f'Unresolved merge: {name}')
        require(not name.startswith('.team-workflow/'), 'Generated evidence must not be Git-tracked')
        if not reserved(name):
            staged[name] = header.decode()
    names = {os.fsdecode(x) for x in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if x}
    for name in profile['inputs']:
        path = inside(root, name)
        require(not reserved(name), 'Explicit inputs cannot be knowledge or generated evidence')
        if path.is_dir():
            names.update(p.relative_to(root).as_posix() for p in path.rglob('*') if not p.is_dir())
        else:
            names.add(name)
    files = {}
    for name in sorted(names):
        if reserved(name):
            continue
        path = inside(root, name, exists=False)
        if path.is_symlink():
            require(path.exists(), f'Broken input symlink: {name}')
            require(path.is_file(), f'Directory symlink requires explicit separate repository: {name}')
            files[name] = {'link': os.readlink(path), 'sha256': sha(path)}
        elif path.is_file():
            files[name] = {'sha256': sha(path), 'executable': bool(path.stat().st_mode & 0o111)}
        elif not path.exists():
            files[name] = {'deleted': True}
        else:
            raise Invalid(f'Unsupported source input: {name}')
    data = {'head': head, 'index': staged, 'files': files}
    external = {}
    for key, item in profile.get('external_inputs', {}).items():
        path = external_path(root, key, item)
        require(path != root, 'External input cannot refer to this project itself')
        if item['kind'] == 'file':
            require(path.is_file(), f'Missing external input: {key}')
            external[key] = {'sha256': sha(path)}
        else:
            external[key] = snapshot(path, {'inputs': []})
    if external:
        data['external_inputs'] = external
    return {'digest': digest(data), **data}


def profile_valid(profile, root, check_context=True):
    obj(profile, {'schema_version', 'project', 'context', 'knowledge', 'checks', 'required_checks', 'risk_checks', 'inputs', 'environment_versions'}, {'external_inputs'})
    require(type(profile['schema_version']) is int and profile['schema_version'] in (3, 4),
            'Unsupported project configuration; expected schema_version 3 or 4. Adjust configuration explicitly; no migration is performed')
    location_settings(root)
    text(profile['project'])
    for name in strings(profile['context'], True):
        if check_context:
            require(inside(root, name).is_file(), f'Context is not a file: {name}')
    obj(profile['knowledge'], {'provider', 'entry'})
    require(profile['knowledge']['provider'] == 'cs', 'Expected independent CS provider')
    require(profile['knowledge']['entry'] == '.codestable/wiki/INDEX.md', 'Expected current CS entry')
    strings(profile['inputs'])
    require(isinstance(profile.get('external_inputs', {}), dict), 'external_inputs must be an object')
    for name, item in profile.get('external_inputs', {}).items():
        text(name)
        obj(item, {'kind'}, {'repository', 'role'} if profile['schema_version'] == 4 else {'repository'})
        if 'role' in item:
            require(item['role'] in ('build', 'modified', 'joint'), 'Dependency role must be build, modified or joint')
        require(item['kind'] in ('file', 'repository'), 'External input must be a file or Git repository')
        if item['kind'] == 'repository':
            require(bool(re.fullmatch(r'[^/\s]+/[^/\s]+', text(item.get('repository')))), 'Expected owner/repository identity')
        else:
            require('repository' not in item, 'File locations belong in local inputs')
    require(isinstance(profile['checks'], dict), 'checks must be an object')
    for key, check in profile['checks'].items():
        require(re.fullmatch('[a-z][a-z0-9-]*', key), f'Invalid check ID: {key}')
        optional = {'report', 'artifacts', 'review'}
        if profile['schema_version'] == 4:
            optional |= {'repository', 'environment', 'revision_sensitive'}
        obj(check, {'argv', 'purpose', 'cwd', 'timeout', 'format', 'required_cases', 'required_env'}, optional)
        argv = check['argv']
        require(isinstance(argv, list) and bool(argv), 'Expected argv array')
        for arg in argv:
            text(arg)
        text(check['purpose'])
        check_root = root
        if check.get('repository'):
            entries = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == check['repository']]
            require(len(entries) == 1, 'Check repository must be a declared external input')
            check_root = external_path(root, check['repository'], entries[0])
        require(inside(check_root, check['cwd']).is_dir(), 'Check cwd must be an existing directory')
        if 'revision_sensitive' in check:
            require(type(check['revision_sensitive']) is bool, 'revision_sensitive must be boolean')
        if 'environment' in check:
            environment = obj(check['environment'], {'kind'}, {'identity', 'target'})
            require(environment['kind'] in ('stateless', 'fixture'), 'Environment kind must be stateless or fixture')
            if environment['kind'] == 'fixture':
                strings(environment.get('identity'), True)
            else:
                require('identity' not in environment, 'Stateless environment has no fixture identity')
            if 'target' in environment:
                names = set(profile['environment_versions'])
                target = obj(environment['target'], {'runtime', 'kind', 'versions'} | ({'fixture'} if environment['kind'] == 'fixture' else set()))
                require(target['kind'] == environment['kind'], 'Target environment kind mismatch')
                obj(target['runtime'], {'python', 'platform', 'machine'})
                for name in ('python', 'platform', 'machine'):
                    text(target['runtime'][name])
                obj(target['versions'], names)
                for name in names:
                    item = obj(target['versions'][name], {'command', 'identity'})
                    strings(item['command'], True); text(item['identity'])
                    require(item['command'] == profile['environment_versions'][name], 'Target environment command mismatch: ' + name)
                if environment['kind'] == 'fixture':
                    item = obj(target['fixture'], {'command', 'identity'})
                    text(item['identity'])
                    require(item['command'] == environment['identity'], 'Target fixture identity command mismatch')
        require(type(check['timeout']) is int and 0 < check['timeout'] <= 86400, 'Invalid timeout')
        require(check['format'] in ('command', 'go-json', 'junit'), 'Unknown result format')
        strings(check['required_cases'])
        strings(check['required_env'])
        if profile['schema_version'] == 4 and check['required_env']:
            require(check.get('environment', {}).get('kind') == 'fixture',
                    'Required environment values need a public fixture/configuration identity')
        if check['format'] == 'command':
            require(not check['required_cases'], 'Plain commands cannot declare test cases')
        if check['format'] == 'junit':
            require(check.get('report', '').startswith('{output}/'), 'JUnit report must use {output}/filename')
            require(any('{output}' in arg for arg in argv), 'Command must generate a fresh JUnit report')
        strings(check.get('artifacts', []))
        for name in check.get('artifacts', []):
            text(name)
            require(name.startswith('{output}/'), 'Artifacts must be generated inside this run output')
        if 'review' in check:
            review = obj(check['review'], {'format', 'path', 'required_artifacts'})
            require(review['format'] == 'codex-scenario', 'Unknown project review format')
            require(review['path'].startswith('{output}/'), 'Review must be inside run output')
            strings(review['required_artifacts'], True)
            require('manifest.json' in review['required_artifacts'], 'Scenario review requires manifest.json')
            require(all('{output}/' + name in check.get('artifacts', []) for name in review['required_artifacts']),
                    'Reviewed artifacts must be captured during execution')
    obj(profile['required_checks'], KINDS)
    for ids in profile['required_checks'].values():
        strings(ids)
        require(set(ids) <= profile['checks'].keys(), 'Unknown required check')
    require(isinstance(profile['risk_checks'], dict), 'risk_checks must be an object')
    for risk, ids in profile['risk_checks'].items():
        require(risk in RISKS, f'Unknown risk: {risk}')
        strings(ids, True)
        require(set(ids) <= profile['checks'].keys(), 'Unknown risk check')
    require(isinstance(profile['environment_versions'], dict), 'environment_versions must be an object')
    for name, argv in profile['environment_versions'].items():
        text(name)
        require(isinstance(argv, list) and bool(argv), 'Version command must be an argv array')
        for arg in argv:
            text(arg)
    return profile


def task_valid(task, profile, root):
    version = task.get('schema_version') if isinstance(task, dict) else None
    optional = {'design_id', 'section_ids', 'paths', 'symbols', 'scopes', 'parent'} if version == 4 else set()
    obj(task, {'schema_version', 'id', 'base', 'goal', 'non_goals', 'kind', 'risks', 'acceptance'}, optional)
    require(type(version) is int and version in (2, 4), 'Expected task schema_version 2 or 4')
    if version == 4:
        text(task.get('design_id'))
        strings(task.get('section_ids'), True)
    for key in ('id', 'goal', 'base'):
        text(task[key])
    require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', task['base']), 'Task base must be a full commit ID')
    git(root, 'cat-file', '-e', task['base'] + '^{commit}')
    strings(task['non_goals'])
    require(task['kind'] in KINDS, 'Unknown task kind')
    strings(task['risks'])
    require(set(task['risks']) <= RISKS, 'Unknown task risk')
    required = set(profile['required_checks'][task['kind']])
    for risk in task['risks']:
        require(bool(profile['risk_checks'].get(risk)), f'No validation configured for risk: {risk}')
        required.update(profile['risk_checks'][risk])
    require(isinstance(task['acceptance'], list) and bool(task['acceptance']), 'Acceptance cannot be empty')
    seen = set()
    for row in task['acceptance']:
        obj(row, {'id', 'expectation', 'checks'})
        key = text(row['id'])
        require(key not in seen, 'Duplicate acceptance ID')
        seen.add(key)
        text(row['expectation'])
        strings(row['checks'])
        require(set(row['checks']) <= profile['checks'].keys(), 'Unknown acceptance check')
        required.update(row['checks'])
    return sorted(required)


def binding(root, profile, task):
    return {'workspace': snapshot(root, profile), 'profile': digest(profile), 'task': digest(task)}


def artifact(root, path):
    path = Path(path)
    relative = path.relative_to(root).as_posix()
    require(inside(root, relative).is_file() and path.stat().st_size > 0, f'Missing/empty artifact: {relative}')
    return {'path': relative, 'sha256': sha(path)}


def artifact_valid(root, item):
    obj(item, {'path', 'sha256'})
    require(artifact(root, inside(root, item['path'])) == item, f'Artifact changed: {item["path"]}')
    return inside(root, item['path'])


def tool_identity():
    scripts = Path(__file__).parent
    return {'version': VERSION, 'scripts': {p.name: sha(p) for p in sorted(scripts.glob('*.py'))}}
