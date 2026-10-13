"""Version 5 CLI composition; legacy task contracts remain explicitly versioned."""
import json
from pathlib import Path

from common import (Invalid, artifact, create, digest, inside, location_settings, now,
                    profile_valid, read, require, task_valid, text)
import knowledge
import validation

NEW_COMMANDS = {'prepare', 'design-draft', 'approval-draft', 'design-diff', 'schema', 'cleanup'}


def local(root, value):
    require(value is not None, 'Missing input path')
    path = Path(value)
    if path.is_absolute():
        require(path.resolve().is_relative_to(root), 'Input must be inside the project')
        path = path.relative_to(root)
    return inside(root, path.as_posix())


def handles(args, root):
    return args.command not in ('version', 'agents', 'stage-draft', 'migrate', 'upgrade', 'adopt')


def readable(result):
    lines = [result.get('summary') or result.get('status') or ('命令已完成；验收状态见下方' if result.get('ok', True) else '尚未完成')]
    for key in ('problem', 'next_action'):
        if result.get(key):
            lines.append(str(result[key]))
    for gap in result.get('gaps', []):
        lines.append('- ' + str(gap))
    for key in ('artifact', 'task', 'design', 'brief'):
        item = result.get(key)
        if isinstance(item, dict) and item.get('path'):
            lines.append(key + ': ' + item['path'])
    for name, path in result.get('templates', {}).items():
        lines.append('模板 ' + name + ': ' + path)
    for target in result.get('targets', []):
        lines.append(f"{target.get('action')}: {target['path']}" + (f" ({target['reason']})" if target.get('reason') else ''))
    if result.get('reference'):
        lines.append('字段说明: ' + result['reference'])
    pending = set(result.get('missing', [])) | set(result.get('stale', []))
    pending &= set(result.get('required_sections', pending))
    if pending:
        lines.append('待确认章节：' + '、'.join(sorted(pending)))
    labels = {'needs-review': '方案待评审', 'pending-decision': '有待定业务问题', 'unassigned': '未指派实施者',
              'waiting-for-tasks': '等待前置任务验收', 'scope-unknown': '尚未声明范围', 'needs-history': '缺少方案历史'}
    for name, value in result.get('tasks', {}).items():
        if not value.get('ready'):
            lines.append('任务 ' + name + '：' + labels.get(value.get('state'), str(value.get('state'))))
    if result.get('checks'):
        lines.append('检查：' + json.dumps(result['checks'], ensure_ascii=False))
    for key in ('implementation_ready', 'business_accepted', 'delivery_complete', 'regression_pending', 'closable'):
        if key in result:
            lines.append(key + ': ' + str(result[key]))
    if isinstance(result.get('automation_status'), dict):
        for row in result['automation_status']['pending_automation']:
            lines.append(f"自动化待建设：{row['id']} → {row['finding']}，期限 {row['due']}")
    return '\n'.join(lines)


def references(root, values):
    return [local(root, p).relative_to(root).as_posix() for p in values]


def report_input(args, root, task):
    for name in ('design', 'brief'):
        require(getattr(args, name) is not None, 'Missing --' + name + '; supply the existing artifact or use prepare with current approvals and --context')
    result = {'schema_version': 5, 'task_id': task['id'], 'design': local(root, args.design).relative_to(root).as_posix(),
              'approvals': references(root, args.approval), 'design_history': references(root, args.design_history),
              'brief': local(root, args.brief).relative_to(root).as_posix(), 'runs': references(root, args.run),
              'review': local(root, args.review).relative_to(root).as_posix() if args.review else ''}
    if args.knowledge:
        result['knowledge'] = local(root, args.knowledge).relative_to(root).as_posix()
    if args.dependency:
        result['dependencies'] = [read(local(root, p)) for p in args.dependency]
    return result


def predecessor_checks(args, root, profile, task, design):
    """Explicit preparation/hand-off checks may revalidate predecessor evidence."""
    import delivery
    import designs
    completed, proofs = [], []
    hashes = designs.fingerprints(design)['sections']
    for path in args.dependency:
        value = read(local(root, path))
        require(set(value) == {'section', 'task', 'report'}, 'Dependency needs section, task and report paths')
        dependency = read(local(root, value['task']))
        require(value['section'] in dependency['section_ids'] and dependency['design_id'] == task['design_id'],
                'Predecessor evidence belongs to another task section')
        proof = delivery.verify(root, profile, dependency, read(local(root, value['report'])), args.cs_skill, 'acceptance')
        require(proof['sections'][value['section']] == hashes.get(value['section']), 'Predecessor plan changed')
        completed.append(value['section'])
        proofs.append({'section': value['section'], 'acceptance': proof})
    return completed, proofs


def cached_predecessors(args, root, profile):
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
        require(proof['source_digest'] == validation.source_digest(root, profile), 'Predecessor source changed; prepare again')
        for item in proof['materials']:
            artifact_valid(root, item)
        completed.append(value['section'])
    return completed


def dispatch(args, root):
    if args.command == 'schema':
        directory = Path(__file__).resolve().parents[1] / 'templates'
        return {'ok': True, 'summary': '第五版模板与字段说明',
                'templates': {p.stem: str(p) for p in sorted(directory.glob('*.json'))},
                'reference': str(Path(__file__).resolve().parents[1] / 'references/contracts-v5.md'),
                'versions': {'profile': [5], 'task': [5], 'new_records': 5},
                'next_action': 'Read the installed template; replace every placeholder and retain the task format version.'}
    if args.command == 'cleanup':
        import cleanup
        require(not (args.apply and args.dry_run), 'Choose cleanup preview or apply')
        return cleanup.apply(root, read(args.plan)) if args.apply else cleanup.preview(root)
    if args.command == 'aggregate':
        import portable_v4
        mappings = {key: (root / Path(path).expanduser()).resolve() for key, path in location_settings(root)['repositories'].items()}
        return portable_v4.aggregate(root, read(local(root, args.joint)), mappings, args.cs_skill)
    if args.context:
        from common import artifact_valid
        context = read(local(root, args.context))
        require(context.get('schema_version') == 5 and context.get('kind') == 'prepared-context', 'Expected prepared context')
        for key in ('task', 'design', 'brief'):
            path = artifact_valid(root, context[key])
            if getattr(args, key) is None:
                setattr(args, key, path)
        if not args.approval:
            args.approval = [artifact_valid(root, r) for r in context['approvals']]
        if not args.design_history:
            args.design_history = [artifact_valid(root, r) for r in context['design_history']]
    profile = profile_valid(read(local(root, args.profile)), root)
    platform = None
    if args.issue:
        import coordination
        platform = coordination.load(args.issue)
    task = read(local(root, args.task)) if args.task else platform['task'] if platform else None
    if args.command == 'project':
        try:
            skill = knowledge.skill_path(args.cs_skill)
            knowledge.supported(knowledge.call(skill, root, ['--check'], bootstrap=True), True)
            cs = {'status': 'ready'}
        except Invalid as exc:
            cs = {'status': 'incomplete', 'reason': str(exc), 'problem': str(exc)}
        return {'ok': cs['status'] == 'ready', 'schema_version': 5, 'cs': cs,
                'scope': 'project-configuration', 'summary': '已核对项目配置与 CS 能力。'}
    if args.command == 'evidence':
        from common import external_path
        refs = []
        for name in args.path:
            if args.evidence_repository:
                values = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == args.evidence_repository]
                require(len(values) == 1, 'Evidence repository must be declared')
                target = external_path(root, args.evidence_repository, values[0])
                refs.append({'repository': args.evidence_repository, **artifact(target, inside(target, name))})
            else:
                refs.append(artifact(root, local(root, name)))
        return {'ok': True, 'artifacts': refs}
    if args.command == 'import-result':
        import portable_v4
        from artifacts import Request
        from cleanup import guard
        locator_path = local(root, args.result)
        inputs = {'command': 'import-result', 'locator': artifact(root, locator_path),
                  'profile': digest(profile), 'source': validation.source_digest(root, profile)}
        with guard(root):
            request = Request(root, 'imports:' + profile['project'], inputs, args.request_id)
        if request.cached is not None:
            return request.cached
        try:
            path, record = portable_v4.import_result(root, profile, read(locator_path), request.directory / 'import')
            ref = request.publish('import.json', record, args.out) if args.out else artifact(root, path)
            return request.finish({'ok': True, 'artifact': ref, 'scope': 'execution-only'})
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            return request.finish({'ok': False, 'problem': str(exc), 'error_code': 'import-incomplete',
                                   'next_action': 'Inspect provider identity and original reports; retry with a new request ID.'})
    require(task is not None and task.get('schema_version') == 5, 'This operation requires an explicit v5 task; legacy tasks are not upgraded automatically')
    task_valid(task, profile, root)
    if platform:
        require(platform['task'] == task, 'Local task differs from platform requirements')
    if args.command in ('status', 'resume'):
        value = status(args, root, profile, task, platform)
        from validation_session import active
        running = active(root)
        value['validation_active'] = running
        if running:
            value.update(implementation_ready=False,
                         summary='共享目录正在执行验收检查；源码和生成输入须保持不变。',
                         next_action='Wait for the active validation to finish before editing or changing checkouts.')
        return value
    if args.command == 'snapshot':
        return {'ok': True, 'source_digest': validation.source_digest(root, profile), 'task_digest': digest(task)}
    from artifacts import Request
    input_files = {}
    for name in ('task', 'design', 'brief', 'review', 'report', 'knowledge', 'progress', 'record', 'acceptance', 'final_brief'):
        value = getattr(args, name, None)
        if value:
            input_files[name] = artifact(root, local(root, value))
    inputs = {'command': args.command, 'phase': args.phase, 'task': digest(task), 'profile': digest(profile),
              'files': input_files, 'source': validation.source_digest(root, profile),
              'approvals': [artifact(root, local(root, p)) for p in args.approval],
              'history': [artifact(root, local(root, p)) for p in args.design_history],
              'runs': [artifact(root, local(root, p)) for p in args.run],
              'batch': [read(local(root, p)) for p in args.with_task],
              'dependencies': [read(local(root, p)) for p in args.dependency],
              'options': {'check': args.check, 'kind': args.kind, 'path': args.path, 'symbol': args.symbol,
                          'cs_task_id': args.cs_task_id, 'disposition': args.disposition, 'reason': args.reason}}
    from cleanup import guard
    with guard(root):
        request = Request(root, task['id'], inputs, args.request_id)
    if request.cached is not None:
        return request.cached
    try:
        result = produce(args, root, profile, task, platform, request)
        return request.finish(result)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        return request.finish({'ok': False, 'status': 'incomplete', 'problem': str(exc),
                               'error_code': 'invalid-or-incomplete-input',
                               'next_action': 'Correct the named input and use a new request ID; keep the failed request for diagnosis.'})


def produce(args, root, profile, task, platform, request):
    def emit(value, name):
        return {'ok': value.get('ok', True), 'artifact': request.publish(name, value, args.out),
                **{k: value[k] for k in ('summary', 'gaps', 'problem', 'next_action', 'implementation_ready',
                                       'business_accepted', 'delivery_complete', 'regression_pending', 'automation_status', 'closable', 'acceptance_scope', 'scope', 'validation_active', 'verification_gaps') if k in value}}
    if args.command == 'task-export':
        return {**emit(task, 'task.json'), 'summary': '仅导出任务；实施和交付条件尚未核对。', 'implementation_ready': False, 'business_accepted': False}
    if args.command == 'prepare':
        import designs
        import coordination
        design = read(local(root, args.design)) if args.design else platform['design'] if platform else None
        require(design is not None, 'Prepare needs the short design or a shared plan')
        coordination.validate_task_design(task, design)
        approvals = [read(local(root, p)) for p in args.approval] if args.approval else platform['approvals'] if platform else []
        history = [read(local(root, p)) for p in args.design_history] if args.design_history else platform['history'] if platform else []
        completed, predecessors = predecessor_checks(args, root, profile, task, design)
        readiness = designs.approval_status(design, approvals, history=history, completed_tasks=completed,
                    section_ids=task['section_ids'], changed_paths=validation.changed_paths(root, task),
                    code_digest=validation.source_digest(root, profile), run_refs=[])
        sections = {row['id']: row for row in design['sections']}
        paths = args.path or task.get('paths') or sorted({path for key in task['section_ids']
                    if sections[key]['type'] == 'task' for path in sections[key]['data']['scope']})
        brief = knowledge.brief(root, task, knowledge.skill_path(args.cs_skill), paths, args.symbol)
        from contracts_v5 import execution_environment
        from validation_session import active
        environment_gaps = execution_environment(profile, task, design)
        running = active(root)
        context = {'schema_version': 5, 'kind': 'prepared-context', 'at': now(),
                   'task': request.publish('task.json', task), 'design': request.publish('design.json', design),
                   'brief': request.publish('brief.json', brief), 'source_at_start': validation.source_digest(root, profile),
                   'approvals': [request.publish(f'approval-{i}.json', v) for i, v in enumerate(approvals)],
                   'design_history': [request.publish(f'design-history-{i}.json', v) for i, v in enumerate(history)],
                   'predecessors': [request.publish(f'predecessor-{i}.json', v) for i, v in enumerate(predecessors)],
                   'implementation_ready': readiness['implementation_ready'] and not running,
                   'validation_active': running, 'verification_gaps': environment_gaps,
                   'ok': not platform or not platform['gaps'], 'gaps': platform['gaps'] if platform else [],
                   'summary': '任务与知识材料已准备，请实际阅读简报和方案。',
                   'next_action': 'Implement within the approved scope.' if readiness['implementation_ready'] and not running else 'Obtain confirmation for the named plan sections.',
                   'knowledge_claim': 'captured for reading; not evidence that knowledge was used'}
        return {**emit(context, 'context.json'), **{k: context[k] for k in ('task', 'design', 'brief')}}
    if args.command == 'brief':
        return emit(knowledge.brief(root, task, knowledge.skill_path(args.cs_skill), args.path, args.symbol), 'brief.json')
    if args.command in ('design-draft', 'approval-draft', 'handoff', 'progress'):
        import coordination
        if not args.issue and args.command in ('design-draft', 'approval-draft'):
            import designs
            design = read(local(root, args.design or args.record))
            coordination.validate_task_design(task, design)
            if args.command == 'design-draft':
                return emit(design, 'design.json')
            supplied = read(local(root, args.record))
            require(isinstance(supplied, dict), 'Approval input must contain reviewer and confirmation')
            allowed = {'reviewer', 'confirmation', 'decision', 'section_ids', 'deletion_ids', 'mode'}
            require(supplied.keys() <= allowed, 'Unknown approval input fields')
            history = [read(local(root, p)) for p in args.design_history]
            assessments = designs.task_assessments(design, task['section_ids'])
            mode = supplied.pop('mode', 'combined' if any(v['complexity'] == 'simple' for v in assessments.values()) else 'design')
            binding = {'code_digest': validation.source_digest(root, profile),
                       'run_refs': [artifact(root, local(root, p)) for p in args.run]} if mode == 'combined' else {}
            result = designs.approval_draft(design, history=history, mode=mode, **binding, **supplied)
            return emit(result, 'approval.json')
        require(args.issue == task['id'], 'Shared draft requires its canonical --issue')
        if args.command == 'design-draft':
            result = coordination.draft_design(args.issue, read(local(root, args.record or args.design)))
        elif args.command == 'approval-draft':
            result = coordination.draft_approval(args.issue, read(local(root, args.record)))
        elif args.command == 'progress':
            result = coordination.progress_draft(root, profile, args.issue, read(local(root, args.progress)), request.directory.name)
        else:
            completed, _ = predecessor_checks(args, root, profile, task, platform['design'])
            result = coordination.draft(root, profile, args.issue, read(local(root, args.progress)),
                                        knowledge.skill_path(args.cs_skill), args.kind, completed_tasks=completed)
        return emit(result, args.command + '.json')
    if args.command == 'design-diff':
        import designs
        require(bool(args.design_history), 'Design diff needs at least the previous snapshot')
        previous = [read(local(root, p)) for p in args.design_history]
        return emit(designs.impact(previous[-1], read(local(root, args.design)),
                    history=previous, changed_paths=validation.changed_paths(root, task)), 'design-diff.json')
    if args.command == 'run':
        tasks = [task] + [read(local(root, p)) for p in args.with_task]
        path, record = validation.run_batch(root, profile, tasks, args.check, request.directory / 'execution', args.portable)
        ok = record['source_unchanged'] and all(r['status'] == 'passed' for r in record['results'])
        return {'ok': ok, 'scope': 'execution-only',
                'artifact': request.publish('run.json', record, args.out) if args.out else artifact(root, path),
                'checks': [{'id': r['id'], 'status': r['status'], 'detail': r['detail']} for r in record['results']],
                **({} if ok else {'problem': 'A check failed or its source/environment changed', 'next_action': 'Inspect per-check original reports, fix the failure and use a new request ID.'})}
    if args.command == 'knowledge-template':
        from knowledge import completion_template
        payload = completion_template(root, profile, task, knowledge.skill_path(args.cs_skill),
                    local(root, args.acceptance) if args.acceptance else None, args.cs_task_id)
        return {**emit(payload, 'cs-input.json'), 'scope': 'draft-only',
                'completion_allowed': payload['task']['status'] == 'completed',
                'summary': '知识草稿已生成；仍需填写实际结果并通过 CS 预览和应用。'}
    if args.command == 'knowledge':
        require(bool(args.acceptance and args.cs_task_id and args.disposition and args.reason and args.brief),
                'knowledge requires --acceptance, --cs-task-id, --brief, --disposition and --reason')
        value = knowledge.finish_v4(root, profile, task, knowledge.skill_path(args.cs_skill), args.cs_task_id,
                    local(root, args.brief), args.disposition, args.reason, local(root, args.acceptance),
                    local(root, args.final_brief) if args.final_brief else None)
        return emit(value, 'knowledge.json')
    if args.command in ('review-template', 'delivery-template'):
        import delivery
        report = report_input(args, root, task)
        result = delivery.review_template(root, profile, task, report) if args.command == 'review-template' else report
        return emit(result, 'review.json' if args.command == 'review-template' else 'delivery.json')
    if args.command == 'verify':
        import delivery
        import issue_history
        report = read(local(root, args.report))
        issue_history.capture(request, task, read(local(root, report['review'])),
            [r['id'] for r in read(local(root, report['design']))['sections']])
        return emit(delivery.verify(root, profile, task, read(local(root, args.report)), args.cs_skill, args.phase), args.phase + '.json')
    raise Invalid('This command does not support v5: ' + args.command)


def status(args, root, profile, task, platform=None):
    if args.report:
        import delivery
        report = read(local(root, args.report))
        _, _, value, _ = delivery.design_material(root, profile, task, report, cached_predecessors(args, root, profile))
        return {**value, 'summary': '已读取方案和材料状态；业务验收与环境尚未重新核查。',
                'delivery': 'not-evaluated', 'business_accepted': False, 'delivery_complete': False, 'closable': False,
                'next_action': 'Run verify with this report to check original results and current environment; status executes no project commands.'}
    if platform:
        import coordination
        value = coordination.resume(root, profile, task['id'], knowledge.skill_path(args.cs_skill), cached_predecessors(args, root, profile))
        return {**value, 'summary': '交接材料可接续，最终交付尚未核查。' if value['ok'] else '交接仍有缺口，按下列原因补齐后接续。'}
    require(args.design is not None, 'Local task status needs --design or --context; provide --report to verify acceptance/delivery')
    import designs
    from coordination import validate_task_design
    design = read(local(root, args.design))
    validate_task_design(task, design)
    value = designs.approval_status(design, [read(local(root, p)) for p in args.approval],
                history=[read(local(root, p)) for p in args.design_history], section_ids=task['section_ids'],
                completed_tasks=cached_predecessors(args, root, profile),
                changed_paths=validation.changed_paths(root, task), code_digest=validation.source_digest(root, profile),
                run_refs=[artifact(root, local(root, p)) for p in args.run])
    ready = value['implementation_ready']
    summary = '可以继续实施；方案、代码与交付仍需实际验收。' if ready else '实施条件尚未满足：需补齐方案批准、决策、分派或前置任务证明。'
    next_action = 'Reuse the existing prepared context; if absent, run prepare with the same plan and approvals to capture the brief, without requesting consent again. Then run checks.' if ready else 'Resolve the named pending sections or predecessor evidence, then prepare again.'
    return {**value, 'summary': summary, 'delivery': 'not-evaluated', 'business_accepted': False,
            'delivery_complete': False, 'closable': False, 'next_action': next_action}
