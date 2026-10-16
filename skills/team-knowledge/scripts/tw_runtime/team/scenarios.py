"""场景核对、累积用例导入与覆盖的结构核对。"""
from pathlib import Path
import uuid

from common import Invalid, artifact, create_text, read, require, write
from error_codes import Code
import materials
import scenario_files
import scenario_yaml


def case_document(raw, suffix):
    try:
        document = scenario_yaml.loads(raw, suffix)
    except Invalid as exc:
        raise scenario_files.FileProblems([{'line': getattr(exc, 'line', 1), 'problem': str(exc)}], Code.CASE_LIST) from exc
    v, value = scenario_files.Validation(document), document.value
    rows, key = [], 'test_cases'
    if not isinstance(value, dict):
        v.add((), '顶层对象包含 test_cases 或 cases 数组')
    else:
        key = 'test_cases' if 'test_cases' in value else 'cases'
        rows = v.array(value.get(key), (key,))
    seen = set()
    for index, row in enumerate(rows):
        path = (key, index)
        if not isinstance(row, dict):
            v.add(path, '每条用例为对象，包含 id 与 title')
            continue
        for field in ('id', 'title'):
            v.text(row.get(field), path + (field,))
        identifier = row.get('id')
        if isinstance(identifier, str):
            if identifier in seen:
                v.add(path + ('id',), '重复用例编号：' + identifier)
            seen.add(identifier)
    if v.errors:
        raise scenario_files.FileProblems(v.errors, Code.CASE_LIST)
    return rows


def imported_cases(root, group):
    """按导入登记顺序合并，同一编号采用最后一次的完整内容。"""
    cases = {}
    for ref in group.get('case_imports', []):
        path = materials.checked(root, ref, 'case_imports', group['task_id'])
        for row in case_document(path.read_text(encoding='utf-8'), path.suffix):
            cases[row['id']] = row
    return cases


def current(root, task_id):
    group = materials.load(root, task_id)
    if group is None:
        raise materials.MaterialGap('current', '尚待建立', task_id)
    materials.validate(root, group)
    return group


def snapshot(root, group, name, raw):
    target = materials.path(root, group['task_id']).parent / 'scenarios' / (uuid.uuid4().hex + '-' + name)
    create_text(target, raw)
    return artifact(root, target)


def import_cases(root, task_id, path):
    try:
        raw = path.read_text(encoding='utf-8')
        rows = case_document(raw, path.suffix)
    except (OSError, UnicodeError) as exc:
        raise scenario_files.FileProblems([{'line': 1, 'problem': '读取用例文件：' + str(exc)}], Code.CASE_LIST) from exc
    from cleanup import guard
    with guard(root):
        group = current(root, task_id)
        before = imported_cases(root, group)
        added = [row['id'] for row in rows if row['id'] not in before]
        updated = [row['id'] for row in rows if row['id'] in before]
        ref = snapshot(root, group, 'cases' + ('.json' if path.suffix.lower() == '.json' else '.yaml'), raw)
        group.setdefault('case_imports', []).append(ref)
        write(materials.path(root, task_id), group)
        total = len(set(before) | {row['id'] for row in rows})
    return {'ok': True, 'imported': len(rows), 'total': total, 'added': added, 'updated': updated,
            'artifact': ref, 'summary': '用例快照已登记，累积集合已更新。'}


def task_entries(root, group, profile):
    """按本任务验收节引用的节点读取完整场景，平台材料沿用方案提交。"""
    import design_files
    design = design_files.read(materials.checked(root, group['design'], 'design', group['task_id']))
    # 平台方案已由其不可变原文解析，场景读取沿用同一提交。
    if group.get('platform'):
        import coordination
        platform = coordination.load(group['task_id'], root=root)
        design = platform['design']
        reference = platform['design_source']
        reader = design_files.scenario_reader(root)
        if reference:
            checkout = design_files._checkout(root, reference['repository'])
            reader = design_files.scenario_reader(checkout, reference['commit'])
    else:
        reader = design_files.scenario_reader(root)
    task = read(materials.checked(root, group['task'], 'task', group['task_id']))
    return design, task, design_entries(design, task, profile, reader)


def design_entries(design, task, profile, reader):
    acceptance = {row['id'] for row in task['acceptance']}
    entries = {}
    for section in design['sections']:
        if section['type'] != 'acceptance' or section['id'] not in acceptance:
            continue
        for ref in section['data']['scenarios']:
            value, file_sha256 = reader(ref['path'])
            for node in value['sops']:
                if node['id'] in ref['nodes']:
                    for row in node['scenarios']:
                        entry = {**row, 'node': node['id'], 'file': ref['path'],
                                 'fingerprint': scenario_files.fingerprint(row), 'file_sha256': file_sha256,
                                 'acceptance_entry': profile.get('acceptance_entries', {}).get(row['verify'])}
                        require(row['id'] not in entries or entries[row['id']] == entry,
                                '场景编号在本任务中唯一：' + row['id'], error_code=Code.SCENARIO_FILE)
                        entries[row['id']] = entry
    return entries


def task_scenarios(root, group):
    from common import load_profile
    return set(task_entries(root, group, load_profile(root))[2])


def check_coverage(document, cases, identifiers):
    v, pairs, categories = scenario_files.Validation(document), document.value, {}
    if not v.shape(pairs, (), {'covered', 'conflict', 'disposed'}, pairs.keys() if isinstance(pairs, dict) else ()):
        raise scenario_files.FileProblems(v.errors, Code.SCENARIO_COVERAGE)
    for category in ('covered', 'conflict', 'disposed'):
        for index, row in enumerate(v.array(pairs.get(category), (category,))):
            p = (category, index)
            required = {'case', 'state', 'reason', 'confirmed_by'} if category == 'disposed' else {'case', 'scenarios', 'note'}
            if not v.shape(row, p, required, row.keys() if isinstance(row, dict) else ()):
                continue
            key = row.get('case')
            if not isinstance(key, str) or key not in cases:
                v.add(p + ('case',), 'case 引用已导入的用例：' + str(key))
            else:
                categories.setdefault(key, []).append(category)
            if category == 'disposed':
                if row.get('state') not in ('blocked', 'deferred', 'out-of-scope'):
                    v.add(p + ('state',), 'state 取 blocked、deferred 或 out-of-scope')
                for field in ('reason', 'confirmed_by'):
                    v.text(row.get(field), p + (field,))
            else:
                for ordinal, scenario in enumerate(v.array(row.get('scenarios'), p + ('scenarios',))):
                    if not isinstance(scenario, str) or scenario not in identifiers:
                        v.add(p + ('scenarios', ordinal), 'scenarios 引用本任务的场景编号：' + str(scenario))
                if not isinstance(row.get('note'), str):
                    v.add(p + ('note',), 'note 应为字符串')
    incomplete = []
    for key in cases:
        assigned = categories.get(key, [])
        if len(assigned) != 1 or assigned[0] == 'conflict':
            category = 'unclassified' if not assigned else assigned[0] if len(assigned) == 1 else 'duplicate'
            incomplete.append({'case': key, 'category': category})
            v.errors.append({'problem': '用例 ' + key + '：' + category})
    if v.errors:
        result = scenario_files.FileProblems(v.errors, Code.SCENARIO_COVERAGE).result()
        result['cases'] = incomplete
        return result
    return {'ok': True}


def coverage(root, task_id, path):
    try:
        raw = path.read_text(encoding='utf-8')
        document = scenario_yaml.loads(raw, '.json')
    except (Invalid, OSError, UnicodeError) as exc:
        raise scenario_files.FileProblems([{'line': getattr(exc, 'line', 1), 'problem': '读取配对文件：' + str(exc)}], Code.SCENARIO_COVERAGE) from exc
    from cleanup import guard
    with guard(root):
        group = current(root, task_id)
        cases, identifiers = imported_cases(root, group), task_scenarios(root, group)
        result = check_coverage(document, cases, identifiers)
        if not result['ok']:
            return result
        pairs = document.value
        ref = snapshot(root, group, 'coverage.json', raw)
        group['case_coverage'] = ref
        write(materials.path(root, task_id), group)
    return {'ok': True, 'total': len(cases), 'covered': len(pairs['covered']), 'disposed': len(pairs['disposed']),
            'artifact': ref, 'summary': '全部导入用例已覆盖或已处置。'}


def dispatch(args, root, profile):
    try:
        if args.scenario_action == 'check':
            return scenario_files.check(root / args.file, profile)
        if args.scenario_action == 'import-cases':
            return import_cases(root, str(args.task), root / args.file)
        if args.scenario_action == 'pending':
            import scenario_rounds
            return scenario_rounds.pending(root, str(args.task), profile)
        if args.scenario_action == 'submit':
            import scenario_rounds
            return scenario_rounds.submit(root, str(args.task), profile, root / args.results)
        return coverage(root, str(args.task), root / args.pairs)
    except scenario_files.FileProblems as exc:
        return exc.result()
