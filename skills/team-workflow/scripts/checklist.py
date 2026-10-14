"""Where a task stands and the exact next command, read from the requests the tool already recorded."""
from artifacts import directory
from common import Invalid, artifact_valid, digest, read

STEPS = [
    ('prepare', '准备任务与知识简报', lambda c: c.get('command') == 'prepare'),
    ('run', '运行检查', lambda c: c.get('command') == 'run'),
    ('review', '生成并完成代码与验收评审', lambda c: c.get('command') == 'review-template'),
    ('acceptance', '业务验收', lambda c: c.get('command') == 'verify' and c.get('phase') == 'acceptance'),
    ('knowledge-template', '生成知识回写草稿', lambda c: c.get('command') == 'knowledge-template'),
    ('knowledge', '核对 CS 已写入的知识（之前须在 CS 预览并应用）', lambda c: c.get('command') == 'knowledge'),
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
            sensitive = bool((profile or {}).get('checks', {}).get(row.get('id'), {}).get('revision_sensitive'))
            if sensitive not in sources:
                from validation import source
                sources[sensitive] = digest(source(root, profile, revision_sensitive=sensitive))
            if row.get('binding', {}).get('source') != sources[sensitive]:
                return True
        return False
    refs = ([value.get('acceptance')] if value.get('kind') == 'knowledge-completion' else
            value.get('task', {}).get('source', {}).get('workflow_acceptances', []))
    for ref in refs:
        try:
            acceptance = read(artifact_valid(root, {'path': ref['path'], 'sha256': ref['sha256']}))
            if acceptance.get('source_digest') != source_digest:
                return True
        except (Invalid, OSError, ValueError, KeyError, TypeError):
            return True
    return value.get('source_digest') not in (None, source_digest)


def steps(root, task, source_digest, context=None, task_arg=None, profile=None):
    rows = records(root, task['id'])
    result, previous_done = [], True
    paths = {}
    latest_done = {}
    for key, label, match in STEPS:
        mine = [(c, r) for c, r in rows if match(c)]
        done = [(c, r) for c, r in mine if r and r.get('ok')]
        # Prefer results produced by an unmodified tool installation.
        trusted = [(c, r) for c, r in done if not (_artifact_value(root, r) or {}).get('tool', {}).get('override')]
        state, evidence = 'pending', None
        if done:
            claim, response = (trusted or done)[-1]
            latest_done[key] = claim.get('started_at', '')
            evidence = (response.get('artifact') or {}).get('path')
            paths[key] = evidence
            value = _artifact_value(root, response)
            stale = source_stale(root, value, source_digest, profile)
            state = 'stale' if stale else 'done-with-override' if not trusted else 'done'
        last = mine[-1] if mine else None
        if last and not (last[1] and last[1].get('ok')) and last[0].get('started_at', '') > latest_done.get(key, ''):
            # The newest attempt did not finish well; earlier success no longer describes the current state.
            state = 'running-or-interrupted' if not last[1] else 'failed'
            evidence = (last[1] or {}).get('request_directory') or last[0].get('started_at')
        result.append({'id': key, 'label': label, 'state': state, 'evidence': evidence})
    # A later step that succeeded after an earlier failure shows that failure was superseded.
    for i, row in enumerate(result):
        later = [latest_done.get(other['id'], '') for other in result[i + 1:]]
        if row['state'] == 'failed' and later and max(later) > (rows_started(rows, STEPS[i][2]) or ''):
            row['state'] = 'superseded'
    for row in result:
        if row['state'] == 'done-with-override':
            row['state'] = 'done'
            row['note'] = 'produced with --allow-modified-tool'
    ctx = f'--context {context}' if context else f'--task {task_arg or "<task.json>"}'
    commands = {
        'prepare': f'python3 "$WF" prepare --root "$PROJECT" {ctx} --cs-skill "$CS_SKILL"',
        'run': f'python3 "$WF" run --root "$PROJECT" {ctx}',
        'review': f'python3 "$WF" review-template --root "$PROJECT" {ctx} --run {paths.get("run") or "<run.json>"}',
        'acceptance': f'python3 "$WF" verify --root "$PROJECT" {ctx} --report <delivery.json> --phase acceptance --cs-skill "$CS_SKILL"',
        'knowledge-template': f'python3 "$WF" knowledge-template --root "$PROJECT" {ctx} --acceptance {paths.get("acceptance") or "<acceptance.json>"} --cs-skill "$CS_SKILL"',
        'knowledge': f'python3 "$WF" knowledge --root "$PROJECT" {ctx} --acceptance {paths.get("acceptance") or "<acceptance.json>"} --brief <brief.json> --cs-task-id <CS 任务编号> --disposition <none|reused|updated|added> --reason "<实际处置>" --cs-skill "$CS_SKILL"',
        'delivery': (f'python3 "$WF" delivery-template --root "$PROJECT" {ctx} --approval <approval.json> --run {paths.get("run") or "<run.json>"} '
                     f'--review <review.json> --knowledge {paths.get("knowledge") or "<knowledge.json>"}\n'
                     f'python3 "$WF" verify --root "$PROJECT" {ctx} --report <上一条命令输出的 delivery.json> --cs-skill "$CS_SKILL"'),
    }
    last_done = max((i for i, row in enumerate(result) if row['state'] == 'done'), default=-1)
    for i, row in enumerate(result):
        row['next_command'] = commands[row['id']]
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
    lines = [f'{i}. {marks[row["state"]]} {row["label"]}{words[row["state"]]}' + ('（使用了被修改的工具安装）' if row.get('note') else '')
             for i, row in enumerate(value['steps'], 1)]
    if value['next_step']:
        lines += ['', '下一步：' + value['next_step']['label'], value['next_step']['next_command']]
    else:
        lines += ['', '所有工具步骤已完成。GitHub Issue 任务按结果发布收尾说明或交接，并在有关闭授权后关闭；'
                      '本地任务按团队约定交付。']
    return lines
