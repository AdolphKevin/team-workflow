"""Command composition for the workflow CLI."""
import design_files
import json
from error_codes import Code, check_error_code
import shlex
import copy
import repairs
import task_inputs
from pathlib import Path

from common import (RECORD_SCHEMA, Invalid, artifact, artifact_valid, digest, evidence_file, inside, location_settings, now,
                    load_profile, read, require, skill_resource, task_valid)
import knowledge
import validation
from tw_runtime import Invalid as RuntimeInvalid
from tw_runtime.brief import relative_paths

def local(root, value):
    require(value is not None, 'Missing input path')
    path = Path(value)
    if path.is_absolute():
        path = path.resolve()
        require(path.is_relative_to(root), 'Input must be inside the project')
        path = path.relative_to(root)
    return inside(root, path.as_posix())


def readable_fields(value, indent=''):
    if isinstance(value, dict):
        rows = value.items()
    elif isinstance(value, list):
        rows = (('-', item) for item in value)
    else:
        return [indent + str(value)]
    lines = []
    for key, item in rows:
        if isinstance(item, (dict, list)):
            lines += [indent + key + '：', *readable_fields(item, indent + '  ')]
        else:
            lines.append(indent + ('- ' if key == '-' else key + '：') + str(item))
    return lines


def readable(result):
    lines = [result.get('summary') or result.get('status') or ('命令已完成；验收状态见下方' if result.get('ok', True) else '尚未完成')]
    for key in ('problem', 'next_action'):
        if key == 'next_action' and result.get('step_lines'):
            continue
        if result.get(key) and str(result[key]) not in lines:
            lines.append(('下一步：' if key == 'next_action' else '') + str(result[key]))
    if result.get('error_code') == Code.TOOL_DEFECT:
        if result.get('request_directory'):
            lines.append('请求目录：' + result['request_directory'])
        lines += ['调用位置：' + frame for frame in result.get('traceback', [])]
    for warning in result.get('warnings', []):
        lines.append('提示：' + str(warning))
    for gap in result.get('gaps', []):
        lines.append('- ' + str(gap))
    if result.get('verification_gaps'):
        lines += ['', '验收无法满足：'] + ['- ' + gap for gap in result['verification_gaps']] + ['']
    for key in ('artifact', 'task', 'design', 'brief'):
        item = result.get(key)
        if isinstance(item, dict) and item.get('path'):
            lines.append(key + ': ' + item['path'])
    if result.get('pr_description') is not None:
        lines += ['--- PR 描述草稿 ---', result['pr_description']]
    if result.get('checks_markdown'):
        lines += ['', result['checks_markdown']]
    if result.get('markdown'):
        lines += ['--- 发布评论草稿 ---', result['markdown']]
    if result.get('next_steps'):
        lines += ['', *[f'{index}. {step}' for index, step in enumerate(result['next_steps'], 1)]]
    if result.get('summary_markdown'):
        lines += ['', result['summary_markdown']]
    for role, ref in result.get('verified_records', {}).items():
        lines.append({'acceptance': '已核实的业务验收记录', 'delivery': '已核实的交付记录'}[role] + '：' + ref['path'])
    if result.get('publication'):
        row = result['publication']
        lines.append(row['summary'] + ('：' + row['url'] if row.get('url') else '') if isinstance(row, dict) else str(row))
    for row in result.get('review_failures', []):
        lines.append('- ' + row['id'] + '：' + row['reason'])
    if result.get('knowledge_next_action'):
        lines.append(result['knowledge_next_action'])
    if result.get('review_file'):
        lines.append('评审文件：' + result['review_file'])
    if result.get('archived_draft'):
        lines.append('原草稿已保留：' + result['archived_draft']['path'])
    if result.get('progress'):
        lines.append('已填写：{completed}/{total}'.format(**result['progress']))
    if result.get('close_note'):
        lines += ['--- 收尾说明草稿（原样发布到 Issue）---', result['close_note']['markdown']]
    lines += [line for line in result.get('step_lines', []) if line != result.get('summary')] + result.get('lines', [])
    if 'pending_count' in result and 'pending' in result:
        from scenario_rounds import pending_lines
        lines += pending_lines(result['pending'], result['summary_counts'])
    for row in result.get('authorizations_needed', []):
        if row['question'] not in result.get('next_action', ''):
            lines.append(row['question'])
    for name, path in result.get('templates', {}).items():
        lines.append('模板 ' + name + ': ' + path)
    for target in result.get('targets', []):
        lines.append(f"{target.get('action')}: {target['path']}" + (f" ({target['reason']})" if target.get('reason') else ''))
    if result.get('reference'):
        lines.append('字段说明: ' + result['reference'])
    if result.get('pending_sections'):
        import designs
        lines += ['', '待确认章节：'] + [designs.section_label(row) + '：' + row['reason'] for row in result['pending_sections']]
    pending = set(result.get('missing', [])) | set(result.get('stale', []))
    pending &= set(result.get('required_sections', pending))
    if pending and 'pending_sections' not in result:
        lines.append('待确认章节：' + '、'.join(sorted(pending)))
    labels = {'needs-review': '方案待评审', 'pending-decision': '有待定业务问题', 'unassigned': '未指派实施者',
              'waiting-for-tasks': '等待前置任务验收', 'scope-unknown': '尚未声明范围', 'needs-history': '缺少方案历史'}
    for name, value in result.get('tasks', {}).items():
        if not value.get('ready'):
            lines.append('任务 ' + name + '：' + labels.get(value.get('state'), str(value.get('state'))))
    if result.get('checks'):
        lines += ['检查：', *readable_fields(result['checks'])]
    for key in ('implementation_ready', 'business_accepted', 'delivery_complete', 'overall_complete', 'regression_pending', 'closable'):
        if key in result:
            lines.append(key + ': ' + str(result[key]))
    if isinstance(result.get('automation_status'), dict):
        from summary import regression_lines
        lines += ['回归待沉淀：' + line for line in regression_lines(result)]
    return '\n'.join(lines)


def references(root, values):
    return [local(root, p).relative_to(root).as_posix() for p in values]


def report_input(args, root, task, include_knowledge=True):
    for name in ('design', 'brief'):
        require(getattr(args, name) is not None, '所需材料尚待指定：--' + name,
                error_code={'design': Code.DESIGN_INPUT, 'brief': Code.BRIEF_INPUT}[name],
                next_action=('补齐方案后重新开工：' + repairs.command(args, 'start', '--design <方案文件>')
                             if name == 'design' else None))
    result = {'data_version': RECORD_SCHEMA, 'task_id': task['id'], 'design': local(root, args.design).relative_to(root).as_posix(),
              'approvals': references(root, args.approval), 'design_history': references(root, args.design_history),
              'brief': local(root, args.brief).relative_to(root).as_posix(), 'runs': references(root, args.run),
              'review': local(root, args.review).relative_to(root).as_posix() if args.review else ''}
    if getattr(args, 'acceptance', None):
        result['acceptance'] = local(root, args.acceptance).relative_to(root).as_posix()
    if include_knowledge:
        result['knowledge'] = knowledge.template(root, task)
    if args.dependency:
        result['dependencies'] = [read(local(root, p)) for p in args.dependency]
    elif args.context:
        dependencies = read(local(root, args.context)).get('dependencies', [])
        if dependencies:
            result['dependencies'] = dependencies
    return result


def predecessor_checks(args, root, profile, task, design, dependencies=None, *, workspace=None):
    """Explicit preparation/hand-off checks may revalidate predecessor evidence."""
    import delivery
    import designs
    completed, proofs = [], []
    hashes = designs.fingerprints(design)['sections']
    for value in dependencies if dependencies is not None else [read(local(root, path)) for path in args.dependency]:
        require(set(value) == {'section', 'task', 'report'}, 'Dependency needs section, task and report paths',
                error_code=Code.TASK_INPUT, next_action='修正 --dependency 指向的前置任务材料，再重试原命令。')
        dependency = read(local(root, value['task']))
        require(value['section'] in dependency['section_ids'] and dependency['design_id'] == task['design_id'],
                'Predecessor evidence belongs to another task section')
        proof = delivery.verify(root, profile, dependency, read(local(root, value['report'])), phase='acceptance', workspace=workspace)
        require(proof['sections'][value['section']] == hashes.get(value['section']), 'Predecessor plan changed')
        completed.append(value['section'])
        proofs.append({'section': value['section'], 'acceptance': proof})
    return completed, proofs


def cached_predecessors(args, root, profile, *, workspace=None):
    """Only continuation readiness uses a prepared observation; delivery always rechecks."""
    if not args.context:
        return []
    from common import artifact_valid
    completed = []
    for ref in read(local(root, args.context)).get('predecessors', []):
        value = read(artifact_valid(root, ref))
        proof = value['acceptance']
        require(proof.get('kind') == 'acceptance' and proof.get('business_accepted') is True,
                'Prepared predecessor was not accepted')
        require(proof['source_digest'] == validation.source_digest(root, profile, workspace=workspace), '前置任务的源码与当前源码不同',
                next_action=repairs.command(args, 'start'))
        for item in proof['materials']:
            artifact_valid(root, item)
        completed.append(value['section'])
    return completed


APPROVAL_RECOVERY_LABELS = {Code.APPROVAL_COMMIT: '补齐批准提交', Code.APPROVAL_SOURCE: '修正批准源码链接',
                            Code.DESIGN_HISTORY: '补齐方案历史'}


def approval_recovery(args, value, status):
    code = status.get('error_code')
    if code not in APPROVAL_RECOVERY_LABELS:
        return False
    value.update(error_code=code, next_action=repairs.action(args, error_code=code))
    if value.get('next_step'):
        value['next_step'].update(label=APPROVAL_RECOVERY_LABELS[code], next_command=value['next_action'])
    return True


def dispatch(args, root, *, workspace=None):
    if args.command == 'review' and args.from_platform:
        require(not args.file, '--from-platform 不能与本地 --file 混用')
        args.submit = True
    if args.command == 'schema':
        directory = skill_resource('templates')
        return {'ok': True, 'summary': '统一项目数据格式与字段说明',
                'templates': {p.stem: str(p) for p in sorted(directory.glob('*')) if p.suffix == '.json' or p.name in {'design.md', 'scenarios.yaml'}},
                'reference': str(skill_resource('references/contracts.md')),
                'data_version': RECORD_SCHEMA,
                'next_action': 'Read the installed template and replace every placeholder.'}
    completed = recorded_command(args, root)
    if completed is not None:
        return completed
    if args.command == 'scenarios':
        import scenarios
        return scenarios.dispatch(args, root, load_profile(root), workspace=workspace)
    if args.command == 'project':
        return project_report(root, args.home)
    if args.command == 'cleanup':
        import cleanup
        require(not (args.apply and args.dry_run), 'Choose cleanup preview or apply')
        return (cleanup.apply(root, read(args.plan)) if args.apply
                else cleanup.preview(root, args.cleanup_scope, args.older_than))
    if args.command == 'aggregate':
        import portable
        mappings = {key: (root / Path(path).expanduser()).resolve() for key, path in location_settings(root)['repositories'].items()}
        return portable.aggregate(root, read(local(root, args.joint)), mappings)
    from tw_runtime.team import platform_script as platform_read
    # Validate caller paths before materials.resolve replaces them with tool-owned snapshots.
    for path in ([args.design] if args.design else []) + list(args.design_history):
        design_files.read(local(root, path), internal=False, workspace=workspace)
    if args.command == 'design-draft' and args.record:
        design_files.read(local(root, args.record), internal=False, workspace=workspace)
    candidate = args.issue or (str(args.task) if args.task else None)
    if candidate:
        platform_read.is_task(root, candidate)
    profile = load_profile(root)
    workspace = workspace or validation.Workspace(root, profile)
    task_files = ([args.task] if args.task and (root / args.task).is_file() else []) + list(args.with_task)
    for value in task_files:
        path = local(root, value)
        task_inputs.validate_written(read(path), path.relative_to(root).as_posix())
    import materials
    materials.resolve(args, root, workspace=workspace)
    start = None
    if args.command == 'start':
        import starting
        import coordination
        try:
            start = starting.select(args, root, profile)
        except coordination.MissingTaskBlock as exc:
            return missing_task_block(args, exc)
        args.start_selection = start
    elif args.command == 'accept' and not (getattr(args, 'material_selection', None) or {}).get('value'):
        import starting
        starting.resolve_accept_context(args, root)
    if args.context:
        from common import artifact_valid
        context = read(local(root, args.context))
        require(context.get('data_version') == RECORD_SCHEMA and context.get('kind') == 'prepared-context',
                f'准备上下文需要采用数据版本 {RECORD_SCHEMA}',
                next_action=repairs.command(args, 'start'))
        for key in ('task', 'design', 'brief'):
            if getattr(args, key) is None:
                setattr(args, key, artifact_valid(root, context[key]))
        if not args.approval:
            args.approval = [artifact_valid(root, r) for r in context['approvals']]
        if not args.design_history:
            args.design_history = [artifact_valid(root, r) for r in context['design_history']]
    if args.command == 'metrics':
        import metrics
        from artifacts import directory
        task_ids = [(read(local(root, args.task))['id'] if (root / args.task).is_file() else str(args.task))] if args.task else [args.issue] if args.issue else sorted(
            {read(p).get('task_id') for p in (root / '.tw/local/tasks').glob('*/requests/*/request.json')} - {None})
        rows = [metrics.task_metrics(root, task_id, args.since, workspace=workspace) for task_id in task_ids]
        return {'ok': True, 'kind': 'workflow-metrics', 'read_only': True, 'metrics': rows,
                'summary': f'{len(rows)} 个任务的本机运行统计；只辅助复盘，不是质量结论。',
                'lines': [line for row in rows for line in metrics.render(row)]}
    if args.command == 'issue-draft':
        import issue_draft
        require(bool(args.task), 'issue-draft needs --task (the structured task for the issue)')
        return issue_draft.draft(root, profile, read(local(root, args.task)),
                                 design_files.read(local(root, args.design), workspace=workspace) if args.design else None,
                                 [read(local(root, p)) for p in args.with_task], args.reviewer,
                                 design_path=local(root, args.design) if args.design else None)
    platform = start['platform'] if start else None
    if args.issue and start is None:
        import coordination
        try:
            platform = coordination.load(args.issue, root=root)
        except coordination.MissingTaskBlock as exc:
            return missing_task_block(args, exc)
    task = start['task'] if start else read(local(root, args.task)) if args.task else platform['task'] if platform else None
    if args.command == 'evidence':
        from common import external_path
        refs = []
        for name in args.path:
            if args.evidence_repository:
                values = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == args.evidence_repository]
                require(len(values) == 1, 'Evidence repository must be declared')
                target = external_path(root, args.evidence_repository, values[0])
                path = evidence_file(inside(target, name), args.allow_large_evidence)
                refs.append({'repository': args.evidence_repository, **artifact(target, path)})
            else:
                refs.append(artifact(root, evidence_file(local(root, name), args.allow_large_evidence)))
            if args.allow_large_evidence:
                refs[-1]['allow_large_evidence'] = True
        return {'ok': True, 'artifacts': refs}
    if args.command == 'import-result':
        import portable
        from artifacts import Request
        from cleanup import guard
        locator_path = local(root, args.result)
        inputs = {'command': 'import-result', 'locator': artifact(root, locator_path),
                  'profile': digest(profile), 'source': validation.source_digest(root, profile, workspace=workspace),
                  'options': {'allow_modified_tool': args.allow_modified_tool}}
        with guard(root):
            request = Request(root, 'imports:' + profile['project'], inputs, args.request_id)
        if request.cached is not None:
            return request.cached
        try:
            path, record = portable.import_result(root, profile, read(locator_path), request.directory / 'import', workspace=workspace)
            ref = request.publish('import.json', record, args.out) if args.out else artifact(root, path)
            return request.finish({'ok': True, 'artifact': ref, 'scope': 'execution-only'})
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            code = getattr(exc, 'error_code', Code.INVALID)
            return request.finish(repairs.annotate(args, {'ok': False, 'problem': str(exc),
                                   'error_code': code if code != Code.INVALID else Code.IMPORT_INCOMPLETE,
                                   'next_action': getattr(exc, 'next_action', None) or
                                       'Inspect provider identity and original reports; retry with a new request ID.'}))
    require(task is not None and task.get('data_version') == 1, 'This operation requires a data_version 1 task')
    selected_design = (start['design'] if start else design_files.read(local(root, args.design), workspace=workspace) if args.design else
                       design_files.read(local(root, args.record), workspace=workspace) if args.command == 'design-draft' and args.record else
                       platform['design'] if platform else None)
    if selected_design is None and args.report:
        report = read(local(root, args.report))
        if report.get('design'):
            selected_design = design_files.read(local(root, report['design']), workspace=workspace)
    if selected_design is not None:
        task = task_inputs.expand(task, selected_design)
    if args.command != 'status' or task_phase(platform) != 'closed':
        task_valid(task, profile, root, written=selected_design is None and 'expectation' not in task['acceptance'][0])
    if platform:
        if args.command == 'status' and task_inputs.written(platform['task']) != task_inputs.written(task):
            args.material_selection.setdefault('stale_roles', []).append('task')
        else:
            require(task_inputs.written(platform['task']) == task_inputs.written(task), 'Local task differs from platform requirements')
    if args.command == 'status':
        value = status(args, root, profile, task, platform, workspace=workspace)
        from validation_session import active
        running = active(root)
        value['validation_active'] = running
        if running and value['task_phase'] != 'closed':
            value.update(implementation_ready=False,
                         summary='共享目录正在执行验收检查；源码和生成输入须保持不变。',
                         next_action='Wait for the active validation to finish before editing or changing checkouts.')
        return materials.record_status(args, root, value)
    if args.command == 'snapshot':
        return {'ok': True, 'source_digest': validation.source_digest(root, profile, workspace=workspace), 'task_digest': digest(task)}
    from artifacts import Request
    if args.command == 'review' and args.submit:
        import reviews
        if args.from_platform:
            args.platform_review = reviews.platform_source(root, task['id'])
        reviews.exclude_own_approval(args, root, task['id'])
    input_files = {}
    for name in ('task', 'design', 'brief', 'review', 'report', 'progress', 'record', 'acceptance'):
        value = getattr(args, name, None)
        if value:
            input_files[name] = artifact(root, local(root, value))
    query_paths = relative_paths(root, args.path)
    inputs = {'command': args.command, 'phase': args.phase, 'task': digest(task), 'profile': digest(profile),
              'files': input_files, 'source': validation.source_digest(root, profile, workspace=workspace),
              'approvals': [artifact(root, local(root, p)) for p in args.approval],
              'history': [artifact(root, local(root, p)) for p in args.design_history],
              'runs': [artifact(root, local(root, p)) for p in args.run],
              'batch': [read(local(root, p)) for p in args.with_task],
              'dependencies': [read(local(root, p)) for p in args.dependency],
              'options': {'check': args.check, 'kind': args.kind, 'path': query_paths,
                          'path_directories': [path for path in query_paths if path.directory], 'symbol': args.symbol,
                          'reason': args.reason,
                          'allow_modified_tool': args.allow_modified_tool,
                          'grant': args.grant, 'confirmed_by': args.confirmed_by}}
    if args.reconcile is not None:
        inputs['options']['reconcile'] = args.reconcile
        inputs['reconciliation_history'] = platform['history_digest'] if platform else None
    if args.command == 'review':
        import reviews
        require(not args.file or args.submit, '--file 仅用于 review --submit')
        inputs['options']['submit'] = args.submit
        if args.from_platform:
            inputs['options']['from_platform'] = True
        if args.submit:
            if args.from_platform:
                import hashlib
                item = args.platform_review
                inputs['review_markdown'] = {'path': item['url'], 'sha256': hashlib.sha256(item['body'].encode('utf-8')).hexdigest()}
                inputs['platform_review'] = {key: item[key] for key in ('url', 'author', 'created_at', 'updated_at')}
            else:
                source = reviews.source_path(args, root, task['id'])
                from common import sha
                try:
                    inputs['review_markdown'] = {
                        'path': source.relative_to(root).as_posix() if source.is_relative_to(root) else str(source),
                        'sha256': sha(source)}
                except OSError as exc:
                    raise reviews.ReviewError('评审文件', 1, '无法读取 Markdown：' + str(source), error_code=Code.REVIEW_FILE_UNREADABLE) from exc
            args.review_source_ref = inputs['review_markdown']
    if args.command == 'approval-draft' and any(getattr(args, key) is not None for key in ('reviewer', 'confirmation', 'approval_mode', 'revision')):
        inputs['options'].update(reviewer=args.reviewer, confirmation=args.confirmation, mode=args.approval_mode)
        if args.revision is not None:
            inputs['options']['revision'] = args.revision
    if args.command == 'approval-draft' and args.sections is not None:
        inputs['options']['sections'] = args.sections
    if start:
        # Auto-selected copies must not change the fingerprint of an identical request retry.
        inputs.update(files=start['explicit'], approvals=[], history=[], dependencies=[],
                      preparation=start['signature'])
    else:
        inputs['resolved_materials'] = materials.fingerprint(args, root, workspace=workspace)
    if args.command in ('start', 'brief', 'delivery-template', 'accept', 'verify', 'deliver'):
        inputs['knowledge'] = knowledge.state(root)
    from cleanup import guard
    with guard(root):
        request = Request(root, task['id'], inputs, args.request_id)
    args.actual_request_id = request.directory.name
    if request.cached is not None:
        if args.command == 'review' and not args.submit:
            import reviews
            return reviews.cached_draft(root, task['id'], request.cached)
        if args.command == 'deliver':
            import delivery_sequence
            delivery_sequence.validate_retry(root, task, request.cached)
        return request.cached
    try:
        result = produce(args, root, profile, task, platform, request, workspace=workspace)
        if args.command == 'deliver':
            return request.finish(result)
        return materials.finish(args, root, task, result, request, workspace=workspace)
    except (RuntimeInvalid, OSError, ValueError, TypeError, KeyError) as exc:
        return request.finish(repairs.failure(args, exc,
                               **({'review_failures': exc.review_failures} if hasattr(exc, 'review_failures') else {}),
                               **({'review_file': exc.review_file} if hasattr(exc, 'review_file') else {})))
    except Exception as exc:
        return request.finish(repairs.annotate(args, tool_defect(exc)))


def tool_defect(exc):
    """An unexpected exception is a tool bug: keep evidence and say so instead of blaming the input."""
    import traceback
    frames = traceback.extract_tb(exc.__traceback__)[-3:]
    return {'ok': False, 'status': 'incomplete', 'error_code': Code.TOOL_DEFECT, 'problem': repr(exc),
            'traceback': [f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in frames],
            'next_action': 'Report this as a team-workflow defect with the request directory; evidence is retained. '
                           'Do not patch the installed skill.'}


def missing_task_block(args, exc):
    requested = exc.issue_url == args.issue
    task_input = '<task.json>' if requested else '<parent-task.json>'
    return {'ok': False, 'error_code': 'issue-not-adopted' if requested else 'parent-issue-not-adopted',
            'problem': str(exc),
            'next_action': f'Draft the structured issue body first: tw team issue-draft --root "$PROJECT" '
                           f'--task {task_input} [--design <design.md>] [--with-task <sibling.json>] '
                           f'[--reviewer <name>]  (issue {exc.issue_url})'}


def pending_report(args, root, task, platform, value, design, status, history):
    import designs
    pending = designs.pending_sections(design, status, history)
    value['pending_sections'] = pending
    if approval_recovery(args, value, status):
        return value
    if pending:
        if platform:
            selector = '--issue ' + shlex.quote(platform['design_issue'])
            if platform['design_issue'] != task['id']:
                selector += ' --sections ' + shlex.quote(','.join(dict.fromkeys(row['id'] for row in pending)))
        else:
            selector = '--task ' + shlex.quote(task['id'])
            design_path = args.design
            if args.context:
                design_path = read(local(root, args.context)).get('preparation_inputs', {}).get('design_path') or design_path
            if design_path and Path(design_path).suffix == '.md' and (root / design_path).is_file():
                selector += ' --design ' + shlex.quote(str(design_path))
                selector += ''.join(' --design-history ' + shlex.quote(str(path)) for path in args.design_history
                                    if Path(path).suffix == '.md')
        value['next_action'] = ('tw team approval-draft --root ' + shlex.quote(str(root)) + ' ' + selector
                                + ' --reviewer "<评审人>"')
    return value


def verification_report(args, profile, task, value, design):
    from contracts import execution_environment
    gaps = execution_environment(profile, task, design)
    value['verification_gaps'] = gaps
    if gaps and not value.get('pending_sections'):
        value['next_action'] = gaps[0] + ('；' + value['next_action'] if value.get('next_action') else '')
    return value


def produce(args, root, profile, task, platform, request, *, workspace=None):
    def emit(value, name):
        return {'ok': value.get('ok', True), 'artifact': request.publish(name, value, args.out),
                **{k: value[k] for k in ('summary', 'gaps', 'problem', 'next_action', 'implementation_ready',
                                       'business_accepted', 'delivery_complete', 'overall_complete', 'regression_pending', 'automation_status', 'closable', 'acceptance_scope', 'scope', 'validation_active', 'verification_gaps',
                                       'ci_verified_checks', 'unverified_scope', 'summary_counts', 'statistics', 'scenario_rounds', 'scenario_files', 'summary_markdown', 'close_note', 're_evaluated', 'tool', 'environment_checked', 'pending_acceptance', 'pending_sections', 'authorizations_needed') if k in value}}
    if args.command == 'deliver':
        import delivery_sequence
        return delivery_sequence.deliver(args, root, profile, task, request, workspace=workspace)
    if args.command == 'start' and args.start_selection['continued']:
        from validation_session import active
        selection = args.start_selection
        resumed_inputs = args
        try:
            if selection['platform_gap']:
                raise Invalid(selection['platform_gap'])
            resumed_inputs = continuation_status_inputs(args, root, task, workspace=workspace)
            value = status(resumed_inputs, root, profile, task, platform, workspace=workspace)
            if platform:
                import coordination
                continuation = coordination.resume(root, profile, task['id'], cached_predecessors(args, root, profile, workspace=workspace), workspace=workspace)
                gaps = [row['problem'] for row in continuation['gap_errors']
                        if row['error_code'] not in (Code.HANDOFF_MISSING, Code.OWNER_MISSING)]
                ready = not gaps and not continuation['closed']
                value.update(ok=not gaps, ready_to_implement=ready, implementation_ready=ready, gaps=gaps)
                if gaps:
                    value.update(summary='接续仍有缺口，按所列原因修复后重新 start。',
                                 next_action='tw team start --issue ' + shlex.quote(task['id']))
        except (RuntimeInvalid, OSError, ValueError, TypeError, KeyError) as exc:
            value = {'ok': False, 'implementation_ready': False, 'ready_to_implement': False,
                     'gaps': [str(exc)], **task_steps(args, root, profile, task, workspace=workspace)}
        running = active(root)
        value['validation_active'] = running
        if running:
            value.update(implementation_ready=False, ready_to_implement=False,
                         summary='共享目录正在执行验收检查；源码和生成输入须保持不变。',
                         next_action='Wait for the active validation to finish before editing or changing checkouts.')
        paths = knowledge.query_paths(root, task, selection['design'], args.path)
        brief = value.get('knowledge') or knowledge.brief(root, task, paths, args.symbol)
        value['brief'] = request.publish('brief.json', brief)
        value.update(continued=True, task_id=task['id'], context=selection['previous_ref'],
                     task_directory=request.directory.parent.parent.relative_to(root).as_posix(),
                     task=selection['previous']['task'], design=selection['previous']['design'])
        value.setdefault('implementation_ready', value.get('ready_to_implement', False))
        value.setdefault('gaps', [])
        value['warnings'] = platform.get('warnings', []) if platform else []
        verification_report(args, profile, task, value, selection['design'])
        return {**value, 'artifact': request.publish('start.json', value, args.out)}
    if args.command == 'task-export':
        return {**emit(task, 'task.json'), 'summary': '仅导出任务；实施和交付条件尚未核对。', 'implementation_ready': False, 'business_accepted': False}
    if args.command == 'start':
        import designs
        import coordination
        selection = args.start_selection
        design = selection['design']
        coordination.validate_task_design(task, design)
        approvals, history = selection['approvals'], selection['history']
        completed, predecessors = predecessor_checks(args, root, profile, task, design, selection['dependencies'], workspace=workspace)
        readiness = designs.approval_status(design, approvals, history=history, completed_tasks=completed,
                    root=root, profile=profile,
                    section_ids=task['section_ids'], changed_paths=validation.changed_paths(root, task, profile, design, workspace=workspace),
                    code_digest=validation.source_digest(root, profile, workspace=workspace), run_refs=[], workspace=workspace)
        paths = knowledge.query_paths(root, task, design, args.path)
        brief = knowledge.brief(root, task, paths, args.symbol)
        from validation_session import active
        running = active(root)
        from common import rules_digest
        login = selection['login']
        context = {'data_version': RECORD_SCHEMA, 'kind': 'prepared-context', 'at': now(),
                   'task': request.publish('task.json', task), 'design': request.publish('design.json', design),
                   'brief': request.publish('brief.json', brief), 'source_at_start': validation.source_digest(root, profile, workspace=workspace),
                   'approvals': [request.publish(f'approval-{i}.json', v) for i, v in enumerate(approvals)],
                   'design_history': [request.publish(f'design-history-{i}.json', v) for i, v in enumerate(history)],
                   'predecessors': [request.publish(f'predecessor-{i}.json', v) for i, v in enumerate(predecessors)],
                   'dependencies': selection['dependencies'],
                   **({'design_source': platform['design_source']} if platform else {}),
                   'preparation_inputs': {**selection['signature'],
                                          **({'design_path': selection['design_path']} if selection['design_path'] else {})},
                   'implementation_ready': readiness['implementation_ready'] and not running,
                   'validation_active': running,
                   'rules_digest': rules_digest(), 'login_policy': login['policy'],
                   'authorizations': login['granted'], 'authorizations_needed': login['needed'],
                   'ok': not platform or not platform['gaps'], 'gaps': platform['gaps'] if platform else [],
                   'warnings': platform.get('warnings', []) if platform else [],
                   'summary': '任务与知识材料已准备，请实际阅读简报和方案。',
                   'next_action': (('Before signing in to any declared test account, ask the user: '
                                    + login['needed'][0]['question'] + ' ') if login['needed'] else '')
                                  + ('Implement within the approved scope.' if readiness['implementation_ready'] and not running
                                     else 'Obtain confirmation for the named plan sections.'),
                   'knowledge_claim': 'captured for reading; not evidence that knowledge was used'}
        if not readiness['implementation_ready']:
            pending_report(args, root, task, platform, context, design, readiness, history)
        verification_report(args, profile, task, context, design)
        result = {**emit(context, 'context.json'), **{k: context[k] for k in ('task', 'design', 'brief')},
                  'continued': False, 'task_id': task['id'], 'warnings': context['warnings'],
                  'task_directory': request.directory.parent.parent.relative_to(root).as_posix()}
        result['context'] = result['artifact']
        if selection['previous_ref']:
            result['superseded_context'] = selection['previous_ref']
        return result
    if args.command == 'brief':
        return emit(knowledge.brief(root, task, relative_paths(root, args.path), args.symbol), 'brief.json')
    if args.command in ('design-draft', 'approval-draft', 'handoff', 'progress'):
        import coordination
        if not args.issue and args.command in ('design-draft', 'approval-draft'):
            import designs
            design = design_files.read(local(root, args.design or args.record), workspace=workspace)
            coordination.validate_task_design(task, design)
            if args.command == 'design-draft':
                return verification_report(args, profile, task, {**emit(design, 'design.json'),
                    'checks_markdown': design_files.check_table(design, profile['checks'])}, design)
            supplied = approval_input(args, root)
            require(isinstance(supplied, dict) and 'reviewer' in supplied, 'Approval input must name the reviewer', error_code=Code.APPROVAL_INCOMPLETE)
            allowed = {'reviewer', 'confirmation', 'decision', 'section_ids', 'deletion_ids', 'mode', 'revision'}
            require(supplied.keys() <= allowed, 'Unknown approval input fields', error_code=Code.APPROVAL_INCOMPLETE)
            history = [design_files.read(local(root, p), workspace=workspace) for p in args.design_history]
            assessments = designs.task_assessments(design, task['section_ids'])
            mode = supplied.pop('mode', 'combined' if any(v['complexity'] == 'simple' for v in assessments.values()) else 'design')
            binding = {'code_digest': validation.source_digest(root, profile, workspace=workspace),
                       'run_refs': [artifact(root, local(root, p)) for p in args.run]} if mode == 'combined' else {}
            supplied = designs.approval_selection(design, [read(local(root, p)) for p in args.approval],
                task['section_ids'], history, {**supplied, 'mode': mode, **binding}, root=root, profile=profile, workspace=workspace)
            if supplied is None:
                return verification_report(args, profile, task, {'ok': True, 'summary': '没有需要批准的章节'}, design)
            result = designs.approval_draft(design, history=history, **supplied)
            return verification_report(args, profile, task, {**emit(result, 'approval.json'),
                'summary': '批准草稿：' + coordination.approval_sentence(result, design)}, design)
        require(args.issue == task['id'], 'Shared draft requires its canonical --issue')
        resolution = ({'history_digest': platform['history_digest'], 'reason': args.reconcile}
                      if args.reconcile is not None else None)
        if args.command == 'design-draft':
            result = coordination.draft_design(args.issue, design_files.read(local(root, args.record or args.design), workspace=workspace),
                                               resolution=resolution, path=local(root, args.record or args.design), root=root)
        elif args.command == 'approval-draft':
            supplied = approval_input(args, root)
            if resolution is not None:
                supplied['resolution'] = resolution
            if not args.record:
                import designs
                assessments = designs.task_assessments(platform['design'], task['section_ids'])
                mode = supplied.setdefault('mode', 'combined' if any(row['complexity'] == 'simple' for row in assessments.values()) else 'design')
                if mode == 'combined':
                    supplied.update(code_digest=validation.source_digest(root, profile, workspace=workspace),
                                    run_refs=[artifact(root, local(root, p)) for p in args.run])
            result = coordination.draft_approval(args.issue, supplied, root=root, workspace=workspace)
        elif args.command == 'progress':
            result = coordination.progress_draft(root, profile, args.issue, read(local(root, args.progress)), request.directory.name)
        else:
            completed, _ = predecessor_checks(args, root, profile, task, platform['design'], workspace=workspace)
            result = coordination.draft(root, profile, args.issue, read(local(root, args.progress)),
                                        args.kind, completed_tasks=completed, workspace=workspace)
        if args.command in ('design-draft', 'approval-draft'):
            design = (design_files.read(local(root, args.record or args.design), workspace=workspace)
                      if args.command == 'design-draft' else platform['design'])
            verification_report(args, profile, task, result, design)
        if args.command == 'approval-draft' and 'record' not in result:
            return result
        return {**emit(result, args.command + '.json'), **{key: result[key] for key in
                ('markdown', 'record', 'next_steps', 'pr_description') if key in result}}
    if args.command == 'design-diff':
        import designs
        require(bool(args.design_history), 'Design diff needs at least the previous snapshot')
        previous = [design_files.read(local(root, p), workspace=workspace) for p in args.design_history]
        current = design_files.read(local(root, args.design), workspace=workspace)
        return emit(designs.impact(previous[-1], current, history=previous,
                    changed_paths=validation.changed_paths(root, task, profile, current, workspace=workspace)), 'design-diff.json')
    if args.command == 'run':
        tasks = [task]
        for path in args.with_task:
            sibling = task_inputs.validate_written(read(local(root, path)))
            tasks.append(task_inputs.expand(sibling, design_files.read(local(root, args.design), workspace=workspace)))
        path, record = validation.run_batch(root, profile, tasks, args.check, request.directory / 'execution', args.portable, workspace=workspace)
        ok = record['source_unchanged'] and all(r['status'] == 'passed' for r in record['results'])
        failed = [f'{r["id"]}: {r["detail"]}' for r in record['results'] if r['status'] != 'passed']
        moved = [r['id'] for r in record['results'] if r['status'] == 'passed' and not r.get('source_unchanged')]
        changed = ([f'inputs of {", ".join(moved)} changed while the check ran'] if moved else
                   [] if record['source_unchanged'] else ['project source changed during the run'])
        result = {'ok': ok, 'scope': 'execution-only',
                'artifact': request.publish('run.json', record, args.out) if args.out else artifact(root, path),
                'checks': [{'id': r['id'], 'status': r['status'], 'detail': r['detail'],
                            **({'source_unchanged': False} if r['id'] in moved else {})} for r in record['results']],
                **({} if ok else {'error_code': check_error_code(
                    {r.get('error_code') for r in record['results']}, Code.CHECK_RESULT if failed else Code.RUN_BINDING_STALE),
                    'problem': 'A check failed or its inputs changed during the run: ' + '; '.join(failed + changed),
                    'next_action': ('Read each failed check above. If the command itself ran but a registered required case name is wrong, '
                                    'correct required_cases and verify again: the original report is re-evaluated without a re-run. '
                                    'Otherwise fix the failure and run only that check with --check and a new request ID.') if failed else
                                   ('Results that ran while files changed cannot be used. Keep the workspace unchanged until checks finish, '
                                    'then run ' + (' '.join('--check ' + m for m in moved) or 'the checks') + ' again with a new request ID.')})}
        if ok:
            import reviews
            result = reviews.from_run(args, root, profile, task, result, request, workspace=workspace)
        else:
            repairs.annotate(args, result)
        return result
    if args.command == 'review':
        import reviews
        return (reviews.submit if args.submit else reviews.generate)(args, root, profile, task, request, workspace=workspace)
    if args.command == 'delivery-template':
        report = report_input(args, root, task)
        if args.reason is not None:
            report['knowledge']['reason'] = args.reason
        return emit(report, 'delivery.json')
    if args.command in ('accept', 'verify'):
        import delivery
        import issue_history
        if args.report:
            report = read(local(root, args.report))
            import materials
            effective = materials.effective_report(args, root, report)
            if args.command == 'accept' and effective != report:
                request.publish('report.json', effective)
            report = effective
            if args.command == 'verify':
                materials.report_matches(args, root, report)
        else:
            require(args.command == 'accept', 'verify needs --report <delivery.json>', error_code=Code.REPORT_INCOMPLETE)
            require(args.context is not None, '业务验收尚缺本任务的准备上下文',
                    next_action=repairs.command(args, 'start'))
            if args.review is None:
                from reviews import ReviewNotSubmitted
                raise ReviewNotSubmitted(root, task, missing_run=not bool(args.run))
            require(bool(args.run), 'accept needs --run <run.json>')
            report = report_input(args, root, task, include_knowledge=False)
            request.publish('report.json', report)
        issue_history.capture(request, task, read(local(root, report['review'])),
            [r['id'] for r in design_files.read(local(root, report['design']), workspace=workspace)['sections']])
        phase = 'acceptance' if args.command == 'accept' else 'delivery'
        return emit(delivery.verify(root, profile, task, report, phase=phase, workspace=workspace), phase + '.json')
    raise Invalid('Unsupported command: ' + args.command)


def approval_input(args, root):
    flags = any(getattr(args, key) is not None for key in ('reviewer', 'confirmation', 'approval_mode', 'revision'))
    require(not (args.record and flags), '--record 与批准参数二选一', error_code=Code.APPROVAL_INCOMPLETE)
    if args.record:
        result = read(local(root, args.record))
    else:
        require(bool(args.reviewer), '请用 --reviewer 指定批准人，或用 --record 提供已有输入', error_code=Code.APPROVAL_INCOMPLETE)
        result = {'reviewer': args.reviewer, 'confirmation': args.confirmation or ''}
    if args.sections is not None:
        result['section_ids'] = 'all' if args.sections.strip() == 'all' else [key.strip() for key in args.sections.split(',')]
    if args.approval_mode:
        result['mode'] = 'design' if args.approval_mode == 'plan' else 'combined'
    if args.revision is not None:
        result['revision'] = args.revision
    return result


def login_policy(profile, args):
    declared = profile.get('accounts', [])
    agent = [row['id'] for row in declared if row['login'] == 'agent-after-authorization']
    policy = {'user_signs_in': [row['id'] for row in declared if row['login'] == 'user'] + ['(any undeclared account)'],
              'agent_after_authorization': agent}
    granted = []
    if args.grant:
        require(args.grant == 'synthetic-login' and bool(agent), 'No declared synthetic account can be authorized')
        require(bool(args.confirmed_by and args.confirmed_by.strip()), '--grant needs --confirmed-by <the user who authorized it>')
        granted.append({'id': 'synthetic-login', 'accounts': agent, 'confirmed_by': args.confirmed_by, 'at': now()})
    needed = [] if granted or not agent else [{
        'id': 'synthetic-login', 'accounts': agent,
        'question': '是否授权代理在本任务中登录以下项目声明的本地隔离测试账号：' + '、'.join(agent)
                    + '？真实账号仍由你本人在真实浏览器登录。'}]
    return {'policy': policy, 'granted': granted, 'needed': needed}


def step_materials(args):
    selection = getattr(args, 'material_selection', None) or {}
    return {'task_identity': selection.get('task_id') if selection.get('identity') else None,
            'material_group': selection.get('effective') or selection.get('value'), 'review_inputs': args}


def continuation_status_inputs(args, root, task, *, workspace=None):
    """Preparation signatures stay fixed; continuation displays the current recorded evidence."""
    selection = getattr(args, 'material_selection', None) or {}
    if not selection.get('value'):
        return args  # Keep complete legacy explicit-context operations usable.
    current = copy.copy(args)
    current.command, current.task = 'status', task['id']
    for key in ('context', 'design', 'brief', 'review', 'acceptance', 'report'):
        setattr(current, key, None)
    for key in ('approval', 'design_history', 'run'):
        setattr(current, key, [])
    for key, value in selection['explicit'].items():
        setattr(current, key, copy.deepcopy(value))
    import materials
    materials.resolve(current, root, workspace=workspace)
    current.material_selection['identity'] = selection['identity']
    return current


def task_phase(platform, root=None, task_id=None, group=None):
    """先读平台关闭事实，再按最终交付及后续活动确定阶段。"""
    if platform and platform.get('task_state', platform.get('state')) == 'closed':
        return 'closed'
    if root is None or group is None or not group.get('delivery'):
        return 'in-progress'
    import checklist
    from datetime import datetime
    try:
        proof = read(artifact_valid(root, group['delivery']))
        if not (proof.get('kind') == 'delivery-verification' and proof.get('ok')
                and proof.get('delivery_complete') and proof.get('task_id') == task_id):
            return 'in-progress'
        delivered_at = datetime.fromisoformat(proof['at'])
        for claim, response in checklist.records(root, task_id):
            if claim.get('command') in ('start', 'run', 'review') and datetime.fromisoformat((response or {}).get('finished_at', claim['started_at'])) > delivered_at:
                return 'in-progress'
        for ref in group.get('scenario_rounds', []):
            row = read(artifact_valid(root, ref))
            if datetime.fromisoformat(row['submitted_at']) > delivered_at:
                return 'in-progress'
    except (Invalid, OSError, ValueError, KeyError, TypeError):
        return 'in-progress'
    return 'delivered'


def recorded_command(args, root):
    """完成阶段在方案解析之前读取；显式 verify 保留当前核对。"""
    scenario_pending = args.command == 'scenarios' and args.scenario_action == 'pending'
    if args.command not in ('status', 'deliver') and not scenario_pending:
        return None
    import materials
    import status_records
    from tw_runtime.team import platform_script as platform_read
    identity = args.issue or (str(args.task) if args.task else None)
    if args.task and (root / args.task).is_file():
        identity = task_inputs.validate_written(read(local(root, args.task)),
            local(root, args.task).relative_to(root).as_posix())['id']
    if identity is None and args.context:
        context = read(local(root, args.context))
        identity = read(artifact_valid(root, context['task']))['id']
    if identity is None:
        return None
    platform = (platform_read.call(root, 'task', '--id', identity)
                if platform_read.is_task(root, identity, required=False) else None)
    group = materials.load(root, identity)
    phase = task_phase(platform, root, identity, group)
    if phase == 'in-progress':
        return None
    if args.command == 'deliver' and phase == 'delivered':
        ref = group['delivery']
        proof = read(artifact_valid(root, ref))
        from summary import delivery_status
        return {**proof, 'artifact': ref, 'reused': True, 'task_phase': phase,
                **delivery_status(proof), 'next_action': status_records.closing_action(root, identity)}
    if args.command == 'status' or scenario_pending:
        result = status_records.recorded(root, identity, phase, group, platform)
        if scenario_pending:
            result.update(task_id=identity, pending=[], pending_count=0)
            result.setdefault('summary_counts', {key: 0 for key in ('passed', 'failed', 'blocked', 'pending')})
        return result
    return None


def task_steps(args, root, profile, task, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    import checklist
    from common import rules_digest
    context = read(local(root, args.context)) if args.context else None
    value = checklist.steps(root, task, validation.source_digest(root, profile, workspace=workspace), args.context,
                            str(args.task) if args.task else None, profile=profile, current=getattr(args, 'current_request', None), **step_materials(args), workspace=workspace)
    if context:
        value['authorizations'] = context.get('authorizations', [])
        value['rules_changed'] = context.get('rules_digest') not in (None, rules_digest())
    return value


def current_status(root, task_id, current=None, *, workspace=None, scenario_state=None):
    """按任务身份走状态入口的同一套材料读取与流程计算。"""
    from workflow import parser
    args = parser().parse_args(['status', '--root', str(root), '--task', task_id])
    args.current_request = current
    args.scenario_state = scenario_state
    return dispatch(args, root, workspace=workspace)


def status(args, root, profile, task, platform=None, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    import checklist
    import status_records
    phase = task_phase(platform, root, task['id'], (getattr(args, 'material_selection', None) or {}).get('value'))
    if phase in ('closed', 'delivered'):
        return status_records.recorded(root, task['id'], phase,
            (getattr(args, 'material_selection', None) or {}).get('value'), platform)
    progress = task_steps(args, root, profile, task, workspace=workspace)
    value = _status(args, root, profile, task, platform, workspace=workspace)
    value['task_phase'] = phase
    facts = status_records.inspect(args, root, profile, task, progress, value, workspace=workspace)
    for row in progress['steps']:
        reason = facts['stale_steps'].get(row['id'])
        if reason and (row.get('evidence') or row['state'] in ('done', 'stale')):
            row.update(state='stale', stale_reason=reason)
        if row['id'] == 'knowledge' and facts['report_complete'] is False and row['state'] == 'done':
            row.update(state='pending', evidence=None, incomplete_reason=facts.get('report_problem', '知识处置尚未完整'))
    by_id = {row['id']: row for row in progress['steps']}
    for index, row in enumerate(progress['steps']):
        if row['state'] == 'stale':
            for later in progress['steps'][index + 1:]:
                if later.get('evidence') and later['state'] in ('done', 'stale'):
                    later.update(state='stale', stale_reason=later.get('stale_reason') or '前序材料已变化')
    if facts['review_current']:
        selected = '--task ' + shlex.quote(task['id'])
        repair = facts.get('review_case_repair', {}).get('next_action')
        if facts['review_failures'] and not repair:
            from delivery import ReviewBlocked
            repair = ReviewBlocked(task, facts['review_failures']).next_action  # deliver would only fail again
        for row in progress['steps'][3:]:
            if repair or row['state'] != 'failed':
                row['next_command'] = repair or 'tw team deliver ' + selected + ' --reason <不需要更新知识的理由>'
    urgent = [row for row in progress['steps'] if row['state'] in ('stale', 'running-or-interrupted', 'failed')]
    progress['next_step'] = urgent[0] if urgent else next((row for row in progress['steps'] if row['state'] == 'pending'), None)
    progress['finished'] = progress['next_step'] is None
    value['verified_records'] = {key: ref for key, ref in facts['verified_records'].items()
                                 if by_id[key]['state'] == 'done'}
    value['stale_materials'] = facts['stale_materials']
    value['ok'] = True  # A successful read reports unmet gates as facts, not as a failed status query.
    value['publication'] = status_records.publication(platform)
    value['warnings'] = platform.get('warnings', []) if platform else []
    value['steps'] = progress['steps']
    value['next_step'] = progress['next_step']
    for key in ('authorizations', 'rules_changed'):
        if key in progress:
            value[key] = progress[key]
    value['summary'] = ('已交付；关闭需要授权，工具不执行关闭' if 'delivery' in value['verified_records']
                        and not progress['next_step'] else '按已核实的记录和下一步继续。')
    value['next_action'] = progress['next_step']['next_command'] if progress['next_step'] else value['summary']
    if facts['review_failures'] and facts['review_current'] and not facts.get('review_case_repair'):
        from delivery import ReviewBlocked
        blocked = ReviewBlocked(task, facts['review_failures'])
        value.update(summary='评审已提交，仍有不通过项或阻塞问题。', review_failures=facts['review_failures'],
                     next_action=blocked.next_action)
    if facts.get('review_case_repair') and facts['review_current']:
        repair = facts['review_case_repair']
        value.update(summary='评审中的用例需要修正后重新提交。', review_failures=facts['review_failures'], **repair)
        progress['next_step'] = {'id': 'review', 'label': '修正评审中的用例并重新提交', 'next_command': repair['next_action']}
        value['next_step'] = progress['next_step']
    if facts['stale_materials']:
        value['summary'] = '方案或批准等材料已变化，请重新 start 后继续。'
        extra = '--design ' + shlex.quote(str(args.design)) if args.design and 'design' in (getattr(args, 'material_selection', None) or {}).get('explicit', {}) else ''
        row = by_id['prepare']
        row['next_command'] = repairs.command(args, 'start', extra)
        value['next_action'] = row['next_command']
    if any(row['state'] == 'done' for row in progress['steps'][3:]):
        value.pop('missing', None)
        value.pop('stale', None)
    approval_recovery(args, value, value)
    import scenario_rounds
    scenario_rounds.status_step(root, profile, task['id'], progress,
                               (getattr(args, 'material_selection', None) or {}).get('effective'), workspace=workspace,
                               state=getattr(args, 'scenario_state', None))
    if (progress.get('next_step') or {}).get('id') == 'scenarios':
        value.update(next_step=progress['next_step'], next_action=progress['next_step']['next_command'])
    plan_approval = value.get('review_mode') in ('mixed', 'design-first')
    if args.design and plan_approval and not value.get('implementation_ready', True):
        design = design_files.read(local(root, args.design), workspace=workspace)
        history = [design_files.read(local(root, p), workspace=workspace) for p in args.design_history]
        pending_report(args, root, task, platform, value, design, value, history)
        if value.get('pending_sections'):
            progress['next_step'] = {'id': 'approval', 'label': APPROVAL_RECOVERY_LABELS.get(value.get('error_code'), '取得待确认章节的批准'),
                                     'next_command': value['next_action']}
            value['next_step'] = progress['next_step']
    if args.design:
        value.setdefault('pending_sections', [])
        verification_report(args, profile, task, value, design_files.read(local(root, args.design), workspace=workspace))
    value['step_lines'] = checklist.render(progress)
    if progress.get('rules_changed'):
        value['step_lines'].append('注意：开始任务后团队流程规则已更新；按当前规则核对已完成的步骤。')
    return value


def _status(args, root, profile, task, platform=None, *, workspace=None):
    if args.report:
        import delivery
        import materials
        report = materials.effective_report(args, root, read(local(root, args.report)))
        _, _, value, _ = delivery.design_material(root, profile, task, report, cached_predecessors(args, root, profile, workspace=workspace), workspace=workspace)
        return value
    require(args.design is not None, 'Local task status needs --design or --context; provide --report to verify acceptance/delivery')
    import designs
    from coordination import validate_task_design
    design = design_files.read(local(root, args.design), workspace=workspace)
    validate_task_design(task, design)
    value = designs.approval_status(design, [read(local(root, p)) for p in args.approval],
                root=root, profile=profile,
                history=[design_files.read(local(root, p), workspace=workspace) for p in args.design_history], section_ids=task['section_ids'],
                completed_tasks=cached_predecessors(args, root, profile, workspace=workspace),
                changed_paths=validation.changed_paths(root, task, profile, design, workspace=workspace), code_digest=validation.source_digest(root, profile, workspace=workspace),
                run_refs=[artifact(root, local(root, p)) for p in args.run], workspace=workspace)
    ready = value['implementation_ready']
    summary = '可以继续实施；方案、代码与交付仍需实际验收。' if ready else '实施条件尚未满足：需补齐方案批准、决策、分派或前置任务证明。'
    next_action = 'Run tw team start with the same plan and existing approvals, then follow its next command.' if ready else 'Resolve the named pending sections or predecessor evidence, then run tw team start again.'
    return {**value, 'summary': summary, 'next_action': next_action}


def external_repository_problems(root, profile):
    """Resolve declared repository inputs now, so a wrong identity is not first found by start or run."""
    from common import location_settings
    from portable import repository_id
    errors, warnings = [], []
    try:
        mapped = location_settings(root)['repositories']
    except Invalid as exc:
        return [str(exc)], []
    for name, item in sorted(profile.get('external_inputs', {}).items()):
        if item.get('kind') != 'repository':
            continue
        identity = item['repository']
        if identity not in mapped:
            warnings.append(f'external_inputs.{name}（{identity}）没有本机映射；需要它的 start、run 会失败')
            continue
        path = (root / Path(mapped[identity]).expanduser()).resolve()
        try:
            actual = repository_id(path)
        except Invalid as exc:
            errors.append(f'external_inputs.{name}：本机路径 {path} 无法确定仓库身份：{exc}')
            continue
        if actual != identity:
            errors.append(f'external_inputs.{name} 写的是 {identity}，本机检出 {path} 的身份是 {actual}；'
                          f'请把 .tw/config.json 中的 repository 和本机映射的键改为 {actual}')
    return errors, warnings


def project_report(root, home=None):
    from common import ALLOW_MODIFIED
    from tw_runtime import check, install
    from tw_runtime.project import Project
    import os
    config_errors, input_warnings = [], []
    config_code = None
    try:
        profile = load_profile(root)
    except (Invalid, OSError, ValueError) as exc:
        config_errors.append(str(exc))
        config_code = getattr(exc, 'error_code', None)
        profile = None
    if profile is not None:
        problems, input_warnings = external_repository_problems(root, profile)
        config_errors += problems
        if not profile['context']:
            input_warnings.append('项目验收方案与真实验证操作手册尚未登记到 context')
    checked = check.run(Project(root, require_config=False))
    installed = install.check_install(home, require_team=True)
    override = os.environ.get(ALLOW_MODIFIED) == '1'
    ok = not config_errors and not checked['errors'] and (installed['ok'] or override)
    result = {'ok': ok, 'data_version': RECORD_SCHEMA, 'scope': 'project-configuration',
              'config': {'ok': not config_errors, 'errors': config_errors},
              'knowledge': {'errors': len(checked['errors']), 'check': checked},
              'installation': installed, 'tool': {'override': override},
              'warnings': input_warnings + installed['installation_problems'],
              'summary': '项目配置、知识结构与安装已核对。' + (
                  f'另有 {len(installed["installation_problems"])} 个安装提示，见 warnings。' if installed['installation_problems'] else '')}
    if not installed['ok'] and not override:
        result.update(error_code=Code.TOOL_MODIFIED, problem='；'.join(installed['problems']))
    elif config_code == Code.PROJECT_UNINITIALIZED:
        result['error_code'] = config_code
    problems = config_errors + [row['path'] + '：' + row['message'] for row in checked['errors']]
    if not installed['ok'] and not override:
        problems += installed['problems']
    if problems:
        result['problem'] = '；'.join(problems)
    return result
