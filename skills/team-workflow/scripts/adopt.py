"""Bring a project onto the current tool: stamp the profile and name evidence that needs one re-run.

Evidence written before schema 6 is never rewritten (its hashes are referenced elsewhere); it stays
readable for history and cleanup, and the affected checks are run once more with the current tool.
"""
import json

from common import LEGACY_RECORD_SCHEMA, RECORD_SCHEMA, VERSION, inside, profile_valid, read, require

EVIDENCE = {'execution', 'imported-execution', 'portable-execution', 'acceptance', 'delivery-verification',
            'knowledge-brief', 'knowledge-completion', 'review', 'prepared-context'}
SCAN_LIMIT = 16 * 1024 * 1024


def legacy_evidence(root):
    runtime = root / '.team-workflow'
    rows, unreadable = [], []
    for path in sorted(runtime.rglob('*.json')) if runtime.is_dir() else []:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > SCAN_LIMIT:
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            unreadable.append(path.relative_to(root).as_posix())
            continue
        if isinstance(value, dict) and value.get('schema_version') == LEGACY_RECORD_SCHEMA and value.get('kind') in EVIDENCE:
            rows.append({'path': path.relative_to(root).as_posix(), 'kind': value['kind'],
                         'task_id': value.get('task_id') or ', '.join(sorted(value.get('tasks', {}))) or None})
    tasks = {}
    for row in rows:
        tasks.setdefault(row['task_id'] or '(shared execution)', []).append(row['path'])
    return rows, tasks, unreadable


def plan(root, profile_path):
    raw = read(inside(root, profile_path))
    require(isinstance(raw, dict) and raw.get('schema_version') == 5, 'adopt supports schema_version 5 project configurations')
    profile_valid(raw, root)
    changes = []
    if raw.get('workflow_version') != VERSION:
        changes.append({'field': 'workflow_version', 'from': raw.get('workflow_version'), 'to': VERSION,
                        'why': 'Older team-workflow installations then ask to be updated instead of misreading new records'})
    rows, tasks, unreadable = legacy_evidence(root)
    by_kind = {}
    for row in rows:
        by_kind[row['kind']] = by_kind.get(row['kind'], 0) + 1
    return {'ok': True, 'kind': 'adopt-plan', 'read_only': True, 'tool': VERSION, 'record_schema': RECORD_SCHEMA,
            'profile': {'path': profile_path, 'changes': changes},
            'legacy_evidence': {'count': len(rows), 'by_kind': by_kind, 'tasks': tasks, 'unreadable': unreadable},
            'summary': (f'配置需更新 {len(changes)} 项；' if changes else '配置已是当前版本；')
                       + (f'{len(tasks)} 个任务有旧版证据（{len(rows)} 份），需用当前工具重新运行检查一次并重新验收。'
                          if rows else '没有需要重跑的旧版证据。'),
            'next_action': ('Review, then run adopt --apply to update the configuration and commit it yourself. '
                            if changes else '') + ('For each listed task: run its checks, regenerate the review and '
                                                   'delivery report, then verify --phase acceptance again. Old files stay as history.'
                                                   if rows else '')}


def apply(root, profile_path):
    preview = plan(root, profile_path)
    path = inside(root, profile_path)
    raw = read(path)
    for change in preview['profile']['changes']:
        raw[change['field']] = change['to']
    profile_valid(raw, root)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = preview['legacy_evidence']['count']
    return {**preview, 'read_only': False, 'kind': 'adopt-result', 'applied': preview['profile']['changes'],
            'next_action': ('Commit the updated configuration yourself. ' + (
                'For each listed task: run its checks, regenerate the review and delivery report, then verify again.'
                if rows else '')).strip(),
            'summary': f'已更新配置 {len(preview["profile"]["changes"])} 项（未提交）。' + preview['summary'].split('；', 1)[-1]}
