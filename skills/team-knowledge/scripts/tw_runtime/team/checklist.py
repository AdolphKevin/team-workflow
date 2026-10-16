"""Where a task stands and the exact next command, read from the requests the tool already recorded."""
from artifacts import directory
from common import Invalid, artifact_valid, digest, read
import shlex

STEPS = [
    ('prepare', '准备任务与知识简报', lambda c: c.get('command') in ('start', 'prepare')),
    ('run', '运行检查', lambda c: c.get('command') == 'run'),
    ('review', '提交代码与验收评审', lambda c: c.get('command') == 'review' and c.get('submit')),
    ('acceptance', '业务验收', lambda c: c.get('command') == 'accept' or c.get('command') == 'verify' and c.get('phase') == 'acceptance'),
    ('knowledge', '交付报告写明知识处置', lambda c: c.get('command') == 'delivery-template'),
    ('delivery', '最终交付核查', lambda c: c.get('command') == 'verify' and c.get('phase') == 'delivery'),
]


def records(root, task_id):
    """Finished requests of this task, oldest first: (claim, response)."""
    base = directory(root, task_id).parent
    rows = []
    for claim_path in base.glob('*/request.json') if base.is_dir() else []:
        response_path = claim_path.parent / 'response.json'
        try:
            claim = read(claim_path)
            response = read(response_path) if response_path.is_file() else None
        except Exception:  # an unreadable request is reported by cleanup, not here
            continue
        if isinstance(claim, dict) and claim.get('task_id') == task_id:
            rows.append((claim, response))
    return sorted(rows, key=lambda row: row[0].get('started_at', ''))


def rows_started(rows, match):
    attempts = [c.get('started_at', '') for c, r in rows if match(c)]
    return attempts[-1] if attempts else None


def _artifact_value(root, response):
    item = (response or {}).get('artifact')
    try:
        return read(root / item['path']) if isinstance(item, dict) else None
    except Exception:
        return None


def source_stale(root, value, source_digest, profile=None):
    """Read the source binding each record actually stores; never query its environment."""
    if not isinstance(value, dict):
        return False
    if value.get('kind') in ('execution', 'imported-execution'):
        rows = value.get('results', []) if value['kind'] == 'execution' else [value.get('result', {})]
        sources = {False: source_digest}
        for row in rows:
            from validation import execution_definition
            check = (profile or {}).get('checks', {}).get(row.get('id'))
            if check is not None and row.get('binding', {}).get('definition') != execution_definition(check):
                return True
            sensitive = bool((profile or {}).get('checks', {}).get(row.get('id'), {}).get('revision_sensitive'))
            if sensitive not in sources:
                from validation import source
                sources[sensitive] = digest(source(root, profile, revision_sensitive=sensitive))
            if row.get('binding', {}).get('source') != sources[sensitive]:
                return True
        return False
    return value.get('source_digest') not in (None, source_digest)


def record_evidence(key, response):
    return (response.get('context' if key == 'prepare' else 'artifact') or response.get('artifact') or {}).get('path')


def recorded_steps(root, rows):
    """只按每一步最后一次请求的结果生成步骤记录。"""
    result = []
    for key, label, match in STEPS:
        last = next((row for row in reversed(rows) if match(row[0])), None)
        state, evidence = 'pending', None
        if last:
            claim, response = last
            if response and response.get('ok'):
                state, evidence = 'done', record_evidence(key, response)
            else:
                state = 'failed' if response else 'running-or-interrupted'
                evidence = (response or {}).get('request_directory') or claim.get('started_at')
        row = {'id': key, 'label': label, 'state': state, 'evidence': evidence}
        if state == 'done' and (_artifact_value(root, last[1]) or {}).get('tool', {}).get('override'):
            row['note'] = '使用了 --allow-modified-tool'
        result.append(row)
    return result


def steps(root, task, source_digest, context=None, task_arg=None, profile=None, current=None,
          task_identity=None, material_group=None, review_inputs=None):
    rows = records(root, task['id'])
    if current:
        rows = [(c, current[1] if c == current[0] else r) for c, r in rows]
    prepared = [c.get('started_at', '') for c, r in rows
                if c.get('command') in ('start', 'prepare') and r and not r.get('continued')
                and (_artifact_value(root, r) or {}).get('kind') == 'prepared-context']
    beginning = max(prepared, default='')
    active = [(c, r) for c, r in rows if STEPS[0][2](c) or c.get('started_at', '') >= beginning]
    selected, latest_done, paths = {}, {}, {}
    for key, label, match in STEPS:
        mine = [(c, r) for c, r in active if match(c)]
        done = [(c, r) for c, r in mine if r and r.get('ok')]
        trusted = [(c, r) for c, r in done if not (_artifact_value(root, r) or {}).get('tool', {}).get('override')]
        chosen = (trusted or done)[-1] if done else None
        if chosen:
            latest_done[key] = chosen[0].get('started_at', '')
            paths[key] = record_evidence(key, chosen[1])
        last = mine[-1] if mine else None
        if last and not (last[1] and last[1].get('ok')) and last[0].get('started_at', '') > latest_done.get(key, ''):
            chosen = last
        if chosen:
            selected[key] = chosen
    result = recorded_steps(root, list(selected.values()))
    for row in result:
        if row['id'] in selected:
            response = selected[row['id']][1]
            if row['state'] == 'done' and source_stale(root, _artifact_value(root, response), source_digest, profile):
                row['state'] = 'stale'
            if row['state'] == 'failed' and response.get('next_action'):
                from repairs import recorded_action
                claim = selected[row['id']][0]
                command_name = 'start' if claim['command'] == 'prepare' else claim['command']
                row['repair'] = recorded_action(root, task['id'], command_name, claim, response, material_group)
    for i, row in enumerate(result):
        later = [latest_done.get(other['id'], '') for other in result[i + 1:]]
        if row['state'] == 'failed' and later and max(later) > (rows_started(rows, STEPS[i][2]) or ''):
            row['state'] = 'superseded'
    import reviews
    import review_history
    review_state = None
    if profile is not None:
        editor = reviews._state(root, task['id'])
        draft_binding = read(artifact_valid(root, editor['current'])) if editor['current'] else None
        review_state = review_history.status(root, profile, task, editor, draft_binding, material_group, review_inputs)
        if review_state and review_state['review'] and not review_state['current']:
            row = next(row for row in result if row['id'] == 'review')
            row.update(state='stale', evidence=review_state['review']['path'], stale_reason='评审绑定已变化，需要逐项复核')
            paths['review'] = row['evidence']
    ctx = f'--context {context}' if context else f'--task {task_arg or "<task.json>"}'
    commands = {
        'prepare': f'tw team start --root "$PROJECT" {ctx}',
        'run': f'tw team run --root "$PROJECT" {ctx}',
        'review': f'tw team review --root "$PROJECT" {ctx} --run {paths.get("run") or "<run.json>"}',
        'acceptance': f'tw team accept --root "$PROJECT" {ctx} --run {paths.get("run") or "<run.json>"} --review {paths.get("review") or "<review.json>"} [--approval <approval.json>]',
        'knowledge': f'tw team delivery-template --root "$PROJECT" {ctx} --approval <approval.json> --run {paths.get("run") or "<run.json>"} --review <review.json> --acceptance {paths.get("acceptance") or "<acceptance.json>"}',
        'delivery': f'tw team verify --root "$PROJECT" {ctx} --report <delivery.json>',
    }
    if task_identity:
        selected = '--task ' + shlex.quote(task_identity)
        base = 'tw team {command} --root "$PROJECT" ' + selected
        commands = {key: base.format(command=command) for key, command in
                    [('prepare', 'start'), ('run', 'run'), ('review', 'review'),
                     ('acceptance', 'accept'), ('knowledge', 'delivery-template'), ('delivery', 'verify')]}
        if not (material_group or {}).get('review'):
            commands['acceptance'] += ' --review <review.json>'
        if not (material_group or {}).get('approvals'):
            commands['acceptance'] += ' [--approval <approval.json>]'
    if review_state and review_state['current']:
        selected = '--task ' + shlex.quote(task['id'])
        for key in ('acceptance', 'knowledge', 'delivery'):
            commands[key] = 'tw team deliver ' + selected + ' --reason <不需要更新知识的理由>'
    if reviews.locations(root, task['id'])[0].is_file() and (not review_state or review_state['draft_current']):
        commands['review'] = reviews.submission_action(root, task['id'])
    last_done = max((i for i, row in enumerate(result) if row['state'] == 'done'), default=-1)
    for i, row in enumerate(result):
        row['next_command'] = row.pop('repair', None) if row['state'] == 'failed' else None
        row['next_command'] = row['next_command'] or commands[row['id']]
        row.pop('repair', None)
        if row['state'] == 'superseded':
            row['state'] = 'not-recorded'
        if i < last_done and row['state'] == 'pending':
            row['state'] = 'not-recorded'  # done outside the tool (e.g. a hand-written review) or not needed
    urgent = [row for row in result if row['state'] in ('stale', 'running-or-interrupted', 'failed')]
    upcoming = urgent[0] if urgent else next((row for row in result[last_done + 1:] if row['state'] != 'done'), None)
    return {'steps': result, 'next_step': upcoming,
            'finished': upcoming is None}


def render(value):
    marks = {'done': '[x]', 'stale': '[!]', 'failed': '[x?]', 'running-or-interrupted': '[~]', 'pending': '[ ]',
             'not-recorded': '[-]'}
    words = {'done': '', 'stale': '（源码已变，需要重做）', 'failed': '（上次失败）',
             'running-or-interrupted': '（正在运行或被中断，换新的请求编号重试）', 'pending': '',
             'not-recorded': '（工具没有记录，可能已在工具外完成）'}
    lines = [f'{i}. {marks[row["state"]]} {row["label"]}' + (f'（{row["stale_reason"]}）' if row.get('stale_reason') else words[row['state']]) + ('（使用了被修改的工具安装）' if row.get('note') else '')
             for i, row in enumerate(value['steps'], 1)]
    for index, row in reversed(list(enumerate(value['steps']))):
        if row['id'] == 'scenarios':
            counts, rate = row['summary_counts'], row['first_pass']
            lines.insert(index + 1, '   当前汇总：' + '，'.join(key + ' ' + str(counts[key]) for key in counts)
                         + f'；一次通过率 {rate["numerator"]}/{rate["denominator"]}')
            if row.get('next_command'):
                lines.insert(index + 2, '   下一步：' + row['next_command'])
    if value['next_step']:
        lines += ['', '下一步：' + value['next_step']['label'], value['next_step']['next_command']]
    else:
        lines += ['', value.get('completion_summary', '已交付；关闭需要授权，工具不执行关闭')]
    return lines
