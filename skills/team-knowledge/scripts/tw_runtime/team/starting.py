"""Select a task's most recent prepared context and compare its actual preparation inputs."""
import design_files
import task_inputs
import repairs
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
    """Resolve acceptance through the same contract used by platform and direct commands."""
    return task_inputs.expand(task, design)


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
                '所选上下文的记录类型或版本与准备上下文不符', next_action=repairs.command(args, 'start'))
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
                '所选准备上下文属于另一个任务', next_action=repairs.command(args, 'start', '--design <方案文件>'))
        require(not previous_ref or previous_ref == explicit['context'],
                '所选准备上下文已被新上下文取代', next_action=repairs.command(args, 'start'))
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
    require(task is not None, '当前任务身份尚缺准备上下文', next_action=repairs.command(args, 'start', '--design <方案文件>'))
    design = (design_files.read(local(root, args.design)) if args.design else (platform or {}).get('design') or
              (read(artifact_valid(root, previous['design'])) if previous else None))
    if design is None:
        error = Invalid('；'.join((platform or {}).get('design_gaps', []))
                        or 'start needs --design <design.md> or a shared plan')
        error.next_action = (platform or {}).get('design_repair')
        raise error
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
    previous_inputs = (previous or {}).get('preparation_inputs') or {}
    design_path = explicit.get('design', {}).get('path') or previous_inputs.get('design_path')
    selected = signature(task, design, approvals, history, dependency_inputs, login['granted'], login['policy'])
    old = None
    if previous:
        old = previous.get('preparation_inputs') or signature(read(artifact_valid(root, previous['task'])), read(artifact_valid(root, previous['design'])),
                        _values(root, previous, 'approvals'), _values(root, previous, 'design_history'),
                        dependency_inputs, previous.get('authorizations', []), previous.get('login_policy', {}))
        # The original filename is navigation metadata, not a change to the prepared content.
        old = {key: value for key, value in old.items() if key != 'design_path'}
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
            'signature': selected, 'explicit': explicit, 'design_path': design_path}


def resolve_accept_context(args, root):
    from commands import local
    if args.context or not args.task:
        return
    supplied = read(local(root, args.task)) if (root / args.task).is_file() else None
    task_id = supplied['id'] if supplied else str(args.task)
    ref, context = latest_context(root, task_id)
    if ref is None and args.report and supplied:
        return  # Existing complete reports keep the original explicit-task entry.
    require(ref is not None, '业务验收尚缺本任务的准备上下文', next_action=repairs.command(args, 'start', '--design <方案文件>'))
    if supplied:
        captured = read(artifact_valid(root, context['task']))
        task_inputs.validate_written(supplied, local(root, args.task).relative_to(root).as_posix())
        same = supplied == task_inputs.written(captured)
        require(same, '任务内容与准备时的材料不同', next_action=repairs.command(args, 'start'))
    args.context = Path(ref['path'])
    args.task = None
