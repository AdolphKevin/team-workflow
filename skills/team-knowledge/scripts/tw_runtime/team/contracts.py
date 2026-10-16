"""Business coverage, scenarios and issue dispositions shared by preparation and delivery.

These checks establish declared coverage, not the truth of a reviewer's prose.
"""
from error_codes import Code
from common import Invalid, obj, require, strings, text

LEVELS = {'unit', 'interface', 'journey', 'manual'}
STATES = {'open', 'resolved', 'accepted', 'deferred'}
COVERS = {'unit': {'unit', 'interface', 'journey'}, 'interface': {'interface', 'journey'}, 'journey': {'journey'}, 'manual': {'manual'}}
AUTOMATION = {'automated': {'check', 'cases'}, 'manual-only': {'reason', 'owner', 'trigger'},
              'pending-automation': {'reason', 'finding', 'due'}}


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
        require(set(value['affects']) <= set(section_ids), 'Issue references an unknown section', section='问题清单')
    strings(value['blocks'], True)
    require(set(value['blocks']) <= {'implementation', 'acceptance'}, 'Unknown issue blocking phase', section='问题清单')
    require(value['state'] in STATES, 'Unknown issue disposition', section='问题清单')
    resolution = value['resolution']
    if value['state'] == 'open':
        require(resolution == {}, 'An open issue cannot claim a resolution', section='问题清单')
    else:
        obj(resolution, {'reason', 'evidence'}, {'confirmed_by', 'confirmation', 'follow_up', 'scope_change'})
        material(resolution['reason'])
        strings(resolution['evidence'], True)
        for ref in resolution['evidence']:
            material(ref)
        if value['state'] in {'accepted', 'deferred'}:
            material(resolution.get('confirmed_by'))
        if 'confirmation' in resolution:
            require(isinstance(resolution['confirmation'], str), 'Confirmation must be text')
            require('__REPLACE__' not in resolution['confirmation'], 'Replace the named placeholder before continuing')
        if value['state'] == 'deferred':
            material(resolution.get('follow_up'))
            material(resolution.get('scope_change'))
    return value


def issues(values, section_ids=None):
    require(isinstance(values, list), 'Issues must be an array', section='问题清单')
    seen = set()
    for value in values:
        issue(value, section_ids)
        require(value['id'] not in seen, 'Duplicate issue identifier: ' + value['id'], section='问题清单')
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
        require(old['id'] in by_id, 'Known issue disappeared: ' + old['id'], section='问题清单')
        new = by_id[old['id']]
        require(all(old[k] == new[k] for k in ('summary', 'owner', 'affects', 'blocks')),
                'Known issue identity or affected scope changed: ' + old['id'], section='问题清单')
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
    issues(value['issues'], rows)
    identifiers = {row['id'] for row in value['issues']}
    assessments = [value['assessment']] + [r['data']['assessment'] for r in rows.values() if r['type'] == 'task' and 'assessment' in r['data']]
    for assessment in assessments:
        require(set(assessment['uncertainties']) <= identifiers, 'Assessment uncertainties must reference shared issue IDs', section='问题清单')
    for row in rows.values():
        material(row['title']); material(row['body'])
        if row['type'] != 'acceptance':
            continue
        data = row['data']
        require('scenario' not in data, '场景写在场景文件，验收节用 `- 场景：<路径>#<节点>`')
        require({'scenarios', 'verification'} <= data.keys(), '验收需要 scenarios 场景引用与 verification 验证要求：' + row['id'])
        require(isinstance(data['scenarios'], list) and bool(data['scenarios']), '验收至少引用一份场景文件')
        for reference in data['scenarios']:
            obj(reference, {'path', 'sha256', 'nodes'})
            from designs import _path
            _path(reference['path'])
            import re
            require(isinstance(reference['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', reference['sha256']), '场景引用填写 sha256')
            strings(reference['nodes'], True)
        if 'sources' in data:
            sources(data['sources'])
        verification = data['verification']
        require(isinstance(verification, dict) and 'coverage' not in verification,
                'verification 不再接受 coverage；验证：自动；用例 <用例>；替身 <替身>；覆盖范围写在 .tw/config.json 的 checks.<编号>.coverage')
        obj(verification, {'method', 'cases', 'substitutes'})
        require(verification['method'] in {'automatic', 'manual'}, 'Unknown verification method')
        strings(verification['cases'])
        strings(verification['substitutes'])
        if verification['method'] == 'automatic':
            require(bool(data['checks']), 'Automatic acceptance needs an executable check')
        else:
            require(not verification['cases'] and not verification['substitutes'], '人工验证不能填写用例或替身')
    for identifier in scope['requirement_acceptance']:
        require(identifier in rows and rows[identifier]['type'] == 'acceptance', 'Missing requirement acceptance section')
    strings(value['assessment']['drivers'], True)
    for driver in value['assessment']['drivers']:
        material(driver)
    for row in rows.values():
        if row['type'] == 'task' and 'assessment' in row['data']:
            strings(row['data']['assessment']['drivers'], True)


def sources(values):
    """Confirmed business origins of a scenario's expectations; the tool checks presence, not truth."""
    require(isinstance(values, list) and bool(values), 'Scenario sources must be a non-empty list')
    seen = set()
    for value in values:
        obj(value, {'ref', 'version', 'confirmed_by'})
        for key in ('ref', 'version', 'confirmed_by'):
            material(value[key])
        require((value['ref'], value['version']) not in seen, 'Duplicate scenario source: ' + value['ref'])
        seen.add((value['ref'], value['version']))
    return values


def unsourced(task, plan):
    rows = {v['id']: v for v in plan['sections']}
    return sorted(a['id'] for a in task['acceptance'] if not rows[a['id']]['data'].get('sources'))


def identity(value):
    return ' '.join(value.split()).casefold()


def independent(plan, actor, label):
    """Recorded identities must differ; the tool cannot prove two names are different people."""
    owner = plan['roles']['implementation_owner']
    require(bool(owner.strip()), 'Acceptance needs the recorded implementation owner to check independence', error_code=Code.INDEPENDENCE)
    material(actor)
    require(identity(actor) != identity(owner), label + ' must not be the implementation owner: ' + actor, error_code=Code.INDEPENDENCE)


def match_coverage(required, actual):
    coverage(actual)
    require(actual['isolation'] != 'unresolved', 'Verification environment isolation is unresolved')
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
    gaps = ['Acceptance scenario needs confirmed business sources: ' + key for key in unsourced(task, plan)]
    requirement_acceptance = rows['scope-global']['data']['requirement_acceptance']
    for a in task['acceptance']:
        required = rows[a['id']]['data']['verification']
        if required['method'] == 'automatic':
            checks = rows[a['id']]['data']['checks']
            for key in checks:
                actual = profile['checks'][key].get('coverage')
                if actual is None or actual['isolation'] == 'unresolved':
                    reason = '未声明覆盖范围' if actual is None else '隔离未解决'
                    gaps.append(f'在 .tw/config.json 的 checks.{key}.coverage 中补全覆盖范围及隔离声明（验收 {a["id"]}，检查 {key}：{reason}）')
                if actual and set(actual['substitutes']) - set(required['substitutes']):
                    from design_markdown import listing, verification_text
                    allowed = list(dict.fromkeys(required['substitutes'] + actual['substitutes']))
                    missing = list(dict.fromkeys(value for value in actual['substitutes'] if value not in required['substitutes']))
                    line = '- 验证：' + verification_text({**required, 'substitutes': allowed})
                    gaps.append(f'把 {a["id"]} 的验证行改为：{line}（检查 {key} 还使用了未允许的替身：{listing(missing, outer=("；",))}）')
            names = '、'.join(checks)
            if a['id'] in requirement_acceptance and not any(
                    profile['checks'][key].get('coverage', {}).get('level') == 'journey' for key in checks):
                gaps.append(f'改用 journey 层级的检查，或改为人工验收（需求级验收 {a["id"]}，检查 {names}：均未声明完整业务路径层级）')
            if required['cases'] and all(profile['checks'][key]['format'] == 'command' for key in checks):
                gaps.append(f'删除用例，或改用报告用例的检查（验收 {a["id"]}，检查 {names}：命令型检查没有逐项用例结果）')
    return list(dict.fromkeys(gaps))


def automation(value, task, findings, profile, execution):
    """Declared regression state per scenario; structure and references only, not proof of protection."""
    from datetime import date
    obj(value, {'scenarios'})
    require(isinstance(value['scenarios'], list) and bool(value['scenarios']), 'Automation needs declared scenarios')
    acceptance = {a['id'] for a in task['acceptance']}
    deferred = {f['id'] for f in findings if f['state'] == 'deferred'}
    status, seen = {'automated': [], 'manual_only': [], 'pending_automation': []}, set()
    for entry in value['scenarios']:
        require(isinstance(entry, dict) and entry.get('status') in AUTOMATION, 'Unknown automation status')
        obj(entry, {'id', 'acceptance', 'guarantee', 'status', 'level'} | AUTOMATION[entry['status']])
        material(entry['id']); material(entry['guarantee'])
        require(entry['id'] not in seen, 'Duplicate automation scenario: ' + entry['id'])
        seen.add(entry['id'])
        strings(entry['acceptance'], True)
        require(set(entry['acceptance']) <= acceptance, 'Automation references an unknown acceptance')
        require(entry['level'] in LEVELS, 'Unknown verification level')
        require((entry['level'] == 'manual') == (entry['status'] == 'manual-only'),
                'Only manual-only scenarios use the manual level')
        if entry['status'] == 'automated':
            key = entry['check']
            require(key in profile['checks'] and key in execution['results'], 'Automated scenario needs an executed check: ' + key)
            require(profile['checks'][key].get('coverage', {}).get('level') in COVERS[entry['level']],
                    'Automated check level does not cover the declared regression level')
            strings(entry['cases'])
            require(all(execution['results'][key].get('cases', {}).get(c) == 'passed' for c in entry['cases']),
                    'Automated case is missing, failed or skipped')
            status['automated'].append({'id': entry['id'], 'acceptance': entry['acceptance'], 'level': entry['level'], 'check': key})
        elif entry['status'] == 'manual-only':
            for key in ('reason', 'owner', 'trigger'):
                material(entry[key])
            status['manual_only'].append({'id': entry['id'], 'acceptance': entry['acceptance'], 'owner': entry['owner']})
        else:
            material(entry['reason'])
            require(entry['finding'] in deferred, 'Pending automation needs a deferred issue with follow-up: ' + entry['id'], section='问题清单')
            try:
                date.fromisoformat(entry['due'])
            except (TypeError, ValueError):
                raise Invalid('Pending automation needs an ISO due date: ' + entry['id'])
            status['pending_automation'].append({'id': entry['id'], 'acceptance': entry['acceptance'], 'level': entry['level'],
                                                 'finding': entry['finding'], 'due': entry['due']})
    return status
