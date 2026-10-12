"""Compare the installed tool with the project configuration and upgrade older projects."""
import copy
import re

from common import Invalid, VERSION, profile_valid, require

PROFILE_SCHEMA = 4
UPGRADABLE_SCHEMAS = (3, 4)
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?')
UPDATE_TOOL = 'npx skills update -g'


class Outdated(Invalid):
    def __init__(self, message, error_code, next_action, version):
        super().__init__(message)
        self.error_code, self.next_action, self.version = error_code, next_action, version


def parse(value):
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    require(match is not None, f'Expected a semantic version: {value!r}')
    release = tuple(int(part) for part in match.group(1, 2, 3))
    pre = match.group(4)
    return release, tuple((0, int(p), '') if p.isdigit() else (1, 0, p) for p in pre.split('.')) if pre else None


def compare(left, right):
    """Semantic Versioning 2.0 precedence: a prerelease sorts before its release."""
    (a, pa), (b, pb) = parse(left), parse(right)
    if a != b:
        return -1 if a < b else 1
    if pa == pb:
        return 0
    if pa is None or pb is None:
        return 1 if pa is None else -1
    return -1 if pa < pb else 1


def status(profile):
    """Classify a raw profile without validating the rest of its fields."""
    schema = profile.get('schema_version')
    project = profile.get('workflow_version')
    info = {'tool': VERSION, 'project': project, 'profile_schema': schema, 'latest_profile_schema': PROFILE_SCHEMA}
    require(type(schema) is int, 'Project configuration needs an integer schema_version')
    newer_schema = schema > PROFILE_SCHEMA
    newer_version = project is not None and compare(project, VERSION) > 0
    if newer_schema or newer_version:
        return {**info, 'status': 'tool-outdated',
                'next_action': f'The project uses a newer team-workflow; run `{UPDATE_TOOL}`, start a new session and retry.'}
    if schema < PROFILE_SCHEMA or project is None or compare(project, VERSION) < 0:
        return {**info, 'status': 'project-outdated',
                'next_action': 'Run `workflow.py upgrade` to preview, then `workflow.py upgrade --apply`, and rerun `project`.'}
    return {**info, 'status': 'current'}


def ensure_tool_current(profile):
    info = status(profile)
    if info['status'] == 'tool-outdated':
        raise Outdated(f"Installed team-workflow {VERSION} is older than the project "
                       f"({info['project'] or 'schema ' + str(info['profile_schema'])})",
                       'tool-outdated', info['next_action'], info)
    return info


def upgrade(root, profile, record=None):
    """Return the latest-format profile; never invent environments that need project commands."""
    info = ensure_tool_current(profile)
    schema = profile['schema_version']
    require(schema in UPGRADABLE_SCHEMAS,
            f'Profile schema_version {schema} cannot be upgraded directly; run `workflow.py migrate` first')
    profile_valid(profile, root)
    record = record or {}
    require(isinstance(record, dict) and record.keys() <= {'environment'}, 'Upgrade input only accepts environment')
    environments = record.get('environment', {})
    require(isinstance(environments, dict) and environments.keys() <= profile['checks'].keys(),
            'Upgrade environment input must name existing checks')
    result = copy.deepcopy(profile)
    changes, assumed, gaps = [], [], []
    if schema != PROFILE_SCHEMA:
        result['schema_version'] = PROFILE_SCHEMA
        changes.append(f'schema_version: {schema} -> {PROFILE_SCHEMA}')
    for name, item in result.get('external_inputs', {}).items():
        if item['kind'] == 'repository' and 'role' not in item:
            item['role'] = 'build'
            changes.append(f'external_inputs.{name}.role: build (build input only; adds no collaborator)')
    for key, check in result['checks'].items():
        if key in environments:
            check['environment'] = copy.deepcopy(environments[key])
            changes.append(f'checks.{key}.environment: {check["environment"]["kind"]} (from upgrade input)')
        elif 'environment' in check:
            continue
        elif check['required_env']:
            gaps.append({'check': key, 'required_env': check['required_env'],
                         'problem': 'Checks reading environment values need a fixture identity command from this project',
                         'input': {'environment': {key: {'kind': 'fixture', 'identity': ['<read-only command printing the fixture identity>']}}}})
        else:
            check['environment'] = {'kind': 'stateless'}
            assumed.append(key)
            changes.append(f'checks.{key}.environment: stateless (assumed; review)')
    if info['project'] != VERSION:
        result['workflow_version'] = VERSION
        changes.append(f"workflow_version: {info['project'] or 'unset'} -> {VERSION}")
    if gaps:
        return {'ok': False, 'status': 'needs-input', 'version': info, 'changes': changes, 'assumed_stateless': assumed,
                'gaps': gaps, 'problem': 'Some checks need a project-provided fixture identity before upgrading',
                'next_action': 'Add a read-only identity command for each gap, pass it with `upgrade --record <file>`, and retry.'}
    profile_valid(result, root)
    return {'ok': True, 'status': 'ready' if changes else 'current', 'version': info, 'changes': changes,
            'assumed_stateless': assumed, 'gaps': [], 'profile': result}
