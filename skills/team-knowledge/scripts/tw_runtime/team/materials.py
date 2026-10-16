"""One explicit, content-bound material group per task; no latest-file inference."""
from error_codes import Code
import design_files
from tw_runtime.team import platform_script as platform_read
import copy
import hashlib
import json
from pathlib import Path
import shlex

from artifacts import directory
from common import Invalid, artifact, artifact_valid, digest, inside, load_profile, obj, read, sha, write

COMMANDS = {'start', 'run', 'status', 'review', 'approval-draft', 'accept', 'delivery-template', 'deliver',
            'verify', 'handoff', 'progress', 'task-export'}
SINGLE = ('context', 'task', 'design', 'brief', 'review', 'acceptance', 'delivery_report', 'delivery')
OPTIONAL = ('review_markdown', 'review_source')
OPTIONAL_ARRAY = ('case_imports', 'scenario_rounds')
OPTIONAL_SCENARIOS = ('case_coverage',)
ARRAY = ('design_history', 'approvals', 'runs')
OPTIONS = {'context': 'context', 'design': 'design', 'brief': 'brief', 'design_history': 'design_history',
           'approvals': 'approval', 'runs': 'run', 'review': 'review', 'acceptance': 'acceptance',
           'delivery_report': 'report'}
RUN_INPUTS = {'status', 'review', 'approval-draft', 'accept', 'delivery-template', 'deliver'}
LABELS = {'context': '准备上下文', 'task': '任务', 'design': '方案', 'brief': '简报',
          'design_history': '方案历史', 'approvals': '批准', 'runs': '运行', 'review': '评审',
          'acceptance': '业务验收记录', 'delivery_report': '交付报告', 'delivery': '最终交付记录',
          'current': '当前材料组', 'review_markdown': '评审 Markdown 原文', 'review_source': '被评审源码的逐文件指纹'}


class MaterialGap(Invalid):
    error_code = Code.CURRENT_MATERIALS

    def __init__(self, role, detail, task_id, *, next_action=None):
        option = OPTIONS.get(role)
        repair = ('显式指定 --' + option.replace('_', '-') + ' <材料路径>，或' if option else '')
        self.next_action = repair + '重新开工：tw team start --task <任务文件> --design <方案文件>'
        if str(task_id).startswith(('http://', 'https://')):
            self.next_action += '；平台任务用 tw team start --issue ' + shlex.quote(task_id)
        super().__init__(f'{LABELS.get(role, role)}（{role}）{detail}。', next_action=next_action)


def path(root, task_id):
    return directory(root, task_id).parent.parent / 'current.json'


def load(root, task_id):
    return load_snapshot(root, task_id)[0]


def load_snapshot(root, task_id):
    """Read value and CAS token from the same inode, even when another writer renames current.json."""
    target = path(root, task_id)
    try:
        payload = target.read_bytes()
    except FileNotFoundError:
        return None, None
    try:
        value = json.loads(payload.decode('utf-8'))
        obj(value, {'data_version', 'kind', 'task_id', *SINGLE, *ARRAY}, {'platform', 'selected_runs', *OPTIONAL, *OPTIONAL_ARRAY, *OPTIONAL_SCENARIOS})
        if type(value['data_version']) is not int or value['data_version'] != 1 or value['kind'] != 'current-materials' or value['task_id'] != task_id:
            raise Invalid('记录类型、版本或任务身份不符')
        for key in ARRAY + OPTIONAL_ARRAY:
            if not isinstance(value.get(key, []), list):
                raise Invalid(key + ' 必须是列表')
        return value, hashlib.sha256(payload).hexdigest()
    except (Invalid, OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise MaterialGap('current', str(exc), task_id) from exc


def checked(root, ref, role, task_id):
    try:
        return artifact_valid(root, ref)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        raise MaterialGap(role, '缺失或指纹不符：' + str(exc), task_id) from exc


def validate(root, value, replaced=()):
    replaced = set(replaced)
    if 'review' in replaced:
        replaced.update(OPTIONAL)
    for key in SINGLE + OPTIONAL + OPTIONAL_SCENARIOS + ARRAY + OPTIONAL_ARRAY:
        if key in replaced:
            continue
        refs = value.get(key, []) if key in ARRAY + OPTIONAL_ARRAY else [value[key]] if value.get(key) is not None else []
        for ref in refs:
            checked(root, ref, key, value['task_id'])
    if value.get('selected_runs') is not None and 'runs' not in replaced:
        if not isinstance(value['selected_runs'], list):
            raise MaterialGap('runs', '选用运行必须是列表', value['task_id'])
        for ref in value['selected_runs']:
            checked(root, ref, 'runs', value['task_id'])


def platform_signature(value):
    return {'design': digest(value['design']), 'approvals': [digest(v) for v in value['approvals']]}


def resolve(args, root):
    """Resolve only roles consumed by this command; publication never fingerprints its own output."""
    if args.command not in COMMANDS:
        return None
    from commands import local
    explicit = {key: copy.deepcopy(getattr(args, key)) for key in
                ('context', 'design', 'brief', 'approval', 'design_history', 'run', 'review', 'acceptance', 'report')
                if getattr(args, key)}
    file_task = args.task is not None and (root / args.task).is_file()
    supplied = read(local(root, args.task)) if file_task else None
    context = read(local(root, args.context)) if args.context else None
    context_task = read(checked(root, context['task'], 'task', str(args.task or args.issue or ''))) if context else None
    identity = args.task is not None and not file_task
    task_id = args.issue or (supplied or {}).get('id') or (str(args.task) if identity else None) or (context_task or {}).get('id')
    if not task_id:
        return None
    if context_task and context_task['id'] != task_id:
        raise MaterialGap('context', '属于另一个任务，不能跨任务复用', task_id)
    value, token = load_snapshot(root, task_id)
    snapshot = {'task_id': task_id, 'value': value, 'token': token,
                'explicit': explicit, 'identity': identity, 'repair': False}
    args.material_selection = snapshot
    if platform_read.is_task(root, task_id):
        args.issue = task_id
    if args.command == 'start':
        if value:
            replaced = {key for key, option in OPTIONS.items() if option in explicit}
            if file_task:
                replaced.add('task')
            try:
                validate(root, value, replaced)
            except MaterialGap:
                if not (file_task and args.design or args.issue):
                    raise
                snapshot['repair'] = True
        return snapshot
    if value is None:
        if identity:
            raise MaterialGap('current', '不存在；该身份尚未 start', task_id)
        return snapshot  # Complete explicit paths retain the pre-existing interface.

    replaced = {key for key, option in OPTIONS.items() if option in explicit}
    supplied_report = read(local(root, args.report)) if args.report and args.command in {'accept', 'verify', 'status'} else None
    if supplied_report:
        for key, field in [('design', 'design'), ('brief', 'brief'), ('approvals', 'approvals'),
                           ('design_history', 'design_history'), ('runs', 'runs'), ('review', 'review'), ('acceptance', 'acceptance')]:
            if field in supplied_report:
                replaced.add(key)
    switched = bool(explicit.get('context') and artifact(root, local(root, args.context)) != value['context'])
    defaults = initial(root, task_id, artifact(root, local(root, args.context)), previous=value) if switched else value
    snapshot.update(effective=defaults, context_switched=switched)
    snapshot['stale_roles'] = []
    validate(root, defaults, replaced)
    if args.command == 'status' and args.design and defaults.get('design'):
        if digest(design_files.read(local(root, args.design))) != digest(design_files.read(checked(root, defaults['design'], 'design', task_id))):
            snapshot['stale_roles'].append('design')
    if not value['context']:
        raise MaterialGap('context', '不存在；请先 start', task_id)
    if file_task:
        captured = read(checked(root, defaults['task'], 'task', task_id))
        import task_inputs
        task_inputs.validate_written(supplied, local(root, args.task).relative_to(root).as_posix())
        same = supplied == task_inputs.written(captured)
        if not same:
            raise MaterialGap('task', '内容已改变，须重新 start', task_id)
    # Use the normalized, complete task captured by start, even if its input still has ID-only acceptance rows.
    args.task = Path(checked(root, defaults['task'], 'task', task_id))
    args.context = args.context or Path(value['context']['path'])
    for key, option in OPTIONS.items():
        if option in explicit or key in {'context', 'delivery_report'}:
            continue
        if key == 'runs' and args.command not in RUN_INPUTS:
            continue
        if key == 'review' and args.command not in {'status', 'accept', 'delivery-template', 'deliver'}:
            continue
        if key == 'acceptance' and args.command != 'delivery-template':
            continue
        refs = defaults.get('selected_runs') if key == 'runs' and defaults.get('selected_runs') is not None else defaults[key]
        if key in ARRAY:
            setattr(args, option, [Path(ref['path']) for ref in refs])
        elif refs:
            setattr(args, option, Path(refs['path']))
    if not args.report and args.command == 'verify' and defaults['delivery_report']:
        args.report = Path(defaults['delivery_report']['path'])
    if supplied_report:
        for option, field in [('design', 'design'), ('brief', 'brief'), ('approval', 'approvals'),
                              ('design_history', 'design_history'), ('run', 'runs'), ('review', 'review')]:
            if option not in explicit and field in supplied_report:
                raw = supplied_report[field]
                setattr(args, option, [Path(v) for v in raw] if isinstance(raw, list) else Path(raw) if raw else None)
    if platform_read.is_task(root, task_id):
        import coordination
        try:
            platform = coordination.load(task_id, root=root)
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            raise MaterialGap('current', '无法核对平台材料：' + str(exc), task_id) from exc
        stored = defaults.get('platform') or {'design': digest(design_files.read(root / defaults['design']['path'])),
                                             'approvals': [digest(read(root / ref['path'])) for ref in defaults['approvals']]}
        fresh = platform_signature(platform)
        for role in ('design', 'approvals'):
            if fresh[role] != stored[role]:
                if args.command == 'status':
                    snapshot['stale_roles'].append(role)
                else:
                    raise MaterialGap(role, '平台材料比记录更新，须重新 start', task_id)
        selected_design = design_files.read(local(root, args.design)) if args.design else None
        if selected_design != platform['design']:
            if args.command == 'status':
                snapshot['stale_roles'].append('design')
            else:
                raise MaterialGap('design', '所选方案与平台当前方案不同，不能用显式旧材料覆盖', task_id)
        if 'approval' in explicit or supplied_report and 'approvals' in supplied_report:
            selected_approvals = [read(local(root, p)) for p in args.approval]
            published = None
            if defaults.get('review') and any(row not in platform['approvals'] for row in selected_approvals):
                import reviews
                published = reviews.published_approval(root, task_id, read(checked(root, defaults['review'], 'review', task_id)))
            if any(row not in platform['approvals'] and row != published for row in selected_approvals) and args.command != 'status':
                raise MaterialGap('approvals', '所选批准未在平台当前材料中登记', task_id)
            import designs
            status = designs.approval_status(selected_design, selected_approvals,
                root=root, profile=load_profile(root),
                history=[design_files.read(local(root, p)) for p in args.design_history],
                section_ids=read(args.task)['section_ids'], changed_paths=[])
            if set(status['stale']) & set(status['required_sections']) and args.command != 'status':
                raise MaterialGap('approvals', '所选批准已过期，不能覆盖平台当前批准', task_id)
        args.issue = task_id
    return snapshot


def fingerprint(args, root):
    """The resolved roles enter the same request fingerprint as explicit files."""
    from commands import local
    if not getattr(args, 'material_selection', None) or args.command == 'start':
        return None
    result = {'context': artifact(root, local(root, args.context))} if args.context else {}
    selection = args.material_selection
    value = selection.get('effective') or selection.get('value') or {}
    result['scenarios'] = {key: value.get(key) for key in OPTIONAL_ARRAY + OPTIONAL_SCENARIOS}
    if getattr(args, 'design', None):
        from scenario_acceptance import bindings, current
        from common import load_profile
        design = design_files.read(local(root, args.design))
        task = read(local(root, args.task))
        result['scenario_bindings'] = bindings(current(root, load_profile(root), task, design)[1])
    if args.command == 'review' and not args.submit:
        import reviews
        result['review_history'] = reviews.history_inputs(root, selection['task_id'], selection.get('effective') or selection['value'])
    if args.command == 'verify' and selection['value']:
        value = selection.get('effective') or selection['value']
        group = {key: value[key] for key in ('task', 'design', 'brief', 'approvals', 'design_history', 'review', 'acceptance')}
        group['runs'] = value.get('selected_runs') if value.get('selected_runs') is not None else value['runs']
        if 'report' in selection['explicit']:
            report = read(local(root, args.report))
            for key in ('design', 'brief', 'review', 'acceptance'):
                group[key] = artifact(root, local(root, report[key])) if report.get(key) else None
            for key in ('approvals', 'design_history', 'runs'):
                group[key] = [artifact(root, local(root, p)) for p in report.get(key, [])]
        result['group'] = group
    return result


def initial(root, task_id, context_ref, platform=None, *, previous=None):
    context = read(checked(root, context_ref, 'context', task_id))
    value = {'data_version': 1, 'kind': 'current-materials', 'task_id': task_id, 'selected_runs': None,
             'review_markdown': None,
             'review_source': None,
             **{key: None for key in SINGLE}, **{key: [] for key in ARRAY}}
    value.update(context=context_ref, **{key: context[key] for key in ('task', 'design', 'brief', 'approvals', 'design_history')})
    if platform:
        value['platform'] = platform_signature(platform)
    if previous:
        value.update({key: previous[key] for key in OPTIONAL_ARRAY + OPTIONAL_SCENARIOS if key in previous})
    return value


def report_matches(args, root, report):
    """An automatically selected report cannot silently choose an older group than current.json."""
    selection = getattr(args, 'material_selection', None)
    if not selection or not selection['value'] or 'report' in selection['explicit']:
        return
    value = selection.get('effective') or selection['value']
    for key, field in [('design', 'design'), ('brief', 'brief'), ('approvals', 'approvals'),
                       ('design_history', 'design_history'), ('runs', 'runs'), ('review', 'review'), ('acceptance', 'acceptance')]:
        refs = value.get('selected_runs') if key == 'runs' and value.get('selected_runs') is not None else value[key]
        expected = [r['path'] for r in refs] if key in ARRAY else refs['path'] if refs else None
        if report.get(field, [] if key in ARRAY else None) != expected:
            raise MaterialGap('delivery_report', '引用的 ' + key + ' 与当前组不同', value['task_id'],
                              next_action='按当前材料生成交付报告：tw team delivery-template --task ' + shlex.quote(value['task_id']))


def select_runs(value, refs):
    for ref in refs:
        if ref not in value['runs']:
            value['runs'].append(ref)
    value['selected_runs'] = refs


def select_review(root, value, ref, approval=None):
    """评审携带自己的合并批准；方案批准继续保留。"""
    from checklist import records
    previous = value.get('review')
    if previous != ref:
        for _, response in records(root, value['task_id']):
            if response and response.get('artifact') == previous and response.get('review_submitted'):
                old = response.get('approval')
                value['approvals'] = [item for item in value['approvals'] if item != old]
        value['review_markdown'] = None
        value['review_source'] = None
    if approval is None:
        approval = next((response.get('approval') for _, response in records(root, value['task_id'])
                         if response and response.get('artifact') == ref and response.get('review_submitted')), None)
    value['review'] = ref
    if approval and approval not in value['approvals']:
        value['approvals'].append(approval)


def apply_explicit(args, root, value):
    from commands import local
    explicit = args.material_selection['explicit']
    for key, option in OPTIONS.items():
        if option not in explicit or key in {'context', 'delivery_report'}:
            continue
        raw = getattr(args, option)
        refs = [artifact(root, local(root, v)) for v in raw] if key in ARRAY else artifact(root, local(root, raw))
        if key == 'runs':
            select_runs(value, refs)
        elif key == 'review':
            select_review(root, value, refs)
        else:
            value[key] = refs


def capture_report(root, value, report):
    from commands import local
    for key, field in [('design', 'design'), ('brief', 'brief'), ('acceptance', 'acceptance')]:
        if report.get(field):
            ref = artifact(root, local(root, report[field]))
            value[key] = ref
    for key in ('approvals', 'design_history'):
        value[key] = [artifact(root, local(root, p)) for p in report.get(key, [])]
    if report.get('review'):
        select_review(root, value, artifact(root, local(root, report['review'])))
    select_runs(value, [artifact(root, local(root, p)) for p in report['runs']])


def effective_report(args, root, report):
    """Explicit per-role paths take precedence over the same role inside a supplied report."""
    from commands import local
    result = copy.deepcopy(report)
    explicit = (getattr(args, 'material_selection', None) or {}).get('explicit', {})
    for option, field in [('design', 'design'), ('brief', 'brief'), ('approval', 'approvals'),
                          ('design_history', 'design_history'), ('run', 'runs'), ('review', 'review'), ('acceptance', 'acceptance')]:
        if option in explicit:
            raw = getattr(args, option)
            result[field] = [local(root, p).relative_to(root).as_posix() for p in raw] if isinstance(raw, list) else local(root, raw).relative_to(root).as_posix()
    return result


def record_status(args, root, result):
    selection = getattr(args, 'material_selection', None)
    if (not selection or not selection['value'] or not selection['explicit'] or not result.get('ok', True)
            or selection.get('stale_roles')):
        return result
    from cleanup import guard
    from commands import local

    with guard(root):
        target = path(root, selection['task_id'])
        if sha(target) != selection['token']:
            raise MaterialGap('current', '并发更新改变了材料组，重新查看状态后再指定材料', selection['task_id'])
        updated = copy.deepcopy(selection.get('effective') or selection['value'])
        apply_explicit(args, root, updated)
        if 'report' in selection['explicit']:
            capture_report(root, updated, effective_report(args, root, read(local(root, args.report))))
            updated['delivery_report'] = artifact(root, local(root, args.report))
        validate(root, updated)
        if updated != selection['value']:
            write(target, updated)
    return result


def finish(args, root, task, result, request):
    """CAS for start, merge concurrent runs, and publish under the cleanup maintenance lock."""
    selection = getattr(args, 'material_selection', None)
    if not selection or not (result.get('ok') or args.command == 'run' and result.get('artifact')):
        return request.finish(result)
    from cleanup import guard
    from commands import local
    def finish_start():
        if args.command == 'start':
            from commands import current_status
            progress = current_status(root, task['id'], (read(request.directory / 'request.json'), result))
            for key in ('steps', 'next_step', 'step_lines', 'pending_sections'):
                if key in progress:
                    result[key] = progress[key]
            if result.get('ok') and not result.get('validation_active'):
                result['next_action'] = progress['next_action']
        return request.finish(result)

    with guard(root):
        target = path(root, task['id'])
        latest, token = load_snapshot(root, task['id'])
        if args.command == 'start':
            if token != selection['token']:
                raise MaterialGap('current', '另一个 start 同时改变了材料组，本次未写入；换请求编号重试', task['id'])
            if result['continued'] and latest:
                return finish_start()
            updated = initial(root, task['id'], result['context'], args.start_selection['platform'], previous=latest)
        elif latest:
            if latest['context'] != selection['value']['context']:
                raise MaterialGap('context', '另一个 start 已取代本次上下文，请重新 start', task['id'])
            if token != selection['token'] and (args.command != 'run' or selection.get('context_switched')):
                raise MaterialGap('current', '并发更新改变了材料组，本次未写入；换请求编号重试', task['id'])
            updated = copy.deepcopy(selection['effective'] if selection.get('context_switched') else latest)
            apply_explicit(args, root, updated)
            if args.command == 'run':
                if result['artifact'] not in updated['runs']:
                    updated['runs'].append(result['artifact'])
                updated['selected_runs'] = None
            elif args.command == 'review' and result.get('review_submitted'):
                select_review(root, updated, result['artifact'], result.get('approval'))
                updated['review_markdown'] = result['review_markdown']
                updated['review_source'] = result['review_source']
                if result.get('approval'):
                    select_runs(updated, result['approval_runs'])
            elif args.command == 'accept':
                accepted = read(root / result['artifact']['path'])
                report = accepted['report']
                capture_report(root, updated, report)
                updated['acceptance'] = result['artifact']
            elif args.command == 'delivery-template':
                updated['delivery_report'] = result['artifact']
                if args.acceptance:
                    updated['acceptance'] = artifact(root, local(root, args.acceptance))
            elif args.command == 'verify':
                capture_report(root, updated, read(root / result['artifact']['path'])['report'])
                updated['delivery_report'] = artifact(root, local(root, args.report))
                updated['delivery'] = result['artifact']
        else:
            return request.finish(result)  # Legacy explicit operations do not invent a prepared context.
        validate(root, updated)
        if updated == latest:
            return request.finish(result)
        editor_before = None
        try:
            if args.command == 'review' and result.get('review_submitted'):
                import reviews
                editor_path = reviews.locations(root, task['id'])[1]
                editor_before = read(editor_path)
                reviews.mark_submitted(root, task['id'], result)
            write(target, updated)
            return finish_start()
        except BaseException:
            if editor_before is not None:
                write(editor_path, editor_before)
            if latest is None:
                target.unlink(missing_ok=True)
            else:
                write(target, latest)
            raise
