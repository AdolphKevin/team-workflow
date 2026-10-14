"""Business acceptance and final delivery are separate read-only decisions."""
from datetime import datetime

from common import (RECORD_SCHEMA, artifact, artifact_valid, digest, evidence_file, external_path, inside, obj, read,
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
    status = designs.approval_status(design, approvals, history=history,
                                     section_ids=task['section_ids'],
                                     completed_tasks=completed_tasks,
                                     changed_paths=validation.changed_paths(root, task),
                                     code_digest=validation.source_digest(root, profile), run_refs=refs)
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
    return {'schema_version': RECORD_SCHEMA, 'kind': 'review', 'task_id': task['id'],
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


def check_review(root, profile, task, review, selected, design, status, execution, run_paths):
    require(review.get('schema_version') == RECORD_SCHEMA and review.get('kind') == 'review',
            f'Expected a schema {RECORD_SCHEMA} code review; regenerate it with review-template')
    require(review.get('task_digest') == digest(task) and review.get('task_id') == task['id'], 'Review belongs to another task/version')
    require(review.get('source_digest') == validation.source_digest(root, profile), 'Review does not cover current source')
    require(review.get('sections') == selected, 'Review does not cover current approved sections')
    require(review.get('validation_policy') == review_policy(root, profile, task), 'Review must cover current validation policy')
    text(review.get('reviewer'))
    for label in ('standards', 'spec'):
        row = review.get(label)
        passed(row, label)
        require(bool(row.get('evidence')), 'Review needs actual evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
    from contracts import independent
    independent(design, review['reviewer'], 'Reviewer')
    require(review.get('risks') == task['risks'], 'Review must assess the current risks')
    require(review.get('knowledge_conflicts_resolved') is True, 'Knowledge conflicts need review')
    from contracts import reconcile, unresolved, issues
    import issue_history
    issues(review.get('findings', []), [r['id'] for r in design['sections']])
    reconcile(design['issues'], review.get('findings', []))
    reconcile(issue_history.known(root, task['id']), review.get('findings', []))
    require(not unresolved(review['findings'], status['required_sections'], 'acceptance'),
            'Unresolved issue blocks business acceptance')
    assessed = set()
    for row in review.get('acceptance', []):
        passed(row, 'Acceptance')
        require(row['id'] not in assessed and bool(row.get('evidence')), 'Duplicate acceptance or missing evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
        check_observations(root, profile, design, row, execution, run_paths)
        assessed.add(row['id'])
    require(assessed == {r['id'] for r in task['acceptance']}, 'Acceptance coverage mismatch')


def verify(root, profile, task, report, cs_skill=None, phase='delivery', _seen=None, live=None):
    """live: re-run environment identity commands. Only the first acceptance does; later checks of the
    same acceptance (knowledge, delivery) rely on the environment it recorded, so a removed fixture
    no longer invalidates finished evidence. Source, definitions, reviews and platform are always rechecked."""
    import designs
    import coordination
    from common import now
    require(phase in ('acceptance', 'delivery'), 'Unknown verification phase')
    live = phase == 'acceptance' if live is None else live
    tool = tool_gate()
    task_valid(task, profile, root)
    obj(report, {'schema_version', 'task_id', 'design', 'approvals', 'brief', 'runs', 'review'},
        {'knowledge', 'design_history', 'close_authorization', 'dependencies', 'automation'})
    require(report['schema_version'] == RECORD_SCHEMA and report['task_id'] == task['id'],
            f'Expected a schema {RECORD_SCHEMA} delivery report for this task; regenerate it with delivery-template')
    strings(report['runs'])
    strings(report['approvals'])
    import issue_history
    issues_before = digest(issue_history.known(root, task['id']))
    before = validation.source_digest(root, profile)
    platform_state = None
    if task['id'].startswith('https://github.com/'):
        platform_state = coordination.load(task['id'])
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
        proof = verify(root, profile, dep_task, dep_report, cs_skill, 'acceptance', seen, live)
        current_design = read(inside(root, report['design']))
        require(dep_task.get('design_id') == task['design_id'] and proof['sections'][dependency['section']]
                == designs.fingerprints(current_design)['sections'][dependency['section']], 'Dependency uses a different plan section')
        completed_tasks.add(dependency['section'])
        dependency_materials += [artifact(root, dep_task_path), artifact(root, dep_report_path), *proof['materials']]
    design, approvals, status, selected = design_material(root, profile, task, report, completed_tasks)
    if platform_state is not None:
        require(platform_state['design'] == design, 'Local design differs from the shared plan')
        require(all(a in platform_state['approvals'] for a in approvals), 'Approval has not been shared on the task')
    from contracts import unsourced
    missing = unsourced(task, design)
    require(not missing, 'Acceptance scenario needs confirmed business sources: ' + ', '.join(missing))
    require(status.get('local_review_valid') is True, 'Design coverage/history needs review: ' + design_problem(status))
    require(status.get('acceptance_ready') is True, 'Current design/code approval is missing: ' + design_problem(status))
    execution = validation.verify_runs(root, profile, task, report['runs'], live=live)
    initial = read(inside(root, report['brief']))
    require(initial.get('schema_version') == RECORD_SCHEMA and initial.get('kind') == 'knowledge-brief'
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
    check_review(root, profile, task, review, selected, design, status, execution, report['runs'])
    from contracts import automation
    regression = automation(report['automation'], task, review['findings'], profile, execution) if 'automation' in report else 'not-declared'
    materials = [artifact(root, inside(root, report[p])) for p in ('design', 'brief', 'review')]
    materials += [artifact(root, inside(root, p)) for p in report['approvals'] + report['runs'] + report.get('design_history', [])]
    materials += dependency_materials
    result = {'schema_version': RECORD_SCHEMA, 'kind': 'acceptance' if phase == 'acceptance' else 'delivery-verification',
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
        require(bool(report.get('knowledge')), 'Knowledge completion is required after business acceptance')
        completed_path = inside(root, report['knowledge'])
        completed = read(completed_path)
        require(completed.get('schema_version') == RECORD_SCHEMA and completed.get('kind') == 'knowledge-completion',
                f'Expected a schema {RECORD_SCHEMA} knowledge completion')
        require(completed.get('task_id') == task['id'] and completed.get('task_digest') == digest(task), 'Knowledge completion belongs to another task/version')
        for ref in completed.get('files', []):
            artifact_valid(root, ref)
        initial_path = artifact_valid(root, completed['brief'])
        require(initial_path == inside(root, report['brief']), 'Knowledge completion must preserve the initial brief')
        acceptance_path = artifact_valid(root, completed['acceptance'])
        prior_acceptance = read(acceptance_path)
        require(prior_acceptance.get('sections') == selected, 'Business acceptance has stale design sections')
        result['environment'] = prior_acceptance.get('environment', result['environment'])
        for ref in prior_acceptance.get('materials', []):
            artifact_valid(root, ref)
        latest_path = artifact_valid(root, completed['final_brief'])
        fresh = knowledge.finish(root, profile, task, knowledge.skill_path(cs_skill), completed['cs_task_id'],
                                     initial_path, completed['disposition'], completed['reason'], acceptance_path, latest_path)
        for field in ('cs_task_revision', 'query_state', 'files', 'external_refs'):
            require(fresh[field] == completed.get(field), 'Knowledge completion changed: ' + field)
        if platform_state is not None:
            import summary
            close = {'acceptance': artifact(root, acceptance_path), 'knowledge': artifact(root, completed_path),
                     'cs_task_id': completed['cs_task_id'], 'cs_task_revision': completed['cs_task_revision'],
                     'disposition': completed['disposition'],
                     'summary': summary.render({**result, 'delivery_complete': True, 'closable': bool(report.get('close_authorization')),
                                                'close_authorization': report.get('close_authorization', {}),
                                                'knowledge_disposition': summary.disposition(completed)},
                                               task, profile)}
            if report.get('close_authorization'):
                close['close_authorization'] = report['close_authorization']
            current, note = coordination.closing(root, profile, task['id'], knowledge.skill_path(cs_skill),
                                                 completed_tasks, close)
            from contracts import reconcile, unresolved
            reconcile(review['findings'], current.get('questions', []))
            require(not unresolved(current.get('questions', []), status['required_sections'], 'acceptance'),
                    'Handoff still has unresolved issues')
            if note is not None:
                result['close_note'] = {k: note[k] for k in ('record', 'markdown', 'publication')}
        result['materials'].extend([artifact(root, completed_path), artifact(root, acceptance_path)])
        result['delivery_complete'] = True
        from artifacts import directory
        requests = directory(root, task['id']).parent
        result['covered_requests'] = [artifact(root, path) for path in sorted(requests.glob('*/request.json'))
                                      if read(path).get('task_id') == task['id']]
        authorization = report.get('close_authorization')
        if authorization:
            obj(authorization, {'confirmed_by', 'reference'})
            text(authorization['confirmed_by']); text(authorization['reference'])
            result['closable'] = True
            result['close_authorization'] = authorization
    import summary
    result['summary_markdown'] = summary.render({**result, 'knowledge_disposition': (
        summary.disposition(completed) if phase == 'delivery' else None)}, task, profile)
    if platform_state is not None:
        latest = coordination.load(task['id'])
        observed = ('requirements', 'history_digest', 'design_requirements', 'design_history_digest', 'owners')
        require(all(latest[key] == platform_state[key] for key in observed) and not latest['gaps'],
                'Platform requirements, approvals or progress changed during verification')
    require(digest(issue_history.known(root, task['id'])) == issues_before, 'Known issues changed during verification')
    require(validation.source_digest(root, profile) == before, 'Source changed during verification')
    return result


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
