"""Business acceptance and final delivery are separate read-only decisions."""
from tw_runtime.team import platform_script as platform_read
from datetime import datetime

from common import (RECORD_SCHEMA, Invalid, artifact, artifact_valid, digest, evidence_file, external_path, inside, obj, read,
                    require, sha, strings, task_valid, text, tool_gate)
import knowledge
import validation


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


def design_material(root, profile, task, report, completed_tasks=()):
    import designs
    from coordination import validate_task_design
    design = read(inside(root, report['design']))
    validate_task_design(task, design)
    approvals = [read(inside(root, p)) for p in report['approvals']]
    history = [read(inside(root, p)) for p in report.get('design_history', [])]
    refs = [artifact(root, inside(root, p)) for p in report['runs']]
    code = validation.source_digest(root, profile)
    selected_refs = None
    if any(row.get('mode') == 'combined' and row.get('code_digest') == code
           and row.get('run_refs') != sorted(refs, key=lambda ref: (ref['path'], ref['sha256'])) for row in approvals):
        try:
            execution = validation.verify_runs(root, profile, task, report['runs'], live=False)
            selected_refs = list({path: artifact(root, inside(root, path)) for path in execution['selected_runs'].values()}.values())
        except (Invalid, OSError, ValueError, TypeError, KeyError):
            pass  # Missing required execution never supplies an alternate approval binding.
    status = designs.approval_status(design, approvals, history=history,
                                     section_ids=task['section_ids'],
                                     completed_tasks=completed_tasks,
                                     changed_paths=validation.changed_paths(root, task, profile),
                                     code_digest=code, run_refs=refs, selected_run_refs=selected_refs)
    fingerprints = designs.fingerprints(design)['sections']
    selected = {key: fingerprints[key] for key in task['section_ids']}
    return design, approvals, status, selected


def design_problem(status):
    """Name what blocks the design, instead of dumping the whole status."""
    parts = list(status.get('gaps', []))
    scope = status.get('scope', {})
    if scope.get('unmapped'):
        parts.append('changed files outside every task section scope (add them, tests included, to a task scope): '
                     + ', '.join(scope['unmapped'][:10]))
    if scope.get('outside_selection'):
        parts.append('changed files belong to sections not selected by this task: ' + ', '.join(scope['outside_selection'][:10]))
    for key in ('missing', 'stale'):
        if status.get(key):
            parts.append(f'{key} approval for sections: ' + ', '.join(status[key]))
    if status.get('required_pending_decisions'):
        parts.append('pending decisions: ' + ', '.join(str(v) for v in status['required_pending_decisions']))
    if not status.get('history_complete', True):
        parts.append('design history is incomplete; pass earlier revisions with --design-history')
    return '; '.join(parts) or 'design review is incomplete'


def passed(row, label):
    require(isinstance(row, dict) and row.get('status') == 'passed', f'{label} has not passed')
    text(row.get('summary'))


def review_template(root, profile, task, report):
    design, _, _, selected = design_material(root, profile, task, report)
    import issue_history
    known = {v['id']: v for v in issue_history.known(root, task['id'])}
    known.update({v['id']: v for v in design.get('issues', [])})
    pending = {'status': 'pending', 'summary': '', 'evidence': []}
    return {'data_version': RECORD_SCHEMA, 'kind': 'review', 'task_id': task['id'],
            'task_digest': digest(task), 'source_digest': validation.source_digest(root, profile),
            'validation_policy': review_policy(root, profile, task),
            'sections': selected, 'reviewer': '', 'standards': dict(pending), 'spec': dict(pending),
            'risks': task['risks'], 'knowledge_conflicts_resolved': False,
            'acceptance': [{'id': a['id'], **pending, 'observations': []} for a in task['acceptance']],
            'findings': list(known.values())}


def review_policy(root, profile, task):
    required = task_valid(task, profile, root)
    return {'checks': {key: digest(profile['checks'][key]) for key in required},
            'risk_checks': {risk: sorted(profile['risk_checks'][risk]) for risk in sorted(task['risks'])}}


def check_review_format(root, profile, task, review, selected, design):
    require(review.get('data_version') == RECORD_SCHEMA and review.get('kind') == 'review',
            f'Expected a schema {RECORD_SCHEMA} code review; regenerate and submit it with review')
    require(review.get('task_digest') == digest(task) and review.get('task_id') == task['id'], 'Review belongs to another task/version')
    require(review.get('source_digest') == validation.source_digest(root, profile), 'Review does not cover current source')
    require(review.get('sections') == selected, 'Review does not cover current approved sections')
    require(review.get('validation_policy') == review_policy(root, profile, task), 'Review must cover current validation policy')
    text(review.get('reviewer'))
    for label in ('standards', 'spec'):
        row = review.get(label)
        require(isinstance(row, dict) and row.get('status') in ('passed', 'failed'), label + ' has not passed: conclusion must be passed or failed')
        text(row.get('summary'))
        require(bool(row.get('evidence')), 'Review needs actual evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
    require(review.get('risks') == task['risks'], 'Review must assess the current risks')
    require(type(review.get('knowledge_conflicts_resolved')) is bool, 'Knowledge conflict disposition must be specified')
    from contracts import reconcile, issues
    import issue_history
    issues(review.get('findings', []), [r['id'] for r in design['sections']])
    reconcile(design['issues'], review.get('findings', []))
    reconcile(issue_history.known(root, task['id']), review.get('findings', []))
    assessed = set()
    for row in review.get('acceptance', []):
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
    error_code = 'review-not-passed'

    def __init__(self, task, failures):
        import shlex
        self.review_failures = failures
        self.next_action = ('修复所列问题后重跑检查：tw team run --task ' + shlex.quote(task['id'])
                            + '；再逐项复核：tw team review --task ' + shlex.quote(task['id']))
        names = {'standards': '规范 standards', 'spec': '需求 spec', 'acceptance': '验收', 'issue': '问题', 'knowledge': '知识'}
        super().__init__('评审未通过：' + '；'.join(names[row['kind']] + ' ' + row['id'] + '：' + row['reason'] for row in failures))


def require_review_passed(task, review, required):
    failures = review_failures(review, required)
    if failures:
        raise ReviewBlocked(task, failures)


def check_review(root, profile, task, review, selected, design, status, execution, run_paths):
    check_review_format(root, profile, task, review, selected, design)
    from contracts import independent
    independent(design, review['reviewer'], 'Reviewer')
    require_review_passed(task, review, status['required_sections'])
    for row in review['acceptance']:
        check_observations(root, profile, design, row, execution, run_paths)


def verify(root, profile, task, report, phase='delivery', _seen=None, live=None):
    """live: re-run environment identity commands. Only the first acceptance does; later checks of the
    same acceptance at delivery rely on the environment it recorded, so a removed fixture
    no longer invalidates finished evidence. Source, definitions, reviews and platform are always rechecked."""
    import designs
    import coordination
    from common import now
    require(phase in ('acceptance', 'delivery'), 'Unknown verification phase')
    live = phase == 'acceptance' if live is None else live
    tool = tool_gate()
    task_valid(task, profile, root)
    obj(report, {'data_version', 'task_id', 'design', 'approvals', 'brief', 'runs', 'review'},
        {'acceptance', 'knowledge', 'design_history', 'close_authorization', 'dependencies', 'automation'})
    require(report['data_version'] == RECORD_SCHEMA and report['task_id'] == task['id'],
            f'Expected a schema {RECORD_SCHEMA} delivery report for this task; regenerate it with delivery-template')
    strings(report['runs'])
    strings(report['approvals'])
    import issue_history
    issues_before = digest(issue_history.known(root, task['id']))
    before = validation.source_digest(root, profile)
    platform_state = None
    if platform_read.is_task(root, task['id']):
        platform_state = coordination.load(task['id'], root=root)
        require(not platform_state['gaps'], 'Platform records are incomplete: ' + '; '.join(platform_state['gaps']))
        require(platform_state['task'] == task, 'Platform task changed; read current requirements')
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
        proof = verify(root, profile, dep_task, dep_report, 'acceptance', seen, live)
        current_design = read(inside(root, report['design']))
        require(dep_task.get('design_id') == task['design_id'] and proof['sections'][dependency['section']]
                == designs.fingerprints(current_design)['sections'][dependency['section']], 'Dependency uses a different plan section')
        completed_tasks.add(dependency['section'])
        dependency_materials += [artifact(root, dep_task_path), artifact(root, dep_report_path), *proof['materials']]
    design, approvals, status, selected = design_material(root, profile, task, report, completed_tasks)
    review = read(inside(root, report['review']))
    if platform_state is not None:
        require(platform_state['design'] == design, 'Local design differs from the shared plan')
        require(all(a in platform_state['approvals'] for a in approvals), 'Approval has not been shared on the task')
    from contracts import unsourced
    missing = unsourced(task, design)
    require(not missing, 'Acceptance scenario needs confirmed business sources: ' + ', '.join(missing))
    try:
        check_review_format(root, profile, task, review, selected, design)
    except Invalid as exc:
        import shlex
        incomplete = Invalid('Current approval/review materials are incomplete: ' + str(exc))
        selected_task = '--task ' + shlex.quote(task['id'])
        incomplete.next_action = '重跑检查并复核当前材料：tw team run ' + selected_task + '；tw team review ' + selected_task
        raise incomplete from exc
    else:
        require_review_passed(task, review, status['required_sections'])
        from contracts import independent
        independent(design, review['reviewer'], 'Reviewer')
    require(status.get('local_review_valid') is True, 'Design coverage/history needs review: ' + design_problem(status))
    require(status.get('acceptance_ready') is True, 'Current design/code approval is missing: ' + design_problem(status))
    execution = validation.verify_runs(root, profile, task, report['runs'], live=live)
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
    check_review(root, profile, task, review, selected, design, status, execution, run_paths)
    from contracts import automation
    regression = automation(report['automation'], task, review['findings'], profile, execution) if 'automation' in report else 'not-declared'
    materials = [artifact(root, inside(root, report[p])) for p in ('design', 'brief', 'review')]
    materials += [artifact(root, inside(root, p)) for p in report['approvals'] + report['runs'] + report.get('design_history', [])]
    materials += dependency_materials
    result = {'data_version': RECORD_SCHEMA, 'kind': 'acceptance' if phase == 'acceptance' else 'delivery-verification',
              'ok': True, 'at': now(), 'phase': phase, 'task_id': task['id'], 'task_digest': digest(task),
              'source_digest': before, 'sections': selected, 'checks': execution['checks'], 'materials': materials,
              'scope': 'business-acceptance' if phase == 'acceptance' else 'team-delivery',
              'acceptance_scope': task['acceptance_scope'], 'report': dict(report), 'issues': review['findings'],
              'observations': {r['id']: r['observations'] for r in review['acceptance']},
              'business_accepted': True, 'delivery_complete': False, 'closable': False,
              'reused_execution': reused, 'automation_status': regression, 'tool': tool,
              'superseded_execution': execution['superseded'],
              're_evaluated': [{'check': key, **row['evaluation']} for key, row in sorted(execution['results'].items())
                               if row.get('evaluation')],
              'environment': {key: row.get('binding', {}).get('environment')
                              for key, row in sorted(execution['results'].items())},
              'environment_checked': 'now' if live else 'recorded at acceptance',
              'regression_pending': regression != 'not-declared' and bool(regression['pending_automation']),
              'assurance': 'content-bound records and explicit reviews; delivery_complete covers acceptance, knowledge '
                           'and handoff records, not regression automation (see automation_status); '
                           'not signed or exhaustive business proof'}
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
                invalid.error_code = 'close-authorization-incomplete'
                invalid.next_action = ('在新报告副本中补齐 confirmed_by 和 reference，再核对：tw team verify --task '
                                       + shlex.quote(task['id']) + ' --report <修正后的报告路径>')
                raise invalid from exc
        require(bool(report.get('acceptance')),
                '最终交付需要业务验收记录：先运行 tw team accept，再把产物路径写进交付报告的 acceptance')
        acceptance_path = inside(root, report['acceptance'])
        accepted = read(acceptance_path)
        require(accepted.get('data_version') == RECORD_SCHEMA and accepted.get('kind') == 'acceptance'
                and accepted.get('business_accepted') is True, '交付报告的 acceptance 不是通过的业务验收记录')
        require(accepted.get('task_id') == task['id'] and accepted.get('task_digest') == digest(task),
                '业务验收记录属于其他任务或任务已经改动')
        require(accepted.get('sections') == selected, '业务验收之后方案章节已变化，需要重新验收')
        require(accepted.get('source_digest') == before, '业务验收之后源码已变化，需要重新验收')
        require(contents(accepted.get('materials')) == contents(result['materials']),
                '业务验收之后执行、评审、批准或方案材料已变化，需要用当前材料重新验收')
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
            current, note = coordination.closing(root, profile, task['id'], completed_tasks, close)
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
    result['summary_markdown'] = summary.render({**result, 'knowledge_disposition': (
        summary.disposition(completed) if phase == 'delivery' else None)}, task, profile)
    if platform_state is not None:
        latest = coordination.load(task['id'], root=root)
        observed = ('requirements', 'history_digest', 'design_requirements', 'design_history_digest', 'owners')
        require(all(latest[key] == platform_state[key] for key in observed) and not latest['gaps'],
                'Platform requirements, approvals or progress changed during verification')
    require(digest(issue_history.known(root, task['id'])) == issues_before, 'Known issues changed during verification')
    require(validation.source_digest(root, profile) == before, 'Source changed during verification')
    return result


def contents(materials):
    """The same files by content: saving an identical copy elsewhere or reordering keeps an acceptance."""
    if not (isinstance(materials, list) and all(isinstance(m, dict) for m in materials)):
        return None
    return sorted(str(m.get('sha256')) for m in materials)


def check_observations(root, profile, design, row, execution, run_paths):
    """Source citations alone cannot satisfy a behavioral acceptance claim."""
    from contracts import match_coverage, material
    section = next((s for s in design['sections'] if s['id'] == row['id']), None)
    require(section is not None, 'Unknown acceptance observation')
    requirement = section['data']['verification']
    observations = row.get('observations')
    require(isinstance(observations, list) and bool(observations), 'Acceptance needs actual execution or manual observations')
    cases = set()
    for observation in observations:
        if requirement['method'] == 'automatic':
            obj(observation, {'kind', 'run', 'check', 'cases'})
            require(observation['kind'] == 'execution', 'Automatic acceptance needs original execution, not source links')
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
            match_coverage(requirement['coverage'], profile['checks'][key]['coverage'])
            strings(observation['cases'])
            require(all(result.get('cases', {}).get(c) == 'passed' for c in observation['cases']),
                    'Observed case is missing, failed or skipped')
            cases.update(observation['cases'])
        else:
            obj(observation, {'kind', 'observer', 'at', 'steps', 'result', 'coverage', 'evidence'})
            require(observation['kind'] == 'manual', 'Manual acceptance needs actual observations')
            from contracts import independent
            independent(design, observation['observer'], 'Manual observer')
            material(observation['result'])
            observed_at = datetime.fromisoformat(observation['at'])
            require(observed_at.tzinfo is not None, 'Manual observation needs a timezone')
            from datetime import timezone
            require(observed_at <= datetime.now(timezone.utc), 'Observation cannot be dated in the future')
            strings(observation['steps'], True)
            match_coverage(requirement['coverage'], observation['coverage'])
            require(bool(observation['evidence']), 'Manual observation needs captured evidence')
            for ref in observation['evidence']:
                evidence(root, profile, ref)
    require(set(requirement['cases']) <= cases, 'Acceptance lacks required observed cases')
