"""Explicit stage flow: platform stage records, read-only status and a sub-agent ledger.

Stage records are append-only issue comments, so moving between stages never edits
the requirement prose that handoffs and reviews fingerprint. Nothing here publishes.
"""
import json
import re
from pathlib import Path

from common import Invalid, digest, now, obj, read, require, strings, text, write
import github_read as github
import handoffs

STAGES = ('S0', 'S1', 'G1', 'S2', 'S3', 'G2', 'S4', 'G3')
USER_GATES = {'G1', 'G3'}
NEXT = {
    'S0': '校对资料与现状，产出差异清单后进入 S1',
    'S1': '用 to-spec 写方案与决策项，完成后进入 G1',
    'G1': '等待用户逐条确认决策项并认可方案',
    'S2': '用 to-tickets 拆子 Issue，每个带验收块后进入 S3',
    'S3': '逐个子任务实现并交接；命中硬暂停触发器时先停下确认',
    'G2': '逐个子任务运行 verify，补齐交接后关闭可关闭的子任务',
    'S4': '汇总验收；跨仓时运行 aggregate',
    'G3': '等待用户确认关闭父任务',
}
DECISION_STATUS = {'pending', 'confirmed'}
AGENT_STATUS = ('planned', 'running', 'completed', 'failed', 'interrupted', 'degraded')
LEDGER_NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')


def validate_decision(item):
    obj(item, {'id', 'question', 'options', 'recommended', 'default_if_unconfirmed', 'affects', 'status'}, {'answer'})
    for key in ('id', 'question', 'recommended', 'default_if_unconfirmed'):
        text(item[key])
    strings(item['options'], nonempty=True)
    strings(item['affects'])
    require(item['status'] in DECISION_STATUS, 'Decision status must be pending or confirmed')
    if item['status'] == 'confirmed':
        text(item.get('answer'))


def validate(row):
    obj(row, {'schema_version', 'kind', 'task', 'stage', 'children', 'decisions', 'note'}, {'confirmation'})
    require(row['schema_version'] == 1 and row['kind'] == 'stage', 'Expected stage record version 1')
    github.issue_ref(row['task'])
    require(row['stage'] in STAGES, 'Unknown stage: ' + str(row['stage']))
    strings(row['children'])
    require(len(set(row['children'])) == len(row['children']), 'Duplicate child issue')
    for child in row['children']:
        github.issue_ref(child)
        require(child != row['task'], 'A task cannot be its own child')
    require(isinstance(row['decisions'], list), 'Decisions must be a list')
    seen = set()
    for item in row['decisions']:
        validate_decision(item)
        require(item['id'] not in seen, 'Duplicate decision ID')
        seen.add(item['id'])
    text(row['note'])
    if 'confirmation' in row:
        text(row['confirmation'])


def transition(previous, row):
    """Forward one step at a time, any step back for revisions; leaving a user gate needs confirmation."""
    before = STAGES.index(previous['stage']) if previous else 0
    after = STAGES.index(row['stage'])
    require(after <= before + 1, f"Cannot skip from {previous['stage'] if previous else 'S0'} to {row['stage']}")
    gate = previous['stage'] if previous else None
    if gate in USER_GATES and after > before:
        require(bool(row.get('confirmation', '').strip()), f'Leaving {gate} needs the user confirmation reference')
    if gate == 'G1' and after > before:
        loose = [d['id'] for d in row['decisions'] if d['status'] == 'pending' and not d['affects']]
        require(not loose, 'Pending decisions without affected tasks block the whole plan: ' + ', '.join(loose))
    if row['stage'] == 'G3' or (gate == 'G3' and after > before):
        pending = [d['id'] for d in row['decisions'] if d['status'] == 'pending']
        require(not pending, 'Closing needs every decision confirmed: ' + ', '.join(pending))


def history(issue):
    records, gaps = [], []
    for comment in issue['comments_data']:
        try:
            row = handoffs.block(comment.get('body'), 'stage', required=False)
            if row is None:
                continue
            validate(row)
            require(row['task'] == issue['html_url'], 'Stage record belongs to another task')
            transition(records[-1]['record'] if records else None, row)
            records.append({'url': comment['html_url'], 'record': row, 'digest': digest(row)})
        except (Invalid, ValueError, KeyError, TypeError) as exc:
            gaps.append('Invalid stage record ' + comment.get('html_url', '?') + ': ' + str(exc))
    return records, gaps


def draft(url, change):
    """Produce the next stage comment; publishing remains with the user's authorization."""
    issue = github.issue(url)
    records, gaps = history(issue)
    require(not gaps, '; '.join(gaps) + '; reconcile stage history before advancing')
    current = records[-1]['record'] if records else None
    obj(change, {'stage', 'note'}, {'children', 'decisions', 'confirmation'})
    row = {'schema_version': 1, 'kind': 'stage', 'task': url, 'stage': change['stage'],
           'children': change.get('children', current['children'] if current else []),
           'decisions': change.get('decisions', current['decisions'] if current else []),
           'note': change['note']}
    if change.get('confirmation'):
        row['confirmation'] = change['confirmation']
    validate(row)
    transition(current, row)
    lines = [f"## 阶段 {row['stage']}", '', row['note'], '', '下一步：' + NEXT[row['stage']]]
    pending = [d for d in row['decisions'] if d['status'] == 'pending']
    if pending:
        lines += ['', '### 等你决定', '']
        for d in pending:
            lines.append(f"- **{d['id']}** {d['question']}｜选项：{' / '.join(d['options'])}｜推荐：{d['recommended']}"
                         f"｜不确认时：{d['default_if_unconfirmed']}｜影响：{', '.join(d['affects']) or '整体方案'}")
    body = '\n'.join(lines) + '\n\n```team-workflow-stage\n' + json.dumps(row, ensure_ascii=False, indent=2) + '\n```\n'
    return {'schema_version': 1, 'kind': 'stage-draft', 'ok': True, 'scope': 'platform-status', 'issue': url,
            'previous': records[-1]['url'] if records else None, 'record': row, 'markdown': body,
            'publication': 'draft-only; re-read the issue before an authorized append, then run status'}


def child_status(url, parent, pending):
    issue = github.issue(url)
    result = {'issue': url, 'state': issue.get('state'), 'owners': [a['login'] for a in issue.get('assignees', [])],
              'blocked_by': [], 'remaining': [], 'questions': [], 'verified': [], 'reasons': []}
    try:
        source = handoffs.task_source(issue)
    except (Invalid, ValueError, KeyError, TypeError) as exc:
        result['reasons'].append('没有有效的验收块：' + str(exc))
        result['closable'] = False
        return result
    if source['parent'] != parent:
        result['reasons'].append('子任务的 parent 不是当前父任务')
    acceptance = {row['id'] for row in source['task']['acceptance']}
    result['blocked_by'] = sorted(d['id'] for d in pending if url in d['affects'] or acceptance & set(d['affects']))
    latest, _, gaps = handoffs.chain(issue)
    result['reasons'] += gaps
    if latest is None:
        result['reasons'].append('没有可确认的交接记录')
    else:
        row = latest['record']
        result.update(remaining=row['remaining'], questions=row['questions'], verified=row['verified'])
        if row['requirements'] != digest(source):
            result['reasons'].append('交接基于旧的需求正文，需重新交接')
        if row['remaining']:
            result['reasons'].append('仍有剩余工作')
        if row['questions']:
            result['reasons'].append('仍有未决问题')
        if not row['verified']:
            result['reasons'].append('交接没有验证引用')
        _, waiting, progress_gaps = handoffs.pending_progress(issue, row)
        result['reasons'] += progress_gaps
        if waiting:
            result['reasons'].append('有尚未纳入交接的进度')
    if result['blocked_by']:
        result['reasons'].append('被待确认决策阻塞：' + ', '.join(result['blocked_by']))
    result['closable'] = not result['reasons']
    return result


def status(url):
    issue = github.issue(url)
    records, gaps = history(issue)
    current = records[-1]['record'] if records else None
    stage = current['stage'] if current else 'S0'
    if not records:
        gaps.append('尚未记录阶段；按 S0 处理')
    decisions = current['decisions'] if current else []
    pending = [d for d in decisions if d['status'] == 'pending']
    children = [child_status(child, url, pending) for child in (current['children'] if current else [])]
    waiting = []
    if stage in USER_GATES:
        waiting.append(f'确认 {stage}')
    waiting += [f"决策 {d['id']}：{d['question']}" for d in pending]
    reasons = []
    if stage not in ('S4', 'G3'):
        reasons.append(f'当前阶段 {stage} 尚未进入汇总验收')
    if not children:
        reasons.append('没有关联子任务')
    for child in children:
        if not child['closable']:
            reasons.append('子任务未满足关闭条件：' + child['issue'])
        elif child['state'] != 'closed':
            reasons.append('子任务可关闭但尚未关闭：' + child['issue'])
    if pending:
        reasons.append('仍有待确认决策')
    if gaps:
        reasons += gaps
    return {'schema_version': 1, 'kind': 'stage-status', 'ok': not gaps, 'scope': 'platform-status',
            'delivery': 'not-evaluated', 'issue': url, 'state': issue.get('state'), 'stage': stage,
            'next': NEXT[stage], 'waiting_for_user': waiting, 'decisions': decisions,
            'children': children, 'closable': not reasons, 'reasons': reasons,
            'local_checks': '子任务的 verify 与跨仓 aggregate 只能在本地核查；本结果只读取平台记录',
            'stage_history': [r['url'] for r in records], 'gaps': gaps}


def ledger_path(root, name):
    require(bool(LEDGER_NAME.fullmatch(text(name))), 'Ledger name must be a lowercase slug')
    return root / '.team-workflow' / 'agents' / name


def agents(root, name, plan=None, mark=None, state=None, reason=None):
    """Record sub-agent fan-out so a resumed session reuses results instead of spawning again."""
    directory = ledger_path(root, name)
    path = directory / 'ledger.json'
    if plan is not None:
        require(not path.exists(), 'Ledger already exists; list it and reuse completed results')
        require(isinstance(plan, list) and bool(plan), 'Plan must be a non-empty list')
        items, seen = [], set()
        for row in plan:
            obj(row, {'id', 'purpose'})
            require(bool(LEDGER_NAME.fullmatch(text(row['id']))), 'Agent ID must be a lowercase slug')
            require(row['id'] not in seen, 'Duplicate agent ID')
            seen.add(row['id'])
            items.append({'id': row['id'], 'purpose': text(row['purpose']), 'status': 'planned',
                          'output': (directory / (row['id'] + '.md')).relative_to(root).as_posix(),
                          'updated_at': now(), 'reason': '', 'history': []})
        directory.mkdir(parents=True, exist_ok=True)
        write(path, {'schema_version': 1, 'name': name, 'created_at': now(), 'items': items})
    require(path.exists(), 'No ledger: ' + name)
    data = read(path)
    if mark is not None:
        require(state in AGENT_STATUS, 'Status must be one of ' + ', '.join(AGENT_STATUS))
        item = next((row for row in data['items'] if row['id'] == mark), None)
        require(item is not None, 'Unknown agent ID: ' + str(mark))
        require(item['status'] != 'completed' or state == 'completed', 'A completed result is reused, not replaced')
        if state == 'completed':
            output = root / item['output']
            require(output.is_file() and output.stat().st_size > 0, 'Write the agent output before marking it completed: ' + item['output'])
        if state in ('failed', 'interrupted', 'degraded'):
            require(bool(reason and reason.strip()), state + ' needs --reason describing what is not covered')
        item.setdefault('history', []).append({'status': item['status'], 'reason': item['reason'], 'at': item['updated_at']})
        item.update(status=state, updated_at=now(), reason=reason or '')
        write(path, data)
    reuse, recover = [], []
    for item in data['items']:
        output = root / item['output']
        item['output_present'] = output.is_file() and output.stat().st_size > 0
        if item['status'] == 'completed':
            reuse.append(item['id'])
        elif item['status'] != 'degraded':
            recover.append(item['id'])
    return {'schema_version': 1, 'kind': 'agent-ledger', 'ok': True, 'ledger': path.relative_to(root).as_posix(),
            'items': data['items'], 'reuse': reuse, 'recover_serially': recover,
            'degraded': [i['id'] for i in data['items'] if i['status'] == 'degraded'],
            'recovered': [i['id'] for i in data['items'] if i['status'] == 'completed'
                          and any(h['status'] in ('failed', 'interrupted') for h in i.get('history', []))],
            'rule': '已完成的直接读取输出复用，不得重启；其余由当前代理串行补做或询问用户，不自动再次并发启动'}
