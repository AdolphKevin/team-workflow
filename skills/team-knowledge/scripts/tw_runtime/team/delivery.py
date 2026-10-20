"""Business acceptance and final delivery are separate read-only decisions."""
from error_codes import Code
import design_files
from tw_runtime.team import platform_script as platform_read
from datetime import datetime
from shlex import quote

from common import (RECORD_SCHEMA, Invalid, artifact, artifact_valid, digest, evidence_file, external_path, inside, obj, read,
                    require, sha, strings, task_valid, text, tool_gate)
import knowledge
import validation
import scenario_acceptance


def evidence(root, profile, item):
    obj(item, {'path', 'sha256'} | ({'repository'} if 'repository' in item else set()),
        {'allow_large_evidence'})
    allow_large = item.get('allow_large_evidence', False)
    require(type(allow_large) is bool, 'Evidence allow_large_evidence must be a boolean')
    if 'repository' not in item:
        ref = {'path': item['path'], 'sha256': item['sha256']}
        return evidence_file(artifact_valid(root, ref), allow_large=allow_large)
    entries = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == item['repository']]
    require(len(entries) == 1, 'Evidence repository is not a declared input')
    target = external_path(root, item['repository'], entries[0])
    path = inside(target, item['path'])
    require(path.is_file() and sha(path) == item['sha256'], 'External evidence changed')
    return evidence_file(path, allow_large=allow_large)


def design_material(root, profile, task, report, completed_tasks=(), *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    import designs
    from coordination import validate_task_design
    design = design_files.read(inside(root, report['design']), workspace=workspace)
    validate_task_design(task, design)
    approvals = [read(inside(root, p)) for p in report['approvals']]
    history = [design_files.read(inside(root, p), workspace=workspace) for p in report.get('design_history', [])]
    refs = [artifact(root, inside(root, p)) for p in report['runs']]
    code = validation.source_digest(root, profile, workspace=workspace)
    selected_refs = None
    if any(row.get('mode') == 'combined' and row.get('code_digest') == code
           and row.get('run_refs') != sorted(refs, key=lambda ref: (ref['path'], ref['sha256'])) for row in approvals):
        try:
            execution = validation.verify_runs(root, profile, task, report['runs'], live=False, workspace=workspace)
            selected_refs = list({path: artifact(root, inside(root, path)) for path in execution['selected_runs'].values()}.values())
        except (Invalid, OSError, ValueError, TypeError, KeyError):
            pass  # Missing required execution never supplies an alternate approval binding.
    status = designs.approval_status(design, approvals, history=history,
                                     root=root, profile=profile,
                                     section_ids=task['section_ids'],
                                     completed_tasks=completed_tasks,
                                     changed_paths=validation.changed_paths(root, task, profile, design, workspace=workspace),
                                     code_digest=code, run_refs=refs, selected_run_refs=selected_refs, workspace=workspace)
    fingerprints = designs.fingerprints(design)['sections']
    selected = {key: fingerprints[key] for key in task['section_ids']}
    return design, approvals, status, selected


def design_problem(status):
    """Name what blocks the design, instead of dumping the whole status."""
    parts = list(status.get('gaps', []))
    scope = status.get('scope', {})
    if scope.get('unmapped'):
        names = scope['unmapped']
        parts.append('请为这些文件确定归属：' + '、'.join(names[:10])
                     + (f'等 {len(names)} 个文件' if len(names) > 10 else '')
                     + '；本机文件加入项目 .gitignore；项目文件纳入任务范围')
    if scope.get('outside_selection'):
        parts.append('changed files belong to sections not selected by this task: ' + ', '.join(scope['outside_selection'][:10]))
    for key in ('missing', 'stale'):
        if status.get(key):
            parts.append(f'{key} approval for sections: ' + ', '.join(status[key]))
    if status.get('required_pending_decisions'):
        parts.append('pending decisions: ' + ', '.join(str(v) for v in status['required_pending_decisions']))
    if not status.get('history_complete', True):
        parts.append('design history is incomplete; pass earlier revisions with --design-history')
    if status.get('combined_complete') is False:
        parts.append('当前任务的合并批准尚待补齐')
    return '; '.join(parts) or 'design review is incomplete'


def passed(row, label):
    require(isinstance(row, dict) and row.get('status') == 'passed', f'{label} has not passed')
    text(row.get('summary'))


def review_template(root, profile, task, report, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    design, _, _, selected = design_material(root, profile, task, report, workspace=workspace)
    import issue_history
    known = {v['id']: v for v in issue_history.known(root, task['id'])}
    known.update({v['id']: v for v in design.get('issues', [])})
    _, state = scenario_acceptance.current(root, profile, task, design, report['runs'], workspace=workspace)
    known.update({v['id']: v for v in scenario_acceptance.findings(state, list(known.values()), design, task)})
    pending = {'status': 'pending', 'summary': '', 'evidence': []}
    return {'data_version': RECORD_SCHEMA, 'kind': 'review', 'task_id': task['id'],
            'task_digest': digest(task), 'source_digest': validation.source_digest(root, profile, workspace=workspace),
            'validation_policy': review_policy(root, profile, task),
            **scenario_acceptance.bindings(state), 'sections': selected, 'reviewer': '', 'standards': dict(pending), 'spec': dict(pending),
            'risks': task['risks'], 'knowledge_conflicts_resolved': False,
            'acceptance': [{'id': a['id'], **pending, 'observations': []} for a in task['acceptance']],
            'findings': list(known.values())}


def review_policy(root, profile, task):
    required = task_valid(task, profile, root)
    return {'checks': {key: digest(profile['checks'][key]) for key in required},
            'risk_checks': {risk: sorted(profile['risk_checks'].get(risk, [])) for risk in sorted(task['risks'])}}


def check_review_format(root, profile, task, review, selected, design, *, workspace=None):
    workspace = workspace or validation.Workspace(root, profile)
    require(review.get('data_version') == RECORD_SCHEMA and review.get('kind') == 'review',
            f'Expected a schema {RECORD_SCHEMA} code review; regenerate and submit it with review')
    require(review.get('task_digest') == digest(task) and review.get('task_id') == task['id'], 'Review belongs to another task/version')
    require(review.get('source_digest') == validation.source_digest(root, profile, workspace=workspace), 'Review does not cover current source', error_code=Code.SOURCE_STALE)
    require(review.get('sections') == selected, 'Review does not cover current approved sections')
    require(review.get('validation_policy') == review_policy(root, profile, task), 'Review must cover current validation policy')
    text(review.get('reviewer'))
    for label in ('standards', 'spec'):
        row = review.get(label)
        require(isinstance(row, dict) and row.get('status') in ('passed', 'failed'), label + ' has not passed: conclusion must be passed or failed',
                section={'standards': '规范 standards', 'spec': '需求 spec'}[label])
        text(row.get('summary'))
        require(bool(row.get('evidence')), 'Review needs actual evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
    _, state = scenario_acceptance.current(root, profile, task, design, workspace=workspace)
    require(all(review.get(key) == value for key, value in scenario_acceptance.bindings(state).items()),
            '评审所用场景文件或轮次已变化，请重新复核', error_code=Code.REVIEW_BINDING_STALE)
    require(review.get('risks') == task['risks'], 'Review must assess the current risks')
    require(type(review.get('knowledge_conflicts_resolved')) is bool, 'Knowledge conflict disposition must be specified')
    from contracts import reconcile, issues
    import issue_history
    issues(review.get('findings', []), [r['id'] for r in design['sections']])
    reconcile(design['issues'], review.get('findings', []))
    reconcile(issue_history.known(root, task['id']), review.get('findings', []))
    assessed = set()
    for row in review.get('acceptance', []):
        strings(row.get('cases', []))
        require(row.get('status') in ('passed', 'failed'), 'Acceptance conclusion must be passed or failed')
        text(row.get('summary'))
        require(row['id'] not in assessed and bool(row.get('evidence')), 'Duplicate acceptance or missing evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
        assessed.add(row['id'])
    require(assessed == {r['id'] for r in task['acceptance']}, 'Acceptance coverage mismatch')


def review_failures(review, required):
    from contracts import unresolved
    failed = [{'kind': key, 'id': key, 'reason': review[key]['summary']}
              for key in ('standards', 'spec') if review[key]['status'] != 'passed']
    failed += [{'kind': 'acceptance', 'id': row['id'], 'reason': row['summary']}
               for row in review['acceptance'] if row['status'] != 'passed']
    failed += [{'kind': 'issue', 'id': row['id'], 'reason': row['summary'], 'owner': row['owner'],
                'affects': row['affects'], 'blocks': row['blocks']}
               for row in unresolved(review['findings'], required, 'acceptance')]
    if not review['knowledge_conflicts_resolved']:
        failed.append({'kind': 'knowledge', 'id': 'knowledge_conflicts_resolved', 'reason': '知识冲突尚未处理'})
    return failed


class ReviewBlocked(Invalid):
    error_code = Code.REVIEW_NOT_PASSED

    def __init__(self, task, failures):
        import shlex
        self.review_failures = failures
        self.next_action = ('修复所列问题后重跑检查：tw team run --task ' + shlex.quote(task['id'])
                            + '；再逐项复核：tw team review --task ' + shlex.quote(task['id']))
        names = {'standards': '规范 standards', 'spec': '需求 spec', 'acceptance': '验收', 'issue': '问题', 'knowledge': '知识'}
        super().__init__('评审未通过：' + '；'.join(names[row['kind']] + ' ' + row['id'] + '：' + row['reason'] for row in failures))


class ReviewCaseError(Invalid):
    def __init__(self, identifier, case):
        super().__init__('验收 ' + identifier + ' 用例不存在或未通过：' + case)


def review_case_failures(review, execution):
    failures = []
    for row in review['acceptance']:
        passed = set()
        for observation in row.get('observations', []):
            key = observation.get('check')
            if observation.get('kind') == 'execution' and observation.get('run', {}).get('path') == execution['selected_runs'].get(key):
                passed.update(case for case, outcome in execution['results'].get(key, {}).get('cases', {}).items() if outcome == 'passed')
        missing = [case for case in row.get('cases', []) if case not in passed]
        if missing:
            failures.append({'kind': 'case', 'id': row['id'], 'reason': '用例不存在或未通过：' + '、'.join(missing)})
    return failures


def require_review_passed(task, review, required):
    failures = review_failures(review, required)
    if failures:
        raise ReviewBlocked(task, failures)


def check_review(root, profile, task, review, selected, design, status, execution, run_paths, *, workspace=None):
    check_review_format(root, profile, task, review, selected, design, workspace=workspace)
    from contracts import independent
    independent(design, review['reviewer'], 'Reviewer')
    require_review_passed(task, review, status['required_sections'])
    for row in review['acceptance']:
        check_observations(root, profile, design, row, execution, run_paths)
        refs = [item for item in row.get('observations', []) if item.get('kind') == 'scenarios']
        require(len(refs) == 1 and refs[0].get('rounds') == review['scenario_rounds'], '验收观察引用评审所用的场景轮次')


def verify(root, profile, task, report, phase='delivery', _seen=None, live=None, *, workspace=None):
    """live: re-run environment identity commands. Only the first acceptance does; later checks of the
    same acceptance at delivery rely on the environment it recorded, so a removed fixture
    no longer invalidates finished evidence. Source, definitions, reviews and platform are always rechecked."""
    workspace = workspace or validation.Workspace(root, profile)
    import designs
    import coordination
    from common import now
    require(phase in ('acceptance', 'delivery'), 'Unknown verification phase')
    live = phase == 'acceptance' if live is None else live
    tool = tool_gate()
    obj(report, {'data_version', 'task_id', 'design', 'approvals', 'brief', 'runs', 'review'},
        {'acceptance', 'knowledge', 'design_history', 'close_authorization', 'dependencies'},
        error_code=Code.REPORT_INCOMPLETE)
    import task_inputs
    task = task_inputs.expand(task, design_files.read(inside(root, report['design']), workspace=workspace))
    task_valid(task, profile, root)
    require(report['data_version'] == RECORD_SCHEMA and report['task_id'] == task['id'],
            f'Expected a schema {RECORD_SCHEMA} delivery report for this task; regenerate it with delivery-template', error_code=Code.REPORT_INCOMPLETE)
    strings(report['runs'])
    strings(report['approvals'])
    import issue_history
    issues_before = digest(issue_history.known(root, task['id']))
    before = validation.source_digest(root, profile, workspace=workspace)
    platform_state = None
    if platform_read.is_task(root, task['id']):
        platform_state = coordination.load(task['id'], root=root)
        require(not platform_state['gaps'], 'Platform records are incomplete: ' + '; '.join(platform_state['gaps']))
        import task_inputs
        require(task_inputs.written(platform_state['task']) == task_inputs.written(task),
                'Platform task changed; read current requirements')
    if platform_state is not None:
        from contracts import reconcile
        reconcile(platform_state.get('known_issues', []), read(inside(root, report['review'])).get('findings', []))
    seen = set(_seen or ())
    identity = (task['id'], tuple(sorted(task['section_ids'])))
    require(identity not in seen, 'Acceptance dependency cycle')
    seen.add(identity)
    completed_tasks, dependency_materials = set(), []
    for dependency in report.get('dependencies', []):
        obj(dependency, {'section', 'task', 'report'})
        dep_task_path, dep_report_path = inside(root, dependency['task']), inside(root, dependency['report'])
        dep_task, dep_report = read(dep_task_path), read(dep_report_path)
        require(dependency['section'] in dep_task.get('section_ids', []), 'Dependency evidence belongs to another section')
        proof = verify(root, profile, dep_task, dep_report, 'acceptance', seen, live, workspace=workspace)
        current_design = design_files.read(inside(root, report['design']), workspace=workspace)
        require(dep_task.get('design_id') == task['design_id'] and proof['sections'][dependency['section']]
                == designs.fingerprints(current_design)['sections'][dependency['section']], 'Dependency uses a different plan section')
        completed_tasks.add(dependency['section'])
        dependency_materials += [artifact(root, dep_task_path), artifact(root, dep_report_path), *proof['materials']]
    design, approvals, status, selected = design_material(root, profile, task, report, completed_tasks, workspace=workspace)
    review = read(inside(root, report['review']))
    if platform_state is not None:
        require(platform_state['design'] == design, 'Local design differs from the shared plan')
        import reviews
        published = reviews.published_approval(root, task['id'], review)
        require(all(a in platform_state['approvals'] or a == published for a in approvals), '批准记录尚待在平台任务上共享',
                error_code=Code.APPROVAL_NOT_SHARED,
                next_action=reviews.submission_action(root, task['id'],
                    reviews.case_repair(root, task['id'], artifact(root, inside(root, report['review'])))['review_file']))
    scenario_group, scenario_state = scenario_acceptance.current(root, profile, task, design, report['runs'], workspace=workspace)
    from contracts import unsourced
    missing = unsourced(task, design)
    require(not missing, 'Acceptance scenario needs confirmed business sources: ' + ', '.join(missing))
    if review.get('source_digest') == before:
        scenario_acceptance.check(root, profile, task, design, review, scenario_group, scenario_state, workspace=workspace)
    try:
        check_review_format(root, profile, task, review, selected, design, workspace=workspace)
    except Invalid as exc:
        import shlex
        incomplete = Invalid('Current approval/review materials are incomplete: ' + str(exc),
                             error_code=Code.SOURCE_STALE if exc.error_code == Code.SOURCE_STALE else Code.REVIEW_MATERIALS_INCOMPLETE,
                             **{key: getattr(exc, key) for key in ('section', 'line') if hasattr(exc, key)})
        selected_task = '--task ' + shlex.quote(task['id'])
        incomplete.next_action = '重跑检查并复核当前材料：tw team run ' + selected_task + '；tw team review ' + selected_task
        raise incomplete from exc
    else:
        require_review_passed(task, review, status['required_sections'])
        from contracts import independent
        independent(design, review['reviewer'], 'Reviewer')
    require(status.get('local_review_valid') is True, 'Design coverage/history needs review: ' + design_problem(status),
            error_code=status.get('error_code') or (Code.APPROVAL_INCOMPLETE if status.get('missing') or status.get('stale')
                or status.get('combined_complete') is False else Code.INVALID))
    require(status.get('acceptance_ready') is True, '方案的验收条件尚待补齐：' + design_problem(status),
            error_code=Code.DESIGN_INPUT,
            next_action='补齐方案中的职责、待定事项与前置任务材料后重新开工：tw team start --task '
                        + quote(task['id']) + ' --design ' + quote(report['design'])
                        + ' --root ' + quote(str(root)))
    execution = validation.verify_runs(root, profile, task, report['runs'], live=live, workspace=workspace)
    initial = read(inside(root, report['brief']))
    require(initial.get('data_version') == RECORD_SCHEMA and initial.get('kind') == 'knowledge-brief'
            and initial.get('task_id') == task['id'] and initial.get('task_digest') == digest(task),
            'Initial knowledge reading is missing or belongs to another task/version')
    reused = []
    for record in execution['records']:
        if record.get('task_digests', {}).get(task['id']) == digest(task):
            require(datetime.fromisoformat(initial['at']) <= datetime.fromisoformat(record['started_at']),
                    'Knowledge was first captured after execution; repeat affected review and validation')
        else:
            reused.append({'id': record.get('id'), 'started_at': record['started_at'],
                           'reason': 'Existing result independently checked against current inputs; not a claim of earlier knowledge reading'})
    review = read(inside(root, report['review']))
    run_paths = [inside(root, p).relative_to(root).as_posix() for p in report['runs']]
    try:
        check_review(root, profile, task, review, selected, design, status, execution, run_paths, workspace=workspace)
    except ReviewCaseError as exc:
        import reviews
        repair = reviews.case_repair(root, task['id'], artifact(root, inside(root, report['review'])))
        exc.next_action, exc.review_file = repair['next_action'], repair['review_file']
        raise
    from execution import output_excerpt
    materials = [artifact(root, inside(root, report[p])) for p in ('design', 'brief', 'review')]
    materials += [artifact(root, inside(root, p)) for p in report['approvals'] + report['runs'] + report.get('design_history', [])]
    materials += dependency_materials + scenario_state['scenario_rounds']
    materials += [ref for row in scenario_state['scenarios'] for ref in row.get('result', {}).get('evidence', [])]
    verification = {row['id']: row['data'].get('verification') for row in design['sections'] if row['type'] == 'acceptance'}
    named_cases = {row['id']: sorted(set(verification[row['id']]['cases']) | set(row.get('cases', [])))
                   for row in review['acceptance'] if verification[row['id']] is not None}
    result = {'data_version': RECORD_SCHEMA, 'kind': 'acceptance' if phase == 'acceptance' else 'delivery-verification',
              'ok': True, 'at': now(), 'phase': phase, 'task_id': task['id'], 'task_digest': digest(task),
              **scenario_acceptance.bindings(scenario_state),
              'summary_counts': scenario_state['summary_counts'], 'statistics': scenario_state['statistics'],
              'source_digest': before, 'sections': selected, 'checks': execution['checks'], 'materials': materials,
              'ci_verified_checks': sorted(key for key, path in execution['selected_runs'].items()
                                           if read(inside(root, path)).get('kind') == 'imported-execution'),
              'scope': 'business-acceptance' if phase == 'acceptance' else 'team-delivery',
              'acceptance_scope': task['acceptance_scope'], 'report': dict(report), 'issues': review['findings'],
              'observations': {r['id']: r['observations'] for r in review['acceptance']},
              'named_cases': named_cases, 'unspecified_cases': [key for key, cases in named_cases.items() if not cases],
              'business_accepted': True, 'delivery_complete': False, 'closable': False,
              'unverified_scope': scenario_acceptance.unverified_scope(scenario_state, review['findings']),
              'reused_execution': reused, 'tool': tool,
              'superseded_execution': execution['superseded'],
              're_evaluated': [{'check': key, **row['evaluation']} for key, row in sorted(execution['results'].items())
                               if row.get('evaluation')],
              'environment': {key: row.get('binding', {}).get('environment')
                              for key, row in sorted(execution['results'].items())},
              'environment_checked': 'now' if live else 'recorded at acceptance',
              'output_excerpts': {key: output_excerpt(root, row['artifacts']) for key, row in execution['results'].items()},
              'assurance': 'content-bound records and explicit reviews; delivery_complete covers scenario acceptance '
                           'on the current product, knowledge and handoff records; not signed or exhaustive business proof'}
    if phase == 'delivery':
        publication_verified = platform_state is None
        authorization = report.get('close_authorization')
        if authorization:
            try:
                obj(authorization, {'confirmed_by', 'reference'})
                text(authorization['confirmed_by']); text(authorization['reference'])
            except Invalid as exc:
                import shlex
                invalid = Invalid('关闭授权 close_authorization 不完整：' + str(exc))
                invalid.error_code = Code.CLOSE_AUTHORIZATION
                invalid.next_action = ('在新报告副本中补齐 confirmed_by 和 reference，再核对：tw team verify --task '
                                       + shlex.quote(task['id']) + ' --report <修正后的报告路径>')
                raise invalid from exc
        require(bool(report.get('acceptance')),
                '交付报告的 acceptance 尚缺业务验收记录', error_code=Code.ACCEPTANCE_MISSING)
        acceptance_path = inside(root, report['acceptance'])
        accepted = read(acceptance_path)
        require(accepted.get('data_version') == RECORD_SCHEMA and accepted.get('kind') == 'acceptance'
                and accepted.get('business_accepted') is True, '交付报告的 acceptance 不是通过的业务验收记录', error_code=Code.REPORT_INCOMPLETE)
        require(accepted.get('task_id') == task['id'],
                '业务验收记录属于其他任务或任务已经改动', error_code=Code.REPORT_INCOMPLETE)
        require(accepted.get('task_digest') == digest(task),
                '业务验收记录属于其他任务或任务已经改动', error_code=Code.ACCEPTANCE_STALE)
        require(accepted.get('sections') == selected, '业务验收之后方案章节已变化，需要重新验收', error_code=Code.ACCEPTANCE_STALE)
        require(accepted.get('source_digest') == before, '业务验收之后源码已变化，需要重新验收', error_code=Code.ACCEPTANCE_STALE)
        require(all(accepted.get(key) == value for key, value in scenario_acceptance.bindings(scenario_state).items()),
                '业务验收之后场景文件或轮次已变化，需要重新验收', error_code=Code.ACCEPTANCE_STALE)
        require(contents(accepted.get('materials')) == contents(result['materials']),
                '业务验收之后执行、评审、批准或方案材料已变化，需要用当前材料重新验收', error_code=Code.ACCEPTANCE_STALE)
        result['environment'] = accepted.get('environment', result['environment'])
        result['materials'].append(artifact(root, acceptance_path))
        completed = knowledge.verify(root, report.get('knowledge'), task.get('base'))
        result['knowledge'] = completed
        result['materials'].extend(artifact(root, inside(root, name)) for name in completed['files']
                                   if inside(root, name, exists=False).is_file())
        if platform_state is not None:
            import summary
            posted = platform_state.get('current')
            published = bool(posted and posted.get('handoff_kind') in ('implementation', 'close') and not posted.get('remaining'))
            close = {'acceptance': artifact(root, acceptance_path), 'knowledge': completed,
                     'summary': summary.render({**result, 'delivery_complete': True, 'closable': bool(report.get('close_authorization') and published),
                                                'close_authorization': report.get('close_authorization', {}),
                                                'knowledge_disposition': summary.disposition(completed)}, task, profile)}
            if report.get('close_authorization'):
                close['close_authorization'] = report['close_authorization']
            current, note = coordination.closing(root, profile, task['id'], completed_tasks, close, review['findings'], workspace=workspace)
            publication_verified = note is None
            from contracts import reconcile, unresolved
            reconcile(review['findings'], current.get('questions', []))
            require(not unresolved(current.get('questions', []), status['required_sections'], 'acceptance'),
                    'Handoff still has unresolved issues')
            if note is not None:
                result['close_note'] = {k: note[k] for k in ('record', 'markdown', 'publication')}
        result['delivery_complete'] = True
        from artifacts import directory
        requests = directory(root, task['id']).parent
        result['covered_requests'] = [artifact(root, path) for path in sorted(requests.glob('*/request.json'))
                                      if read(path).get('task_id') == task['id']]
        if authorization:
            result['closable'] = publication_verified
            result['close_authorization'] = authorization
    import summary
    result.update(summary.delivery_status(result))
    result['summary_markdown'] = summary.render({**result, 'knowledge_disposition': (
        summary.disposition(completed) if phase == 'delivery' else None)}, task, profile)
    if platform_state is not None:
        latest = coordination.load(task['id'], root=root)
        observed = ('requirements', 'history_digest', 'design_requirements', 'design_history_digest', 'owners')
        require(all(latest[key] == platform_state[key] for key in observed) and not latest['gaps'],
                'Platform requirements, approvals or progress changed during verification', error_code=Code.PLATFORM_CHANGED)
    require(digest(issue_history.known(root, task['id'])) == issues_before, 'Known issues changed during verification')
    workspace.refresh()
    require(scenario_acceptance.bindings(scenario_acceptance.current(root, profile, task, design, report['runs'], workspace=workspace)[1])
            == scenario_acceptance.bindings(scenario_state), '验收期间场景文件或轮次已变化', error_code=Code.ACCEPTANCE_STALE)
    require(validation.source_digest(root, profile, workspace=workspace) == before, 'Source changed during verification', error_code=Code.SOURCE_STALE)
    return result


def contents(materials):
    """The same files by content: saving an identical copy elsewhere or reordering keeps an acceptance."""
    if not (isinstance(materials, list) and all(isinstance(m, dict) for m in materials)):
        return None
    return sorted(str(m.get('sha256')) for m in materials)


def check_observations(root, profile, design, row, execution, run_paths):
    """检查核对自身覆盖，场景轮次承担业务入口的验收。"""
    from contracts import match_coverage
    section = next((s for s in design['sections'] if s['id'] == row['id']), None)
    require(section is not None, 'Unknown acceptance observation')
    requirement = section['data'].get('verification')
    observations = row.get('observations')
    require(isinstance(observations, list) and bool(observations), '验收需要检查或场景轮次观察')
    cases = set()
    if requirement is not None:
        checks = section['data']['checks']
        for key in checks:
            require(execution['results'].get(key, {}).get('status') == 'passed', 'Check did not pass: ' + key)
            require('coverage' in profile['checks'][key], '检查缺少覆盖声明：' + key)
            match_coverage(requirement, profile['checks'][key]['coverage'])
    for observation in observations:
        if observation.get('kind') == 'scenarios':
            obj(observation, {'kind', 'rounds'})
            for ref in observation['rounds']:
                artifact_valid(root, ref)
            continue
        require(observation.get('kind') == 'execution', '观察种类填写 execution 或 scenarios；人工执行用 tw team scenarios submit 登记')
        require(requirement is not None, '检查为无的验收项使用 scenarios 观察')
        obj(observation, {'kind', 'run', 'check', 'cases'})
        ref = observation['run']
        path = artifact_valid(root, ref)
        require(path.relative_to(root).as_posix() in run_paths, 'Observation run was not verified for this task')
        key = observation['check']
        require(key in section['data']['checks'] and key in execution['results'], 'Observation check does not cover this acceptance')
        require(path.relative_to(root).as_posix() == execution['selected_runs'][key],
                'Observation must reference the selected execution for this check')
        record = read(path)
        identifiers = [r['id'] for r in record.get('results', [])] if record['kind'] == 'execution' else [record['result']['id']]
        require(key in identifiers, 'Observation check belongs to another run')
        result = execution['results'][key]
        strings(observation['cases'])
        for case in observation['cases']:
            require(result.get('cases', {}).get(case) == 'passed', 'Observed case is missing, failed or skipped: ' + case)
        cases.update(case for case, outcome in result.get('cases', {}).items() if outcome == 'passed')
    for case in sorted(set((requirement or {}).get('cases', [])) | set(row.get('cases', []))):
        if case not in cases and case in row.get('cases', []):
            raise ReviewCaseError(row['id'], case)
        require(case in cases, '验收 ' + row['id'] + ' 用例不存在或未通过：' + case)
