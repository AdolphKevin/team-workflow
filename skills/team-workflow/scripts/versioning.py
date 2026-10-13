"""Refuse to interpret a project configured by a newer team-workflow."""
import re

from common import Invalid, VERSION, require

PROFILE_SCHEMA = 5
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
    return {**info, 'status': 'current'}


def ensure_tool_current(profile):
    info = status(profile)
    if info['status'] == 'tool-outdated':
        raise Outdated(f"Installed team-workflow {VERSION} is older than the project "
                       f"({info['project'] or 'schema ' + str(info['profile_schema'])})",
                       'tool-outdated', info['next_action'], info)
    return info
