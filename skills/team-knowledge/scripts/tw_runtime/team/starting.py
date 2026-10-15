"""Select a task's most recent prepared context and compare its actual preparation inputs."""
import design_files
import copy
from pathlib import Path

from common import Invalid, artifact, artifact_valid, digest, read, require


def latest_context(root, task_id):
    import materials
    current = materials.load(root, task_id)
    if current and current['context']:
        ref = current['context']
        return ref, read(materials.checked(root, ref, 'context', task_id))
    return None, None


def fill_acceptance(task, design):
    """Only local start inputs may omit acceptance text; explicit values remain subject to validation."""
    result = copy.deepcopy(task)
    sections = {row['id']: row for row in design['sections']}
    for row in result.get('acceptance', []):
        if not isinstance(row, dict):
            continue  # The ordinary task validator names invalid rows.
        section = sections.get(row.get('id'), {})
        if 'expectation' not in row or 'checks' not in row:
            require(section.get('type') == 'acceptance',
                    'Missing acceptance section: ' + str(row.get('id')) + '; check --design and run tw team start')
            row.setdefault('expectation', section['body'])
            row.setdefault('checks', copy.deepcopy(section['data']['checks']))
    return result


def _values(root, context, key):
    return [read(artifact_valid(root, ref)) for ref in context.get(key, [])]


def signature(task, design, approvals, history, dependencies, authorizations, login_policy):
    return {'task': digest(task), 'design': digest(design), 'approvals': [digest(v) for v in approvals],
            'history': [digest(v) for v in history], 'dependencies': dependencies,
            'authorizations': [{k: v for k, v in row.items() if k != 'at'} for row in authorizations],
            'login_policy': login_policy}


def select(args, root, profile):
    from commands import local, login_policy
    import coordination
    # Retain exactly the caller's files for request retries, independent of auto-selected copies.
    explicit = {key: artifact(root, local(root, value)) for key in ('design', 'context', 'report')
                if (value := getattr(args, key)) is not None}
    file_task = args.task and (root / args.task).is_file()
    supplied_task = read(local(root, args.task)) if file_task else None
    supplied_context = read(local(root, args.context)) if args.context else None
    context_task = None
    if supplied_context:
        require(supplied_context.get('data_version') == 1 and supplied_context.get('kind') == 'prepared-context',
                'Expected a prepared context; run tw team start --task <task.json>')
        context_task = read(artifact_valid(root, supplied_context['task']))
    task_id = (args.issue or (supplied_task or {}).get('id') or
               (str(args.task) if args.task and not file_task else None) or (context_task or {}).get('id'))
    require(bool(task_id), 'start needs --task <task.json or identity>, --issue <URL>, or --context <context.json>')
    selection = getattr(args, 'material_selection', None)
    current = selection['value'] if selection else None
    previous_ref, previous = None, None
    if current and current['context']:
        previous_ref = current['context']
        try:
            from materials import checked
            previous = read(checked(root, previous_ref, 'context', task_id))
        except Invalid:
            if not selection['repair']:
                raise
    if supplied_context:
        require(context_task['id'] == task_id,
                'Context belongs to another task; run tw team start --task <task.json> --design <design.md> for this task')
        require(not previous_ref or previous_ref == explicit['context'],
                'This context was superseded; run tw team start --task ' + task_id)
        previous_ref, previous = explicit['context'], supplied_context
    platform, platform_gap = None, None
    if args.issue:
        try:
            platform = coordination.load(args.issue, root=root)
        except coordination.MissingTaskBlock:
            raise
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            require(previous is not None, 'Cannot read platform task: ' + str(exc))
            platform_gap = 'Cannot read platform task: ' + str(exc)
    task = supplied_task or (platform or {}).get('task') or (
        read(artifact_valid(root, previous['task'])) if previous else None)
    require(task is not None, 'No prepared context for this identity; run tw team start --task <task.json> --design <design.md>')
    design = (design_files.read(local(root, args.design)) if args.design else (platform or {}).get('design') or
              (read(artifact_valid(root, previous['design'])) if previous else None))
    require(design is not None, 'start needs --design <design.md> or a shared plan')
    # A platform task block is always fully specified and is never generated locally.
    if not args.issue:
        task = fill_acceptance(task, design)
    approvals = ([read(local(root, p)) for p in args.approval] if args.approval else
                 platform['approvals'] if platform else _values(root, previous or {}, 'approvals'))
    history = ([design_files.read(local(root, p)) for p in args.design_history] if args.design_history else
               platform['history'] if platform else _values(root, previous or {}, 'design_history'))
    dependencies = ([read(local(root, p)) for p in args.dependency] if args.dependency else
                    (previous or {}).get('dependencies', []))
    login = login_policy(profile, args)
    if not args.grant and previous and previous.get('login_policy') == login['policy']:
        login['granted'] = previous.get('authorizations', [])
        if login['granted']:
            login['needed'] = []
    dependency_inputs = [{'input': value, 'task': artifact(root, local(root, value['task'])),
                          'report': artifact(root, local(root, value['report']))} for value in dependencies]
    selected = signature(task, design, approvals, history, dependency_inputs, login['granted'], login['policy'])
    old = None
    if previous:
        old = previous.get('preparation_inputs') or signature(read(artifact_valid(root, previous['task'])), read(artifact_valid(root, previous['design'])),
                        _values(root, previous, 'approvals'), _values(root, previous, 'design_history'),
                        dependency_inputs, previous.get('authorizations', []), previous.get('login_policy', {}))
    continued = previous is not None and selected == old and not (selection and selection['repair'])
    require(not platform_gap or continued, platform_gap or '')
    args.context = Path(previous_ref['path']) if continued else None
    if not args.issue:
        # Reuse already captured local material when no replacement was supplied.
        if args.design is None and previous:
            args.design = artifact_valid(root, previous['design'])
        if not args.approval and previous:
            args.approval = [artifact_valid(root, r) for r in previous['approvals']]
        if not args.design_history and previous:
            args.design_history = [artifact_valid(root, r) for r in previous['design_history']]
    if not file_task:
        args.task = None
    return {'task': task, 'platform': platform, 'platform_gap': platform_gap, 'design': design,
            'approvals': approvals, 'history': history, 'dependencies': dependencies, 'login': login,
            'continued': continued, 'previous_ref': previous_ref, 'previous': previous,
            'signature': selected, 'explicit': explicit}


def resolve_accept_context(args, root):
    from commands import local
    if args.context or not args.task:
        return
    supplied = read(local(root, args.task)) if (root / args.task).is_file() else None
    task_id = supplied['id'] if supplied else str(args.task)
    ref, context = latest_context(root, task_id)
    if ref is None and args.report and supplied:
        return  # Existing complete reports keep the original explicit-task entry.
    require(ref is not None, 'accept needs a prepared context; run tw team start --task <task.json> --design <design.md>')
    if supplied:
        captured = read(artifact_valid(root, context['task']))
        # The original file may still contain ID-only rows; every explicitly supplied field must agree.
        rows = captured['acceptance']
        same = (dict(supplied, acceptance=rows) == captured and
                isinstance(supplied.get('acceptance'), list) and len(supplied['acceptance']) == len(rows) and
                all(isinstance(row, dict) and row.get('id') == saved['id']
                    and all(key in saved and saved[key] == value for key, value in row.items())
                    for row, saved in zip(supplied['acceptance'], rows)))
        require(same, 'Task content changed since preparation; run tw team start with this task file before acceptance')
    args.context = Path(ref['path'])
    args.task = None
