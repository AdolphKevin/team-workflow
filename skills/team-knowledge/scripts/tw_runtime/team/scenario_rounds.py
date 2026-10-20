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
    return {'executed': sum(row['status'] != 'carry' for row in rows),
            **{status: sum(row['status'] == status for row in rows) for status in scenario_results.STATUSES + ('carry',)}}


def statistics(entries, history, states):
    """当前内容的首次结果及各执行者的最新结果，统一按登记轮次排序。"""
    first, executors = {}, {}
    for record in history:
        for row in record['results']:
            key = row['scenario']
            if key not in entries or row['fingerprint'] != entries[key]['fingerprint']:
                continue
            if row['status'] != 'carry':
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
            'summary_counts': {**{state: sum(row['state'] == state for row in states)
                                  for state in ('passed', 'failed', 'blocked', 'pending')},
                               'carried': sum(row['state'] == 'passed' and row['result']['status'] == 'carry'
                                              for row in states)}}


def current_state(root, profile, group, inputs=None, *, workspace=None):
    """所有场景命令共用的当前状态入口；历史只按内容与源码判定。"""
    workspace = workspace or validation.Workspace(root, profile)
    design, task, entries = inputs or scenarios.task_entries(root, group, profile, workspace=workspace)
    source, product = workspace.fingerprints(design)
    history = rounds(root, group)
    previous, latest = set(), {}
    for record in history:
        for row in record['results']:
            key = row['scenario']
            previous.add(key)
            if key in entries and row['fingerprint'] == entries[key]['fingerprint']:
                latest[key] = (record, row)
    states = []
    for key, entry in entries.items():
        state, reason = 'pending', 'changed' if key in previous else 'new'
        if key in latest:
            record, row = latest[key]
            if row['status'] == 'fail':
                state, reason = 'failed', 'failed'
            elif row['status'] in ('blocked', 'skip'):
                state, reason = 'blocked', None
            elif record['product_digest'] == product:
                state, reason = 'passed', None
            else:
                # 产品变化后，已通过或沿用的场景由独立执行者判定重跑或沿用。
                reason = 'undetermined'
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
        reason = row['reason'] + ('：待判定，重跑或用 scenarios carry 沿用' if row['reason'] == 'undetermined' else '')
        lines += [row['id'] + ' · ' + row['node'] + ' · ' + row['title'] + '（' + reason + '）',
                  '内容指纹：' + row['fingerprint'], '验收入口 verify：' + row['verify']]
        from commands import readable_fields
        lines += readable_fields(row['acceptance_entry'], '  ')
        for key, label in (('initial_state', '初始状态'), ('steps', '步骤'), ('expected', '预期结果'),
                           ('forbidden_effects', '核对副作用')):
            lines += [label + ('：' if row[key] else '：无')] + ['  ' + str(i) + '. ' + text for i, text in enumerate(row[key], 1)]
    lines.append('当前汇总：' + '，'.join(key + ' ' + str(counts[key]) for key in counts))
    return lines


def pending_result(root, task_id, value, *, workspace=None):
    rows = [row for row in value['scenarios'] if row['state'] in ('pending', 'failed')]
    from commands import current_status
    return {'ok': True, 'task_id': task_id, **{key: item for key, item in value.items() if key != 'scenarios'},
            'pending': rows, 'pending_count': len(rows),
            'summary': f'本任务有 {len(rows)} 条待执行场景。',
            'next_action': ('按清单执行场景，然后提交结果：' + repairs.task_command(
                root, task_id, 'scenarios submit', '--results <文件>')
                + ('；判定不受影响的待判定场景写明理由与改动范围后沿用：' + repairs.task_command(
                    root, task_id, 'scenarios carry', '--results <文件>')
                   if any(row['reason'] == 'undetermined' for row in rows) else '')) if rows else current_status(
                    root, task_id, workspace=workspace, scenario_state=value)['next_action']}


def pending(root, task_id, profile, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    return pending_result(root, task_id, current_state(root, profile, scenarios.current(root, task_id), workspace=workspace), workspace=workspace)


def status_step(root, profile, task_id, progress, group=None, *, workspace=None, state=None):
    """在检查之后展示场景执行，未执行的场景先于评审。"""
    group = group or materials.load(root, task_id)
    if group is None:
        return
    value = state if state is not None else current_state(root, profile, group, workspace=workspace)
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


def task_metrics(root, profile, group, since=None, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    value = current_state(root, profile, group, workspace=workspace)
    return {'statistics': value['statistics'],
            'rounds': [{'round': row['round'], 'submitted_at': row['submitted_at'], 'statistics': row['statistics'],
                        'pass_rate': ratio(row['statistics']['pass'], row['statistics']['executed'])}
                       for row in rounds(root, group) if not since or row['submitted_at'] >= since]}


def submit(root, task_id, profile, path, *, carry=False, workspace=None):
    """登记一轮执行结果；carry 登记待判定场景的沿用，不重新执行。"""
    workspace = workspace or validation.Workspace(root, profile)
    from cleanup import guard
    from contracts import independent
    with guard(root):
        group = scenarios.current(root, task_id)
        inputs = scenarios.task_entries(root, group, profile, workspace=workspace)
        before = current_state(root, profile, group, inputs, workspace=workspace)
        entries = {row['id']: row for row in before['scenarios']}
        rows = scenario_results.load(path, entries, carry=carry)
        if carry:
            wrong = [{'line': index + 1, 'problem': '只沿用待判定的场景：' + row['scenario'] + ' 当前为 '
                      + entries[row['scenario']]['state'] + '（' + str(entries[row['scenario']]['reason']) + '）'}
                     for index, row in enumerate(rows) if entries[row['scenario']]['reason'] != 'undetermined']
            if wrong:
                raise FileProblems(wrong, Code.SCENARIO_RESULT)
        # 待判定场景可以重跑，也可以沿用，不要求出现在本次结果中。
        missing = [] if carry else [key for key, row in entries.items() if row['state'] in ('pending', 'failed')
                                    and row['reason'] != 'undetermined' and key not in {result['scenario'] for result in rows}]
        if missing:
            return {'ok': False, 'error_code': Code.SCENARIO_RESULTS_INCOMPLETE, 'missing': missing,
                    'problem': '补齐待执行场景的结果：' + '、'.join(missing)}
        design = inputs[0]
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
        workspace.refresh()
        inputs = scenarios.task_entries(root, group, profile, workspace=workspace)
        after = current_state(root, profile, group, inputs, workspace=workspace)
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
        updated = pending_result(root, task_id, current_state(root, profile, group, inputs, workspace=workspace), workspace=workspace)
        summary = f'第 {number} 轮已登记，沿用 {len(rows)} 条场景。' if carry else f'第 {number} 轮已登记，共执行 {len(rows)} 条场景。'
        return {**updated, 'artifact': ref, 'round': number, 'round_statistics': record['statistics'], 'summary': summary}
