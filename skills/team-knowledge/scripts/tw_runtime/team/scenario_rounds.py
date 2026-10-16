"""场景的当前状态、待执行清单与结果轮次。"""
import shlex
import uuid

from common import Invalid, artifact, artifact_valid, create, now, read, require, sha, write
from error_codes import Code
from scenario_files import FileProblems
import materials
import scenario_results
import scenarios
import validation


def rounds(root, group):
    values = []
    for ref in group.get('scenario_rounds', []):
        value = read(materials.checked(root, ref, 'scenario_rounds', group['task_id']))
        require(value.get('data_version') == 1 and value.get('kind') == 'scenario-round'
                and value.get('task_id') == group['task_id'], '场景轮次属于本任务且采用 data_version: 1')
        for row in value['results']:
            for evidence in row['evidence']:
                artifact_valid(root, evidence)
        values.append(value)
    return sorted(values, key=lambda row: row['round'])


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': numerator / denominator if denominator else None}


def round_statistics(rows):
    return {'executed': len(rows), **{status: sum(row['status'] == status for row in rows)
                                    for status in scenario_results.STATUSES}}


def regression_runs(root, group):
    """场景复用任务历次运行；显式选用的运行仍由当前材料决定。"""
    if group.get('selected_runs') is not None:
        return [ref['path'] for ref in group['selected_runs']]
    from checklist import records
    paths = [ref['path'] for ref in group['runs']]
    for claim, response in records(root, group['task_id']):
        ref = (response or {}).get('artifact')
        if claim.get('command') == 'run' and ref:
            try:
                path = artifact_valid(root, ref).relative_to(root).as_posix()
            except (Invalid, OSError, ValueError, TypeError, KeyError):
                continue
            if path not in paths:
                paths.append(path)
    return paths


def statistics(entries, history, states):
    """当前内容的首次结果及各执行者的最新结果，统一按登记轮次排序。"""
    first, executors = {}, {}
    for record in history:
        for row in record['results']:
            key = row['scenario']
            if key not in entries or row['fingerprint'] != entries[key]['fingerprint']:
                continue
            first.setdefault(key, row['status'])
            from contracts import identity
            executors.setdefault(identity(row['executor']), {})[key] = row
    by_executor = {}
    votes = {}
    for latest in executors.values():
        actor = list(latest.values())[-1]['executor']
        by_executor[actor] = round_statistics(list(latest.values()))
        for key, row in latest.items():
            if row['status'] in ('pass', 'fail'):
                votes.setdefault(key, []).append(row['status'])
    multiple = [statuses for statuses in votes.values() if len(statuses) >= 2]
    return {'first_pass': ratio(sum(status == 'pass' for status in first.values()),
                                sum(status in ('pass', 'fail') for status in first.values())),
            'by_executor': by_executor,
            'agreement': ratio(sum(all(status == 'pass' for status in statuses) for statuses in multiple), len(multiple)),
            'summary_counts': {state: sum(row['state'] == state for row in states)
                               for state in ('passed', 'failed', 'blocked', 'pending')}}


def current_state(root, profile, group):
    """所有场景命令共用的当前状态入口；历史只按内容与源码判定。"""
    design, task, entries = scenarios.task_entries(root, group, profile)
    source = validation.source_digest(root, profile)
    product = validation.product_digest(root, profile, design)
    history = rounds(root, group)
    previous, latest = set(), {}
    for record in history:
        for row in record['results']:
            key = row['scenario']
            previous.add(key)
            if key in entries and row['fingerprint'] == entries[key]['fingerprint']:
                latest[key] = (record, row)
    checks = {}

    def regression_passed(entry):
        regression = entry.get('regression', {})
        if 'check' not in regression:
            return False
        key = regression['check']
        selection = (key, tuple(regression['cases']))
        if selection not in checks:
            # 把场景用例交给原有解码与运行选用，同时核对 Go 父用例的子用例。
            try:
                check = profile['checks'][key]
                require(check['format'] != 'command', '回归检查提供逐项用例报告')
                selected_profile = {**profile, 'checks': {**profile['checks'], key: {
                    **check, 'required_cases': list(dict.fromkeys(check['required_cases'] + regression['cases']))}}}
                validation.verify_runs(root, selected_profile, task, regression_runs(root, group), checks=[key])
                checks[selection] = True
            except (Invalid, OSError, ValueError, TypeError, KeyError):
                checks[selection] = False
        return checks[selection]

    states = []
    for key, entry in entries.items():
        state, reason = 'pending', 'changed' if key in previous else 'new'
        if key in latest:
            record, row = latest[key]
            if row['status'] == 'fail':
                state, reason = 'failed', 'failed'
            elif row['status'] in ('blocked', 'skip'):
                state, reason = 'blocked', None
            elif record['product_digest'] == product or regression_passed(entry):
                state, reason = 'passed', None
            else:
                reason = 'source-changed'
        states.append({**entry, 'state': state, 'reason': reason})
    totals = statistics(entries, history, states)
    return {'scenarios': states, 'source_digest': source, 'product_digest': product,
            'summary_counts': totals['summary_counts'], 'statistics': totals}


def pending_action(task_id):
    return 'tw team scenarios pending --task ' + shlex.quote(task_id)


def review_action(root, task_id):
    import reviews
    return (reviews.submission_action(root, task_id) if reviews.locations(root, task_id)[0].is_file()
            else 'tw team review --task ' + shlex.quote(task_id))


def pending_result(root, task_id, value):
    rows = [row for row in value['scenarios'] if row['state'] in ('pending', 'failed')]
    lines = []
    for row in rows:
        lines += [row['id'] + ' · ' + row['node'] + ' · ' + row['title'] + '（' + row['reason'] + '）',
                  '内容指纹：' + row['fingerprint'], '验收入口 verify：' + row['verify']]
        from commands import readable_fields
        lines += readable_fields(row['acceptance_entry'], '  ')
        for key, label in (('initial_state', '初始状态'), ('steps', '步骤'), ('expected', '预期结果'),
                           ('forbidden_effects', '核对副作用')):
            lines += [label + '：'] + ['  ' + str(i) + '. ' + text for i, text in enumerate(row[key], 1)]
    counts = value['summary_counts']
    lines.append('当前汇总：' + '，'.join(key + ' ' + str(counts[key]) for key in counts))
    return {'ok': True, 'task_id': task_id, **value, 'pending': rows, 'pending_count': len(rows), 'lines': lines,
            'summary': f'本任务有 {len(rows)} 条待执行场景。',
            'next_action': pending_action(task_id) if rows else review_action(root, task_id)}


def pending(root, task_id, profile):
    return pending_result(root, task_id, current_state(root, profile, scenarios.current(root, task_id)))


def status_step(root, profile, task_id, progress, group=None):
    """只补充状态展示，保留现有流程的判定和总下一步。"""
    group = group or materials.load(root, task_id)
    if group is None:
        return
    value = current_state(root, profile, group)
    counts = value['summary_counts']
    todo = counts['pending'] + counts['failed']
    review = next((row['next_command'] for row in progress['steps'] if row['id'] == 'review'), review_action(root, task_id))
    row = {'id': 'scenarios', 'label': '场景验收', 'state': 'pending' if todo or counts['blocked'] else 'done',
           'evidence': (group.get('scenario_rounds') or [{}])[-1].get('path'),
           'summary_counts': counts, 'first_pass': value['statistics']['first_pass'],
           'next_command': pending_action(task_id) if todo else review}
    index = next((i + 1 for i, row in enumerate(progress['steps']) if row['id'] == 'run'), len(progress['steps']))
    progress['steps'].insert(index, row)


def task_metrics(root, profile, group, since=None):
    value = current_state(root, profile, group)
    return {'statistics': value['statistics'],
            'rounds': [{'round': row['round'], 'submitted_at': row['submitted_at'], 'statistics': row['statistics'],
                        'pass_rate': ratio(row['statistics']['pass'], row['statistics']['executed'])}
                       for row in rounds(root, group) if not since or row['submitted_at'] >= since]}


def submit(root, task_id, profile, path):
    from cleanup import guard
    from contracts import independent
    with guard(root):
        group = scenarios.current(root, task_id)
        before = current_state(root, profile, group)
        entries = {row['id']: row for row in before['scenarios']}
        rows = scenario_results.load(path, entries)
        missing = [key for key, row in entries.items() if row['state'] in ('pending', 'failed')
                   and key not in {result['scenario'] for result in rows}]
        if missing:
            return {'ok': False, 'error_code': Code.SCENARIO_RESULTS_INCOMPLETE, 'missing': missing,
                    'problem': '补齐待执行场景的结果：' + '、'.join(missing)}
        design = scenarios.task_entries(root, group, profile)[0]
        for row in rows:
            try:
                independent(design, row['executor'], '场景执行者')
            except Invalid as exc:
                raise Invalid('由独立于实施负责人的执行者提交结果：' + row['executor'], error_code=exc.error_code,
                              next_action='由未参与实施的执行者实际执行并提交：tw team scenarios submit --task '
                              + shlex.quote(task_id) + ' --results <文件>') from exc
        history = rounds(root, group)
        number = max((record['round'] for record in history), default=0) + 1
        directory = materials.path(root, task_id).parent / 'scenarios' / ('round-' + str(number) + '-' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        for index, row in enumerate(rows):
            refs = []
            for ordinal, ref in enumerate(row['evidence']):
                try:
                    source = artifact_valid(path.parent, ref)
                    target = directory / (str(index + 1) + '-' + str(ordinal + 1) + '-' + source.name)
                    target.write_bytes(source.read_bytes())
                    require(sha(target) == ref['sha256'] and sha(source) == ref['sha256'],
                            '按当前证据重新提交，复制期间指纹已变化：' + ref['path'])
                    refs.append(artifact(root, target))
                except (Invalid, OSError, ValueError, TypeError) as exc:
                    raise FileProblems([{'line': index + 1, 'problem': 'evidence：' + str(exc)}], Code.SCENARIO_RESULT) from exc
            row.update(evidence=refs, fingerprint=entries[row['scenario']]['fingerprint'])
        after = current_state(root, profile, group)
        require(after['source_digest'] == before['source_digest']
                and {row['id']: row['fingerprint'] for row in after['scenarios']} == {key: row['fingerprint'] for key, row in entries.items()},
                '提交期间源码或场景内容已变化，请按当前内容重新执行。', error_code=Code.SOURCE_STALE,
                next_action=pending_action(task_id))
        record = {'data_version': 1, 'kind': 'scenario-round', 'task_id': task_id, 'round': number,
                  'source_digest': before['source_digest'], 'product_digest': before['product_digest'],
                  'submitted_at': now(), 'results': rows,
                  'statistics': round_statistics(rows)}
        target = directory / 'round.json'
        create(target, record)
        ref = artifact(root, target)
        group.setdefault('scenario_rounds', []).append(ref)
        write(materials.path(root, task_id), group)
        updated = pending_result(root, task_id, current_state(root, profile, group))
        return {**updated, 'artifact': ref, 'round': number, 'round_statistics': record['statistics'],
                'summary': f'第 {number} 轮已登记，共执行 {len(rows)} 条场景。'}
