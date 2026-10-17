"""Sequential composition of the existing acceptance, report, and final verification commands."""
import copy
import repairs
import hashlib
import shlex

from common import Invalid, artifact_valid, digest, read, require, write
import delivery
import knowledge
import materials
from error_codes import Code


def platform_task(root, task_id):
    from tw_runtime.team import platform_script
    return platform_script.is_task(root, task_id, required=False)


def child_args(args, task_id, command, request_id=None):
    child = copy.copy(args)
    child.command, child.task, child.issue = command, task_id, None
    child.submit, child.from_platform, child.file = False, command == 'review', None
    for key in ('context', 'design', 'brief', 'review', 'report', 'acceptance', 'out'):
        setattr(child, key, None)
    for key in ('approval', 'design_history', 'run', 'dependency', 'with_task'):
        setattr(child, key, [])
    child.context = (getattr(args, 'material_selection', None) or {}).get('explicit', {}).get('context')
    child.request_id = request_id
    child.reason = args.reason if command == 'delivery-template' else None
    if hasattr(child, 'material_selection'):
        del child.material_selection
    return child


def current_report(args, root, task, include_knowledge=False, *, workspace=None):
    from commands import report_input
    current = child_args(args, task['id'], 'delivery-template')
    materials.resolve(current, root, workspace=workspace)
    return report_input(current, root, task, include_knowledge=include_knowledge)


def usable_acceptance(args, root, profile, task, group, *, workspace=None):
    if not group.get('acceptance'):
        return None
    try:
        accepted = read(artifact_valid(root, group['acceptance']))
        if not (accepted.get('kind') == 'acceptance' and accepted.get('business_accepted') is True):
            return None
        report = current_report(args, root, task, workspace=workspace)
        report.pop('acceptance', None)
        checked = delivery.verify(root, profile, task, report, 'acceptance', live=False, workspace=workspace)
        keys = ('task_id', 'task_digest', 'source_digest', 'sections')
        if all(accepted.get(key) == checked.get(key) for key in keys) and delivery.contents(accepted.get('materials')) == delivery.contents(checked['materials']):
            return {'ok': True, 'artifact': group['acceptance'], 'business_accepted': True,
                    'summary_markdown': accepted.get('summary_markdown', '')}
    except (Invalid, OSError, ValueError, TypeError, KeyError):
        pass  # The ordinary accept command records the precise reason if reuse is impossible.
    return None


def usable_report(args, root, task, group, *, workspace=None):
    if not group.get('delivery_report'):
        return None
    try:
        report = read(artifact_valid(root, group['delivery_report']))
        expected = current_report(args, root, task, include_knowledge=True, workspace=workspace)
        for key in ('task_id', 'design', 'approvals', 'design_history', 'brief', 'runs', 'review', 'acceptance', 'dependencies'):
            if report.get(key) != expected.get(key):
                return None
        knowledge.verify(root, report.get('knowledge'), task['base'])
        if args.reason is not None and report['knowledge'].get('reason') != args.reason:
            return None
        return {'ok': True, 'artifact': group['delivery_report']}
    except (Invalid, OSError, ValueError, TypeError, KeyError):
        return None


def validate_retry(root, task, cached):
    if not cached.get('ok'):
        return
    group = materials.load(root, task['id']) or {}
    expected = {'review': 'review', 'acceptance': 'acceptance', 'delivery-report': 'delivery_report', 'delivery': 'delivery'}
    for step in cached.get('steps', []):
        role = expected[step['step']]
        old, current = step['result'].get('artifact'), group.get(role)
        require(old is not None and current is not None and old['sha256'] == current['sha256'],
                'Request ID already belongs to different inputs; use a new request ID', error_code=Code.REQUEST_CONFLICT)


def deliver(args, root, profile, task, request, *, workspace=None):
    import commands
    steps = []
    task_arg = '--task ' + shlex.quote(task['id'])

    def execute(command, step):
        key = hashlib.sha256((request.directory.name + ':' + step).encode('utf-8')).hexdigest()[:32]
        child = child_args(args, task['id'], command, 'deliver-' + key)
        try:
            return commands.dispatch(child, root, workspace=workspace)
        except Exception as exc:
            # Material/platform preconditions can fail before dispatch creates its request.
            # Retain that step's diagnosis as well as the sequence's stopping point.
            from artifacts import Request
            from cleanup import guard
            from tw_runtime import Invalid as RuntimeInvalid
            if isinstance(exc, (RuntimeInvalid, OSError, ValueError, TypeError, KeyError)):
                import repairs
                result = repairs.failure(child, exc)
            else:
                result = commands.tool_defect(exc)
            with guard(root):
                failed = Request(root, task['id'], {'command': command, 'task': digest(task),
                                 'parent_request': request.directory.name, 'precondition_failure': result},
                                 'deliver-error-' + key)
            return failed.cached if failed.cached is not None else failed.finish(result)

    def append(step, result, reused=False):
        steps.append({'step': step, 'reused': reused, 'result': result})

    def finish(result=None, stopped=None, problem=None):
        result = result or {}
        value = {'ok': stopped is None, 'kind': 'delivery-sequence', 'steps': steps, 'stopped_at': stopped,
                 'business_accepted': any(row['step'] == 'acceptance' and row['result'].get('ok') for row in steps),
                 'delivery_complete': bool(result.get('delivery_complete')) if not stopped else False,
                 'closable': bool(result.get('closable')) if not stopped else False,
                 'summary_markdown': result.get('summary_markdown', ''),
                 'summary': ('交付停在' + {'review': '平台评审', 'acceptance': '业务验收', 'delivery-report': '交付报告',
                              'delivery': '最终核查'}[stopped] + '。') if stopped else ''}
        for key in ('ci_verified_checks', 'unverified_scope', 'close_note', 'acceptance_scope', 'scope', 'automation_status', 'regression_pending', 'summary_counts', 'statistics', 'scenario_rounds', 'scenario_files'):
            if key in result:
                value[key] = result[key]
        from summary import delivery_status
        value.update(delivery_status(value))
        if stopped:
            value['problem'] = problem or result.get('problem', '本步骤尚未完成。')
            for key in ('error_code', 'review_failures', 'review_file', 'scenario_states'):
                if key in result:
                    value[key] = result[key]
            if stopped == 'delivery-report':
                command = 'tw team deliver ' + task_arg + ' --reason <不需要更新知识的理由>'
            elif stopped == 'review':
                command = 'tw team review ' + task_arg + ' --from-platform'
            elif stopped == 'acceptance':
                if result.get('error_code') in (Code.SOURCE_STALE, Code.RUN_BINDING_STALE):
                    command = 'tw team run ' + task_arg
                else:
                    command = reviews.submission_action(root, task['id'])
            else:
                command = 'tw team verify ' + task_arg
            if result.get('next_action') and not result.get('ok'):
                command = result['next_action']
            value.update(next_action=command, next_step={'id': stopped, 'next_command': command})
        value['artifact'] = request.publish('deliver.json', value, args.out)
        return value

    group = materials.load(root, task['id'])
    require(group is not None, '当前任务尚缺开工材料组',
            next_action=repairs.command(args, 'start', '--design <方案文件>'))
    # An interrupted deliver continues with the reason it was given; an explicit new reason replaces it.
    pending = materials.path(root, task['id']).parent / 'deliver-reason.json'
    if args.reason is None and pending.is_file():
        args.reason = read(pending).get('reason')
    elif args.reason is not None:
        write(pending, {'data_version': 1, 'kind': 'pending-delivery-reason', 'task_id': task['id'], 'reason': args.reason})
    import reviews
    if (profile.get('platform') and platform_task(root, task['id'])
            and reviews.platform_is_newer(root, task['id'], group.get('review'))):
        reviewed = execute('review', 'review')
        append('review', reviewed)
        if not reviewed.get('ok'):
            return finish(reviewed, 'review')
        group = materials.load(root, task['id'])
    accepted = usable_acceptance(args, root, profile, task, group, workspace=workspace)
    reused = accepted is not None
    accepted = accepted or execute('accept', 'acceptance')
    append('acceptance', accepted, reused)
    if not accepted.get('ok'):
        return finish(accepted, 'acceptance')

    group = materials.load(root, task['id'])
    report = usable_report(args, root, task, group, workspace=workspace)
    reused = report is not None
    report = report or execute('delivery-template', 'delivery-report')
    append('delivery-report', report, reused)
    if not report.get('ok'):
        return finish(report, 'delivery-report')
    try:
        value = read(artifact_valid(root, report['artifact']))
        knowledge.disposition(value.get('knowledge'))
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        return finish(accepted, 'delivery-report', str(exc))

    result = execute('verify', 'delivery')
    append('delivery', result)
    if result.get('ok'):
        pending.unlink(missing_ok=True)
    return finish(result, None if result.get('ok') else 'delivery')
