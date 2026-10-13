"""Sub-agent ledger: a resumed session reuses completed results instead of spawning again."""
import re

from common import now, obj, read, require, text, write

AGENT_STATUS = ('planned', 'running', 'completed', 'failed', 'interrupted', 'degraded')
LEDGER_NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')


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
