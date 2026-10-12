"""Version 4 business acceptance and final delivery are separate read-only decisions."""
from datetime import datetime

from common import (artifact, artifact_valid, digest, external_path, inside, obj, read,
                    require, sha, strings, task_valid, text)
import knowledge
import validation


def evidence(root, profile, item):
    if 'repository' not in item:
        return artifact_valid(root, item)
    obj(item, {'repository', 'path', 'sha256'})
    entries = [v for v in profile.get('external_inputs', {}).values() if v.get('repository') == item['repository']]
    require(len(entries) == 1, 'Evidence repository is not a declared input')
    target = external_path(root, item['repository'], entries[0])
    path = inside(target, item['path'])
    require(path.is_file() and sha(path) == item['sha256'], 'External evidence changed')
    return path


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


def review_template(root, profile, task, report):
    _, _, _, selected = design_material(root, profile, task, report)
    pending = {'status': 'pending', 'summary': '', 'evidence': []}
    return {'schema_version': 4, 'kind': 'review', 'task_id': task['id'],
            'task_digest': digest(task), 'source_digest': validation.source_digest(root, profile),
            'validation_policy': review_policy(root, profile, task),
            'sections': selected, 'reviewer': '', 'standards': dict(pending), 'spec': dict(pending),
            'risks': task['risks'], 'knowledge_conflicts_resolved': False,
            'acceptance': [{'id': a['id'], **pending} for a in task['acceptance']], 'findings': []}


def review_policy(root, profile, task):
    required = task_valid(task, profile, root)
    return {'checks': {key: digest(profile['checks'][key]) for key in required},
            'risk_checks': {risk: sorted(profile['risk_checks'][risk]) for risk in sorted(task['risks'])}}


def check_review(root, profile, task, review, selected):
    require(review.get('schema_version') == 4 and review.get('kind') == 'review', 'Expected v4 code review')
    require(review.get('task_digest') == digest(task) and review.get('task_id') == task['id'], 'Review belongs to another task/version')
    require(review.get('source_digest') == validation.source_digest(root, profile), 'Review does not cover current source')
    require(review.get('sections') == selected, 'Review does not cover current approved sections')
    require(review.get('validation_policy') == review_policy(root, profile, task), 'Review must cover current validation policy')
    text(review.get('reviewer'))
    from verification import passed
    for label in ('standards', 'spec'):
        row = review.get(label)
        passed(row, label)
        require(bool(row.get('evidence')), 'Review needs actual evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
    require(review.get('risks') == task['risks'], 'Review must assess the current risks')
    require(review.get('knowledge_conflicts_resolved') is True, 'Knowledge conflicts need review')
    require(isinstance(review.get('findings'), list), 'Review needs findings')
    for row in review['findings']:
        obj(row, {'blocking', 'resolved', 'summary'})
        require(type(row['blocking']) is bool and type(row['resolved']) is bool, 'Finding states must be boolean')
        require(not row['blocking'] or row['resolved'], 'Unresolved blocking finding')
        text(row['summary'])
    assessed = set()
    for row in review.get('acceptance', []):
        passed(row, 'Acceptance')
        require(row['id'] not in assessed and bool(row.get('evidence')), 'Duplicate acceptance or missing evidence')
        for ref in row['evidence']:
            evidence(root, profile, ref)
        assessed.add(row['id'])
    require(assessed == {r['id'] for r in task['acceptance']}, 'Acceptance coverage mismatch')


def verify(root, profile, task, report, cs_skill=None, phase='delivery', _seen=None):
    import designs
    import coordination
    from common import now
    require(phase in ('acceptance', 'delivery'), 'Unknown verification phase')
    task_valid(task, profile, root)
    obj(report, {'schema_version', 'task_id', 'design', 'approvals', 'brief', 'runs', 'review'},
        {'knowledge', 'design_history', 'close_authorization', 'dependencies'})
    require(report['schema_version'] == 4 and report['task_id'] == task['id'], 'Expected v4 delivery for this task')
    strings(report['runs'])
    strings(report['approvals'])
    before = validation.source_digest(root, profile)
    platform_state = None
    if task['id'].startswith('https://github.com/'):
        platform_state = coordination.load(task['id'])
        require(not platform_state['gaps'], 'Platform records are incomplete: ' + '; '.join(platform_state['gaps']))
        require(platform_state['task'] == task, 'Platform task changed; read current requirements')
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
        proof = verify(root, profile, dep_task, dep_report, cs_skill, 'acceptance', seen)
        current_design = read(inside(root, report['design']))
        require(dep_task.get('design_id') == task['design_id'] and proof['sections'][dependency['section']]
                == designs.fingerprints(current_design)['sections'][dependency['section']], 'Dependency uses a different plan section')
        completed_tasks.add(dependency['section'])
        dependency_materials += [artifact(root, dep_task_path), artifact(root, dep_report_path), *proof['materials']]
    design, approvals, status, selected = design_material(root, profile, task, report, completed_tasks)
    if platform_state is not None:
        require(platform_state['design'] == design, 'Local design differs from the shared plan')
        require(all(a in platform_state['approvals'] for a in approvals), 'Approval has not been shared on the task')
    require(status.get('local_review_valid') is True, 'Design coverage/history needs review: ' + str(status))
    require(status.get('acceptance_ready') is True, 'Current design/code approval is missing: ' + str(status))
    execution = validation.verify_runs(root, profile, task, report['runs'])
    initial = read(inside(root, report['brief']))
    require(initial.get('schema_version') == 4 and initial.get('kind') == 'knowledge-brief'
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
    check_review(root, profile, task, review, selected)
    materials = [artifact(root, inside(root, report[p])) for p in ('design', 'brief', 'review')]
    materials += [artifact(root, inside(root, p)) for p in report['approvals'] + report['runs'] + report.get('design_history', [])]
    materials += dependency_materials
    result = {'schema_version': 4, 'kind': 'acceptance' if phase == 'acceptance' else 'delivery-verification',
              'ok': True, 'at': now(), 'phase': phase, 'task_id': task['id'], 'task_digest': digest(task),
              'source_digest': before, 'sections': selected, 'checks': execution['checks'], 'materials': materials,
              'scope': 'business-acceptance' if phase == 'acceptance' else 'team-delivery',
              'business_accepted': True, 'delivery_complete': False, 'closable': False,
              'reused_execution': reused,
              'assurance': 'content-bound records and explicit reviews; not signed or exhaustive business proof'}
    if phase == 'delivery':
        require(bool(report.get('knowledge')), 'Knowledge completion is required after business acceptance')
        completed_path = inside(root, report['knowledge'])
        completed = read(completed_path)
        require(completed.get('schema_version') == 4 and completed.get('kind') == 'knowledge-completion', 'Expected v4 knowledge completion')
        require(completed.get('task_id') == task['id'] and completed.get('task_digest') == digest(task), 'Knowledge completion belongs to another task/version')
        for ref in completed.get('files', []):
            artifact_valid(root, ref)
        initial_path = artifact_valid(root, completed['brief'])
        require(initial_path == inside(root, report['brief']), 'Knowledge completion must preserve the initial brief')
        acceptance_path = artifact_valid(root, completed['acceptance'])
        prior_acceptance = read(acceptance_path)
        require(prior_acceptance.get('sections') == selected, 'Business acceptance has stale design sections')
        for ref in prior_acceptance.get('materials', []):
            artifact_valid(root, ref)
        latest_path = artifact_valid(root, completed['final_brief'])
        fresh = knowledge.finish_v4(root, profile, task, knowledge.skill_path(cs_skill), completed['cs_task_id'],
                                     initial_path, completed['disposition'], completed['reason'], acceptance_path, latest_path)
        for field in ('cs_task_revision', 'query_state', 'files', 'external_refs'):
            require(fresh[field] == completed.get(field), 'Knowledge completion changed: ' + field)
        if platform_state is not None:
            continuation = coordination.resume(root, profile, task['id'], knowledge.skill_path(cs_skill), completed_tasks=completed_tasks)
            require(continuation.get('ok') is True, 'Delivery handoff incomplete: ' + str(continuation.get('gaps')))
            current = continuation.get('current')
            require(current and not current.get('remaining') and not current.get('questions')
                    and not continuation.get('pending_progress'), 'Handoff still has unfinished work or unconfirmed progress')
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
    if platform_state is not None:
        latest = coordination.load(task['id'])
        observed = ('requirements', 'history_digest', 'design_requirements', 'design_history_digest', 'owners')
        require(all(latest[key] == platform_state[key] for key in observed) and not latest['gaps'],
                'Platform requirements, approvals or progress changed during verification')
    require(validation.source_digest(root, profile) == before, 'Source changed during verification')
    return result
