"""Shared validation, content binding and file helpers. Standard library only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from contextvars import ContextVar
from datetime import datetime, timezone

from tw_runtime import DATA_VERSION, VERSION, Invalid as RuntimeInvalid, install, repo_paths
from tw_runtime.project import CONFIG, MAPPING, TEAM_KEYS, config_problems, user_mapping_path
from tw_runtime.project import location_settings as project_locations

RECORD_SCHEMA = DATA_VERSION
RISKS = {'authorization', 'persistence', 'concurrency', 'messaging', 'public-contract', 'cross-service'}
KINDS = {'code', 'docs'}
INSTALL_HOME = ContextVar('workflow_install_home', default=None)
LOCATIONS = ContextVar('workflow_locations', default={'repositories': {}, 'inputs': {}})


class Invalid(RuntimeInvalid, ValueError):
    error_code = 'invalid-or-incomplete-input'
    next_action = None


class ToolModified(Invalid):
    """An installed skill differs from its release; the fix is a reinstall, never an input change."""
    error_code = 'tool-modified'
    next_action = ('Reinstall the named skill from its release (npx skills update -g) and report the defect; '
                   'do not patch installed files. --allow-modified-tool records an explicit team-workflow override.')


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
    local_write_guard(path)
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
    local_write_guard(path)
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


def create_text(path, value):
    """Publish exact UTF-8 text without overwriting an existing editable or immutable file."""
    path = Path(path)
    local_write_guard(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.publishing-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(value.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def location_settings(root):
    try:
        return project_locations(root, overrides=LOCATIONS.get())
    except RuntimeInvalid as exc:
        raise Invalid(str(exc)) from exc


def external_path(root, name, item):
    settings = location_settings(root)
    kind = 'repositories' if item['kind'] == 'repository' else 'inputs'
    key = item['repository'] if kind == 'repositories' else name
    require(key in settings[kind],
            f'Missing local {kind} mapping: {key}；请在 {root / MAPPING} 或用户级 {user_mapping_path()} 中登记')
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


def git(root, *args, input=None, local_only=False):
    try:
        environment = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}
        if local_only:
            environment['GIT_NO_LAZY_FETCH'] = '1'
        p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=30, input=input,
                           env=environment)
        require(p.returncode == 0, 'Cannot read Git state: ' + p.stderr.decode(errors='replace')[:300])
        return p.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid(f'Cannot read Git: {exc}') from exc


def knowledge_path(name):
    """Knowledge body paths, excluding configuration, the local ignore rules and all local evidence."""
    return name in {'.tw/overview.md', '.tw/glossary.md'} or any(
        name.startswith(f'.tw/{kind}/') for kind in ('rules', 'decisions', 'lessons'))


def explicit_input(name, inputs):
    return any(name == p.rstrip('/') or name.startswith(p.rstrip('/') + '/') for p in inputs)


def reserved(name, inputs=()):
    return name in ('.tw/local', '.tw/.gitignore') or name.startswith('.tw/local/') or (
        knowledge_path(name) and not explicit_input(name, inputs))


def ensure_local(root, name='.tw/local/.ignore-probe'):
    try:
        ignored = git(root, 'check-ignore', '--no-index', '--', '.tw/local/', name).decode().splitlines()
    except Invalid as exc:
        raise Invalid('生成本地证据前必须用 .tw/.gitignore 忽略 .tw/local/') from exc
    require('.tw/local/' in ignored and name in ignored, '生成本地证据前必须忽略整个 .tw/local/：' + name)
    tracked = git(root, 'ls-files', '-z', '--', '.tw/local').split(b'\0')
    require(not any(tracked), '.tw/local/ 本地证据不能被 Git 跟踪')


def local_write_guard(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.name == 'local' and parent.parent.name == '.tw':
            root = parent.parent.parent
            ensure_local(root, path.relative_to(root).as_posix())
            return


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
        require(not (name == '.tw/local' or name.startswith('.tw/local/')), '.tw/local/ 本地证据不能被 Git 跟踪')
        if not reserved(name, profile['inputs']):
            staged[name] = header.decode()
    names = {os.fsdecode(x) for x in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if x}
    for name in profile['inputs']:
        path = inside(root, name)
        require(not (name == '.tw/local' or name.startswith('.tw/local/')), '.tw/local/ 本地证据不能作为 inputs')
        if path.is_dir():
            names.update(p.relative_to(root).as_posix() for p in path.rglob('*') if not p.is_dir())
        else:
            names.add(name)
    files = {}
    for name in sorted(names):
        if reserved(name, profile['inputs']):
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


def accounts(values):
    """Who may sign in. Undeclared accounts are treated as real: the user signs in in a real browser."""
    require(isinstance(values, list), 'accounts must be a list')
    seen = set()
    for row in values:
        obj(row, {'id', 'kind', 'environment', 'login'}, {'isolation', 'credential_env', 'note'})
        require(text(row['id']) not in seen, 'Duplicate account: ' + row['id'])
        seen.add(row['id'])
        text(row['environment'])
        require(row['kind'] in ('real', 'synthetic'), 'Account kind is real or synthetic: ' + row['id'])
        require(row['login'] in ('user', 'agent-after-authorization'), 'Account login is user or agent-after-authorization')
        require(row['kind'] == 'synthetic' or row['login'] == 'user',
                'A real account is always signed in by the user: ' + row['id'])
        if row['kind'] == 'synthetic':
            text(row.get('isolation', ''))
        for name in strings(row.get('credential_env', [])):
            require(bool(re.fullmatch(r'[A-Z_][A-Z0-9_]*', name)), 'credential_env lists variable names, never values')
    return values


def load_profile(root, check_context=True):
    """Read the single project config and adapt its name for existing team logic."""
    config = read(Path(root) / CONFIG)
    problems = config_problems(config)
    require(not problems, '；'.join(problems))
    optional = {'external_inputs': {}, 'accounts': []}
    missing = [key for key in TEAM_KEYS if key not in config and key not in optional]
    require(not missing, '.tw/config.json 尚未配置团队功能，缺少字段：' + ', '.join(missing))
    profile = {key: config.get(key, optional.get(key)) for key in TEAM_KEYS}
    if 'platform' in config:
        profile['platform'] = config['platform']
    profile.update(data_version=config['data_version'], project=config['project']['name'], context=config.get('context', []))
    return profile_valid(profile, root, check_context)


def profile_valid(profile, root, check_context=True):
    obj(profile, {'data_version', 'project', 'context', *TEAM_KEYS}, {'platform'})
    require(type(profile['data_version']) is int and profile['data_version'] == DATA_VERSION,
            '项目数据只支持 data_version 1')
    accounts(profile['accounts'])
    location_settings(root)
    text(profile['project'])
    for name in strings(profile['context']):
        if check_context:
            require(inside(root, name).is_file(), f'Context is not a file: {name}')
    strings(profile['inputs'])
    require(isinstance(profile.get('external_inputs', {}), dict), 'external_inputs must be an object')
    for name, item in profile.get('external_inputs', {}).items():
        text(name)
        obj(item, {'kind'}, {'repository', 'role'})
        if 'role' in item:
            require(item['role'] in ('build', 'modified', 'joint'), 'Dependency role must be build, modified or joint')
        require(item['kind'] in ('file', 'repository'), 'External input must be a file or Git repository')
        if item['kind'] == 'repository':
            from tw_runtime.team import platform_script as platform_read
            platform_read.repository(item.get('repository'))
        else:
            require('repository' not in item, 'File locations belong in local inputs')
    require(isinstance(profile['checks'], dict), 'checks must be an object')
    for key, check in profile['checks'].items():
        require(re.fullmatch('[a-z][a-z0-9-]*', key), f'Invalid check ID: {key}')
        optional = {'report', 'artifacts', 'review', 'repository', 'environment', 'coverage', 'revision_sensitive'}
        obj(check, {'argv', 'purpose', 'cwd', 'timeout', 'format', 'required_cases', 'required_env'}, optional)
        if 'coverage' in check:
            from contracts import coverage
            coverage(check['coverage'])
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
        if check['required_env']:
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
    obj(task, {'data_version', 'id', 'base', 'goal', 'non_goals', 'kind', 'risks', 'acceptance',
               'design_id', 'section_ids', 'acceptance_scope'}, {'paths', 'symbols', 'scopes', 'parent'})
    require(type(task['data_version']) is int and task['data_version'] == 1, 'Expected task data_version 1')
    text(task['design_id'])
    strings(task['section_ids'], True)
    require(task['acceptance_scope'] in ('task', 'requirement'), 'Task needs acceptance_scope: task or requirement')
    for key in ('id', 'goal', 'base'):
        text(task[key])
    require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', task['base']), 'Task base must be a full commit ID')
    git(root, 'cat-file', '-e', task['base'] + '^{commit}')
    strings(task['non_goals'])
    try:
        for path in strings(task.get('paths', [])):
            repo_paths.normalize(path, scope=True)
    except RuntimeInvalid as exc:
        raise Invalid(str(exc)) from exc
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


EVIDENCE_LIMIT_BYTES = 64 * 1024 * 1024
EXECUTABLE_MAGIC = (b'\x7fELF', b'MZ', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe',
                    b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe')


def evidence_file(path, allow_large=False):
    """Evidence is what a reviewer can read. Binaries are identified by build commit and command, not copied."""
    path = Path(path)
    with path.open('rb') as handle:
        head = handle.read(4)
    require(not head.startswith(EXECUTABLE_MAGIC),
            f'{path.name} is a compiled executable; record the build commit and command instead of copying binaries into evidence')
    require(allow_large or path.stat().st_size <= EVIDENCE_LIMIT_BYTES,
            f'{path.name} exceeds {EVIDENCE_LIMIT_BYTES // (1024 * 1024)} MiB; keep an excerpt or pass --allow-large-evidence')
    return path


def artifact(root, path):
    path = Path(path)
    relative = path.relative_to(root).as_posix()
    require(inside(root, relative).is_file() and path.stat().st_size > 0, f'Missing/empty artifact: {relative}')
    return {'path': relative, 'sha256': sha(path)}


def artifact_valid(root, item):
    obj(item, {'path', 'sha256'})
    require(artifact(root, inside(root, item['path'])) == item, f'Artifact changed: {item["path"]}')
    return inside(root, item['path'])


SKILL_ROOT = install.SKILL.parent / 'team-workflow'
ALLOW_MODIFIED = 'TEAM_WORKFLOW_ALLOW_MODIFIED_TOOL'


def skill_resource(name=None):
    require((SKILL_ROOT / 'SKILL.md').is_file(),
            f'缺少同级 team-workflow 技能目录：{SKILL_ROOT}；请安装同一发行的两个技能')
    path = SKILL_ROOT / name if name else SKILL_ROOT
    require(path.exists(), f'team-workflow 技能缺少资源：{path}')
    return path


def rules_digest(skill=None):
    """The written rules an agent follows; recorded when a task starts so later changes are visible."""
    skill = skill or skill_resource()
    files = [skill / 'SKILL.md', *sorted((skill / 'references').glob('*.md')), *sorted((skill / 'templates').glob('guidance-*.md'))]
    return digest({p.relative_to(skill).as_posix(): sha(p) for p in files if p.is_file()})


def tool_identity():
    scripts = Path(__file__).parent
    return {'version': VERSION, 'scripts': {p.name: sha(p) for p in sorted(scripts.glob('*.py'))},
            'installation': install.check_install(INSTALL_HOME.get(), require_team=True), 'rules_digest': rules_digest()}


def tool_gate():
    """Verification refuses a modified installation unless the override is explicit and recorded."""
    state = install.check_install(INSTALL_HOME.get(), require_team=True)
    override = os.environ.get(ALLOW_MODIFIED) == '1'
    if not state['ok'] and not override:
        raise ToolModified('安装与发行清单不一致：' + '；'.join(state['problems'])
                           + '；请重新安装同一发行的两个技能，或用 --allow-modified-tool 显式记录覆盖')
    return {'version': VERSION, 'integrity': 'intact' if state['ok'] else 'modified', 'override': not state['ok']}
