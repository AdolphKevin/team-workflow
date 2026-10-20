"""Local, read-only run statistics for the weekly review. Nothing leaves the machine."""
from datetime import datetime

from checklist import records


def _seconds(claim, response):
    if response and isinstance(response.get('seconds'), (int, float)):
        return response['seconds']
    try:
        return (datetime.fromisoformat(response['finished_at']) - datetime.fromisoformat(claim['started_at'])).total_seconds()
    except (TypeError, KeyError, ValueError):
        return None


def task_metrics(root, task_id, since=None, *, workspace=None):
    rows = [(c, r) for c, r in records(root, task_id) if not since or c.get('started_at', '') >= since]
    by_command, check_runs, total = {}, {}, 0.0
    for claim, response in rows:
        name = claim.get('command') or 'unknown'
        if claim.get('phase') and name == 'verify':
            name = 'verify:' + claim['phase']
        entry = by_command.setdefault(name, {'requests': 0, 'failed': 0, 'unfinished': 0, 'seconds': 0.0})
        entry['requests'] += 1
        if response is None:
            entry['unfinished'] += 1
        elif not response.get('ok'):
            entry['failed'] += 1
        seconds = _seconds(claim, response)
        if seconds is not None:
            entry['seconds'] = round(entry['seconds'] + seconds, 3)
            total += seconds
        for check in (response or {}).get('checks', []) if name == 'run' else []:
            if isinstance(check, dict) and check.get('id'):
                row = check_runs.setdefault(check['id'], {'runs': 0, 'passed': 0})
                row['runs'] += 1
                row['passed'] += check.get('status') == 'passed'
    started = rows[0][0].get('started_at') if rows else None
    finished = [r.get('finished_at') for c, r in rows if r and c.get('command') == 'verify'
                and c.get('phase') == 'delivery' and r.get('ok')]
    result = {'task_id': task_id, 'requests': len(rows), 'commands': by_command,
            'checks': {k: {**v, 'reruns': max(v['runs'] - 1, 0)} for k, v in sorted(check_runs.items())},
            'tool_seconds': round(total, 3), 'first_request_at': started,
            'delivered_at': finished[-1] if finished else None}
    import materials
    group = materials.load(root, task_id)
    if group:
        from common import load_profile
        import scenario_rounds
        result['scenarios'] = scenario_rounds.task_metrics(root, load_profile(root), group, since, workspace=workspace)
    return result


def render(value):
    lines = [f'任务 {value["task_id"]}：{value["requests"]} 次工具请求，工具耗时约 {round(value["tool_seconds"] / 60, 1)} 分钟']
    for name, row in sorted(value['commands'].items()):
        lines.append(f'- {name}：{row["requests"]} 次，失败 {row["failed"]}，未完成 {row["unfinished"]}，耗时 {round(row["seconds"])} 秒')
    for name, row in value['checks'].items():
        if row['reruns']:
            lines.append(f'- 检查 {name} 运行 {row["runs"]} 次（重跑 {row["reruns"]} 次）')
    if value.get('scenarios'):
        scenarios = value['scenarios']
        first = scenarios['statistics']['first_pass']
        lines.append(f'- 场景一次通过率：{first["numerator"]}/{first["denominator"]}')
        for row in scenarios['rounds']:
            count = row['statistics']
            lines.append(f'- 第 {row["round"]} 轮：执行 {count["executed"]}，pass {count["pass"]}，fail {count["fail"]}，'
                         f'blocked {count["blocked"]}，skip {count["skip"]}，沿用 {count.get("carry", 0)}；'
                         f'通过率 {row["pass_rate"]["numerator"]}/{row["pass_rate"]["denominator"]}')
    return lines
