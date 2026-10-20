"""场景验收、评审绑定和回归状态共用的交付规则。"""
from common import Invalid, require
from error_codes import Code
import design_files
import materials
import scenario_rounds
import scenario_yaml
import scenarios


def current(root, profile, task, design, run_paths=None, *, workspace=None):
    from validation import Workspace
    workspace = workspace or Workspace(root, profile)
    group = materials.load(root, task['id']) or {'task_id': task['id'], 'runs': []}
    if run_paths is not None:
        from common import artifact, inside
        group = {**group, 'selected_runs': [artifact(root, inside(root, path)) for path in run_paths]}
    if group.get('platform'):
        inputs = scenarios.task_entries(root, group, profile, workspace=workspace)
    else:
        entries = scenarios.design_entries(design, task, profile, design_files.scenario_reader(root))
        inputs = design, task, entries
    return group, scenario_rounds.current_state(root, profile, group, inputs, workspace=workspace)


def bindings(value):
    return {key: value[key] for key in ('scenario_rounds', 'scenario_files')}


def selected(section, value):
    return [row for row in value['scenarios'] if any(row['file'] == ref['path'] and row['node'] in ref['nodes']
            for ref in section['data']['scenarios'])]


def check_cases(root, profile, task, design, group, *, workspace=None):
    if group.get('case_imports'):
        cases = scenarios.imported_cases(root, group)
        if group.get('case_coverage'):
            path = materials.checked(root, group['case_coverage'], 'case_coverage', task['id'])
            document = scenario_yaml.loads(path.read_text(encoding='utf-8'), '.json')
        else:
            document = scenario_yaml.loads('{"covered": [], "conflict": [], "disposed": []}', '.json')
        entries = current(root, profile, task, design, workspace=workspace)[1]['scenarios']
        result = scenarios.check_coverage(document, cases, {row['id'] for row in entries})
        require(result['ok'], result.get('problem', '补齐当前用例的场景覆盖'), error_code=Code.SCENARIO_COVERAGE)
    else:
        from designs import task_assessments
        require(not any(row['complexity'] == 'complex' for row in task_assessments(design, task['section_ids']).values()),
                '复杂任务需要主流程用例集（测试同事提供，或由未参与实现的测试代理编写），用 tw team scenarios import-cases 导入', error_code=Code.TESTER_CASES)


def check(root, profile, task, design, review, group, value, *, workspace=None):
    check_cases(root, profile, task, design, group, workspace=workspace)
    from contracts import independent
    incomplete = []
    states = {key: [] for key in ('failed', 'pending', 'blocked')}
    findings = {row['id']: row for row in review.get('findings', [])}
    for row in value['scenarios']:
        if row['state'] in states:
            states[row['state']].append(row['id'])
        result = row.get('result')
        if result:
            independent(design, result['executor'], '场景执行者')
        if row['state'] in ('pending', 'failed'):
            incomplete.append(row['id'] + '：' + row['state']
                              + ('（待判定：重跑或用 scenarios carry 沿用）' if row['reason'] == 'undetermined' else ''))
        elif row['state'] == 'blocked':
            finding = findings.get(result['finding'], {})
            if finding.get('state') not in ('accepted', 'deferred'):
                incomplete.append(row['id'] + '：blocked（问题 ' + result['finding'] + ' 需要 accepted 或 deferred 处置）')
    if incomplete:
        error = Invalid('场景验收尚待完成：' + '；'.join(incomplete), error_code=Code.SCENARIO_ACCEPTANCE)
        error.scenario_states = states
        raise error


def unverified_scope(value, findings):
    states = {row['id']: row['state'] for row in findings}
    return [{'scenario': row['id'], 'status': row['result']['status'],
             'finding': row['result']['finding'], 'finding_state': states[row['result']['finding']]}
            for row in value['scenarios'] if row['state'] == 'blocked']


def findings(value, existing, design, task):
    """按验收职责与节点引用一次填好问题身份，处置留给评审人。"""
    known, added = {row['id'] for row in existing}, {}
    acceptance_ids = {row['id'] for row in task['acceptance']}
    affected = {}
    for section in design['sections']:
        if section['type'] == 'acceptance' and section['id'] in acceptance_ids:
            for row in selected(section, value):
                affected.setdefault(row['id'], set()).add(section['id'])
    for row in value['scenarios']:
        result = row.get('result', {})
        key = result.get('finding')
        if row['state'] == 'blocked' and key not in known:
            summary = row['id'] + '：' + result['actual']
            if key not in added:
                added[key] = {'id': key, 'summary': summary, 'owner': design['roles']['acceptance_owner'],
                              'affects': [], 'blocks': ['acceptance'], 'state': 'open', 'resolution': {}}
            else:
                added[key]['summary'] = added[key]['summary'].rstrip('。；; ') + '；' + summary
            added[key]['affects'] = sorted(set(added[key]['affects']) | affected.get(row['id'], set()))
    return list(added.values())


def result_lines(rows):
    lines = ['场景执行：']
    for row in rows:
        result = row.get('result', {})
        lines += ['- ' + row['id'] + '：' + row['state'], '  - 实际结果：' + result.get('actual', '待执行'),
                  '  - 执行者：' + result.get('executor', '待执行'), '  - 轮次：' + str(row.get('round', '无'))]
        lines += ['  - 证据：' + ref['path'] for ref in result.get('evidence', [])]
        if result.get('finding'):
            lines.append('  - 问题：' + result['finding'])
    return lines
