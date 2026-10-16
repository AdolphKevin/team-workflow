"""场景验收、评审绑定和回归状态共用的交付规则。"""
from common import require
from error_codes import Code
import design_files
import materials
import scenario_rounds
import scenario_yaml
import scenarios


def current(root, profile, task, design, run_paths=None):
    group = materials.load(root, task['id']) or {'task_id': task['id'], 'runs': []}
    if run_paths is not None:
        from common import artifact, inside
        group = {**group, 'selected_runs': [artifact(root, inside(root, path)) for path in run_paths]}
    if group.get('platform'):
        inputs = scenarios.task_entries(root, group, profile)
    else:
        entries = scenarios.design_entries(design, task, profile, design_files.scenario_reader(root))
        inputs = design, task, entries
    return group, scenario_rounds.current_state(root, profile, group, inputs)


def bindings(value):
    return {key: value[key] for key in ('scenario_rounds', 'scenario_files')}


def selected(section, value):
    return [row for row in value['scenarios'] if any(row['file'] == ref['path'] and row['node'] in ref['nodes']
            for ref in section['data']['scenarios'])]


def check_cases(root, profile, task, design, group):
    if group.get('case_imports'):
        cases = scenarios.imported_cases(root, group)
        if group.get('case_coverage'):
            path = materials.checked(root, group['case_coverage'], 'case_coverage', task['id'])
            document = scenario_yaml.loads(path.read_text(encoding='utf-8'), '.json')
        else:
            document = scenario_yaml.loads('{"covered": [], "conflict": [], "disposed": []}', '.json')
        entries = current(root, profile, task, design)[1]['scenarios']
        result = scenarios.check_coverage(document, cases, {row['id'] for row in entries})
        require(result['ok'], result.get('problem', '补齐当前用例的场景覆盖'), error_code=Code.SCENARIO_COVERAGE)
    else:
        from designs import task_assessments
        require(not any(row['complexity'] == 'complex' for row in task_assessments(design, task['section_ids']).values()),
                '复杂任务需要测试同事的用例集，用 tw team scenarios import-cases 导入', error_code=Code.TESTER_CASES)


def check(root, profile, task, design, review, group, value):
    check_cases(root, profile, task, design, group)
    from contracts import independent
    incomplete = []
    findings = {row['id']: row for row in review.get('findings', [])}
    for row in value['scenarios']:
        result = row.get('result')
        if result:
            independent(design, result['executor'], '场景执行者')
        if row['state'] in ('pending', 'failed'):
            incomplete.append(row['id'] + '：' + row['state'])
        elif row['state'] == 'blocked':
            finding = findings.get(result['finding'], {})
            if finding.get('state') not in ('accepted', 'deferred'):
                incomplete.append(row['id'] + '：blocked（问题 ' + result['finding'] + ' 需要 accepted 或 deferred 处置）')
    require(not incomplete, '场景验收尚待完成：' + '；'.join(incomplete), error_code=Code.SCENARIO_ACCEPTANCE)


def regression(root, profile, task, group, value, findings):
    deferred = {row['id'] for row in findings if row['state'] == 'deferred'}
    status, checks = {'automated': [], 'manual-only': [], 'pending': []}, {}
    for row in value['scenarios']:
        declared = row.get('regression', {})
        category = 'pending'
        if 'pending' in declared:
            require(declared['pending'] in deferred, '场景 ' + row['id'] + ' 的 regression.pending 引用评审中 deferred 的问题：'
                    + declared['pending'], section='问题清单')
        elif 'manual' in declared:
            category = 'manual-only'
        elif scenario_rounds.regression_passed(root, profile, task, group, row, checks):
            category = 'automated'
        status[category].append({'id': row['id'], **declared})
    return status


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
                added[key]['summary'] += '；' + summary
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
