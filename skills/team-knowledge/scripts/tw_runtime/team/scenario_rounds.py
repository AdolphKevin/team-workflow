"""场景的当前状态、待执行清单与结果轮次。"""
import uuid

from common import Invalid, artifact, artifact_valid, create, now, read, require, sha, write
from error_codes import Code
from scenario_files import FileProblems
import materials
import repairs
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


def regression_passed(root, profile, task, group, entry, checks=None):
    checks = checks if checks is not None else {}
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


def current_state(root, profile, group, inputs=None):
    """所有场景命令共用的当前状态入口；历史只按内容与源码判定。"""
    design, task, entries = inputs or scenarios.task_entries(root, group, profile)
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

    states = []
    for key, entry in entries.items():
        state, reason = 'pending', 'changed' if key in previous else 'new'
        if key in latest:
            record, row = latest[key]
            if row['status'] == 'fail':
                state, reason = 'failed', 'failed'
            elif row['status'] in ('blocked', 'skip'):
                state, reason = 'blocked', None
            elif record['product_digest'] == product or regression_passed(root, profile, task, group, entry, checks):
                state, reason = 'passed', None
            else:
                reason = 'source-changed'
        result = ({'result': latest[key][1], 'round': latest[key][0]['round']} if key in latest else {})
        states.append({**entry, 'state': state, 'reason': reason, **result})
    totals = statistics(entries, history, states)
    return {'scenarios': states, 'source_digest': source, 'product_digest': product,
            'summary_counts': totals['summary_counts'], 'statistics': totals,
            'scenario_rounds': group.get('scenario_rounds', []),
            'scenario_files': [{'path': path, 'sha256': checksum} for path, checksum in sorted(
                {(row['file'], row['file_sha256']) for row in entries.values()})]}


def pending_action(root, task_id):
    return repairs.task_command(root, task_id, 'scenarios pending')


def pending_lines(rows, counts):
    lines = []
    for row in rows:
        lines += [row['id'] + ' · ' + row['node'] + ' · ' + row['title'] + '（' + row['reason'] + '）',
                  '内容指纹：' + row['fingerprint'], '验收入口 verify：' + row['verify']]
        from commands import readable_fields
        lines += readable_fields(row['acceptance_entry'], '  ')
        for key, label in (('initial_state', '初始状态'), ('steps', '步骤'), ('expected', '预期结果'),
                           ('forbidden_effects', '核对副作用')):
            lines += [label + ('：' if row[key] else '：无')] + ['  ' + str(i) + '. ' + text for i, text in enumerate(row[key], 1)]
    lines.append('当前汇总：' + '，'.join(key + ' ' + str(counts[key]) for key in counts))
    return lines


def pending_result(root, task_id, value):
    rows = [row for row in value['scenarios'] if row['state'] in ('pending', 'failed')]
    from commands import current_status
    return {'ok': True, 'task_id': task_id, **{key: item for key, item in value.items() if key != 'scenarios'},
            'pending': rows, 'pending_count': len(rows),
            'summary': f'本任务有 {len(rows)} 条待执行场景。',
            'next_action': ('按清单执行场景，然后提交结果：' + repairs.task_command(
                root, task_id, 'scenarios submit', '--results <文件>')) if rows else current_status(root, task_id)['next_action']}


def pending(root, task_id, profile):
    return pending_result(root, task_id, current_state(root, profile, scenarios.current(root, task_id)))


def status_step(root, profile, task_id, progress, group=None):
    """在检查之后展示场景执行，未执行的场景先于评审。"""
    group = group or materials.load(root, task_id)
    if group is None:
        return
    value = current_state(root, profile, group)
    counts = value['summary_counts']
    todo = counts['pending'] + counts['failed']
    row = {'id': 'scenarios', 'label': '场景验收', 'state': 'pending' if todo else 'done',
           'evidence': (group.get('scenario_rounds') or [{}])[-1].get('path'),
           'summary_counts': counts, 'first_pass': value['statistics']['first_pass']}
    if todo:
        row['next_command'] = pending_action(root, task_id)
    index = next((i + 1 for i, row in enumerate(progress['steps']) if row['id'] == 'run'), len(progress['steps']))
    progress['steps'].insert(index, row)
    if todo and (progress.get('next_step') or {}).get('id') in ('review', 'acceptance', 'knowledge', 'delivery'):
        progress.update(next_step=row, finished=False)


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
                              next_action='由未参与实施的执行者实际执行并提交：' + repairs.task_command(root, task_id, 'scenarios submit', '--results <文件>')) from exc
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
                next_action=pending_action(root, task_id))
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
