"""Business coverage and issue dispositions shared by preparation and delivery.

These checks establish declared coverage, not the truth of a reviewer's prose.
"""
from common import obj, require, strings, text

LEVELS = {'unit', 'interface', 'journey', 'manual'}
STATES = {'open', 'resolved', 'accepted', 'deferred'}


def material(value):
    text(value)
    require('__REPLACE__' not in value, 'Replace the named placeholder before continuing')
    return value


def coverage(value):
    obj(value, {'level', 'entrypoints', 'environment', 'substitutes', 'isolation', 'isolation_evidence'})
    require(value['level'] in LEVELS, 'Unknown verification level')
    strings(value['entrypoints'], True)
    for item in value['entrypoints']:
        material(item)
    material(value['environment'])
    strings(value['substitutes'])
    require(value['isolation'] in {'isolated', 'shared-reviewed', 'unresolved'}, 'Unknown isolation state')
    strings(value['isolation_evidence'])
    if value['isolation'] == 'shared-reviewed':
        require(bool(value['isolation_evidence']), 'Shared resources need isolation evidence')
    return value


def issue(value, section_ids=None):
    obj(value, {'id', 'summary', 'owner', 'affects', 'blocks', 'state', 'resolution'})
    for key in ('id', 'summary', 'owner'):
        material(value[key])
    strings(value['affects'])
    if section_ids is not None and value.get('state') == 'open':
        require(set(value['affects']) <= set(section_ids), 'Issue references an unknown section')
    strings(value['blocks'], True)
    require(set(value['blocks']) <= {'implementation', 'acceptance'}, 'Unknown issue blocking phase')
    require(value['state'] in STATES, 'Unknown issue disposition')
    resolution = value['resolution']
    if value['state'] == 'open':
        require(resolution == {}, 'An open issue cannot claim a resolution')
    else:
        obj(resolution, {'reason', 'evidence'}, {'confirmed_by', 'confirmation', 'follow_up', 'scope_change'})
        material(resolution['reason'])
        strings(resolution['evidence'], True)
        for ref in resolution['evidence']:
            material(ref)
        if value['state'] in {'accepted', 'deferred'}:
            material(resolution.get('confirmed_by'))
            material(resolution.get('confirmation'))
        if value['state'] == 'deferred':
            material(resolution.get('follow_up'))
            material(resolution.get('scope_change'))
    return value


def issues(values, section_ids=None):
    require(isinstance(values, list), 'Issues must be an array')
    seen = set()
    for value in values:
        issue(value, section_ids)
        require(value['id'] not in seen, 'Duplicate issue identifier: ' + value['id'])
        seen.add(value['id'])
    return values


def relevant(value, required):
    return not value['affects'] or bool(set(value['affects']) & set(required))


def unresolved(values, required, phase):
    return [v for v in values if v['state'] == 'open' and phase in v['blocks'] and relevant(v, required)]


def reconcile(known, current):
    """Every known issue survives, with an explicit disposition for each change."""
    issues(current)
    by_id = {v['id']: v for v in current}
    for old in known:
        require(old['id'] in by_id, 'Known issue disappeared: ' + old['id'])
        new = by_id[old['id']]
        require(all(old[k] == new[k] for k in ('summary', 'owner', 'affects', 'blocks')),
                'Known issue identity or affected scope changed: ' + old['id'])
    return current


def design(value):
    rows = {v['id']: v for v in value['sections']}
    scope = rows['scope-global']['data']
    require({'requirement_acceptance', 'impact'} <= scope.keys(), 'Plan needs requirement acceptance and impact investigation')
    strings(scope['requirement_acceptance'], True)
    require(len(set(scope['requirement_acceptance'])) == len(scope['requirement_acceptance']), 'Duplicate requirement acceptance')
    require(isinstance(scope['impact'], list) and bool(scope['impact']), 'Plan needs affected entrypoints and service responsibilities')
    for row in scope['impact']:
        obj(row, {'repository', 'entrypoint', 'operations', 'producer', 'consumer', 'commit_owner', 'acceptance'})
        for key in ('repository', 'entrypoint', 'producer', 'consumer', 'commit_owner'):
            material(row[key])
        strings(row['operations'], True)
        strings(row['acceptance'], True)
        require(all(k in rows and rows[k]['type'] == 'acceptance' for k in row['acceptance']), 'Impact needs actual acceptance references')
    require('issues' in value, 'Plan needs an explicit known-issues list')
    issues(value['issues'], rows)
    identifiers = {row['id'] for row in value['issues']}
    assessments = [value['assessment']] + [r['data']['assessment'] for r in rows.values() if r['type'] == 'task' and 'assessment' in r['data']]
    for assessment in assessments:
        require(set(assessment['uncertainties']) <= identifiers, 'Assessment uncertainties must reference shared issue IDs')
    require(not value.get('decisions'), 'Use shared issue IDs for v5 decisions')
    for row in rows.values():
        material(row['title']); material(row['body'])
        if row['type'] != 'acceptance':
            continue
        data = row['data']
        require({'scenario', 'verification'} <= data.keys(), 'Acceptance needs a business scenario and verification requirements: ' + row['id'])
        scenario = obj(data['scenario'], {'actor', 'initial_state', 'steps', 'expected', 'negative_cases'})
        for key in ('actor', 'initial_state', 'expected'):
            material(scenario[key])
        for key in ('steps', 'negative_cases'):
            strings(scenario[key], True)
            for item in scenario[key]:
                material(item)
        verification = data['verification']
        obj(verification, {'method', 'coverage', 'cases'})
        require(verification['method'] in {'automatic', 'manual'}, 'Unknown verification method')
        coverage(verification['coverage'])
        strings(verification['cases'])
        if verification['method'] == 'automatic':
            require(bool(data['checks']), 'Automatic acceptance needs an executable check')
        else:
            require(verification['coverage']['level'] == 'manual', 'Manual acceptance needs manual coverage')
    for identifier in scope['requirement_acceptance']:
        require(identifier in rows and rows[identifier]['type'] == 'acceptance', 'Missing requirement acceptance section')
        require(rows[identifier]['data']['verification']['coverage']['level'] in {'journey', 'manual'},
                'Requirement acceptance must cover the business journey or explicit manual observations')
    strings(value['assessment']['drivers'], True)
    for driver in value['assessment']['drivers']:
        material(driver)
    for row in rows.values():
        if row['type'] == 'task' and 'assessment' in row['data']:
            strings(row['data']['assessment']['drivers'], True)


def match_coverage(required, actual):
    coverage(required); coverage(actual)
    require(actual['isolation'] != 'unresolved', 'Verification environment isolation is unresolved')
    allowed = {'unit': {'unit', 'interface', 'journey'}, 'interface': {'interface', 'journey'}, 'journey': {'journey'}, 'manual': {'manual'}}
    require(actual['level'] in allowed[required['level']], 'Verification level does not cover the declared acceptance')
    require(set(required['entrypoints']) <= set(actual['entrypoints']), 'Verification omits a required business entrypoint')
    require(required['environment'] == actual['environment'], 'Verification environment differs from the plan')
    require(set(actual['substitutes']) <= set(required['substitutes']), 'Verification substituted an undeclared dependency')


def task_scope(task, plan):
    expected = 'requirement' if not task.get('parent') and task['id'] == plan['task_id'] else 'task'
    require(task.get('acceptance_scope') == expected, 'Acceptance scope must distinguish the parent requirement from a child task')
    if expected == 'requirement':
        scope = next(v['data'] for v in plan['sections'] if v['id'] == 'scope-global')
        require(set(scope['requirement_acceptance']) <= {a['id'] for a in task['acceptance']},
                'Parent requirement omits its business journey acceptance')
    else:
        require(task.get('parent') == plan['task_id'] and task['id'] != plan['task_id'], 'Child task needs its actual parent requirement')


def execution_environment(profile, task, plan):
    """Preparation is read-only: inspect declarations without running environment commands."""
    rows = {v['id']: v for v in plan['sections']}
    gaps = []
    for a in task['acceptance']:
        required = rows[a['id']]['data']['verification']
        if required['coverage']['isolation'] == 'unresolved':
            gaps.append('Unresolved verification isolation: ' + a['id'])
        if required['method'] == 'automatic':
            for key in a['checks']:
                actual = profile['checks'][key].get('coverage')
                if actual is None:
                    gaps.append('Check needs declared business coverage: ' + key)
                elif actual['isolation'] == 'unresolved':
                    gaps.append('Unresolved verification isolation: ' + key)
    return sorted(set(gaps))
