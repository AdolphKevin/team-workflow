"""Explicit, non-destructive historical task inspection and adoption drafts."""
import copy

from common import Invalid, artifact, digest, read, require


def source(args, root):
    if args.task:
        from workflow import local
        value = read(local(root, args.task))
        require(isinstance(value, dict), 'Task material must be an object')
        task = copy.deepcopy(value.get('task', value))
        require(isinstance(task, dict), 'Task material must contain a task object')
        if value.get('parent') and 'task' in value:
            task.setdefault('parent', value['parent'])
        return task, {'file': artifact(root, local(root, args.task)), 'material': value}
    if args.issue:
        import github_read
        from handoffs import block
        item = github_read.issue(args.issue)
        value = block(item.get('body'), 'task', required=False)
        task = copy.deepcopy(value.get('task', value)) if value else None
        require(task is None or isinstance(task, dict), 'Issue task must be an object')
        require(task is None or task.get('id') == args.issue, 'Historical task ID differs from its canonical Issue')
        if task is not None and value.get('parent'):
            task.setdefault('parent', value['parent'])
        return task, {'issue': args.issue, 'body_sha256': digest(item.get('body', '')), 'material': value,
                      'history': item.get('comments_data', [])}
    return None, {}


def historical_input(args, root):
    if args.command in ('version', 'schema', 'project', 'upgrade', 'migrate', 'adopt', 'evidence', 'cleanup'):
        return None
    if args.context:
        from workflow import local
        value = read(local(root, args.context))
        require(isinstance(value, dict), 'Context material must be an object')
        if value.get('schema_version') != 5:
            return {'material': 'context', 'schema_version': value.get('schema_version')}
    value, origin = source(args, root)
    if value is not None:
        require(type(value.get('schema_version')) is int and value['schema_version'] <= 5, 'Task uses an unknown/newer format; update the installed tool')
    if value is not None and value.get('schema_version') != 5:
        return {'task': value, 'origin': origin}
    if args.issue and value is None:
        return {'origin': origin, 'problem': 'Issue has no current structured task'}
    return None


def status(value):
    return {'ok': True, 'scope': 'historical-only', 'status': 'needs-adoption',
            'summary': '历史材料已读取；当前任务需补齐第五版条件。', 'historical': value,
            'implementation_ready': False, 'business_accepted': False, 'delivery_complete': False,
            'closable': False, 'next_action': 'Run adopt to retain original materials and prepare missing current inputs.'}


def draft(args, root):
    from artifacts import Request
    from workflow import local
    task, origin = source(args, root)
    require(task is not None, 'adopt needs --task or an Issue with a structured task')
    require(task.get('schema_version') in (2, 3, 4, 5), 'Unsupported historical task format')
    original = copy.deepcopy(task)
    task = copy.deepcopy(task)
    task['schema_version'] = 5
    task.setdefault('design_id', '__REPLACE__')
    task.setdefault('section_ids', ['__REPLACE__'])
    task.setdefault('acceptance_scope', 'task' if task.get('parent') else 'requirement')
    plan = read(local(root, args.design)) if args.design else None
    histories = [read(local(root, p)) for p in args.design_history]
    approvals = [read(local(root, p)) for p in args.approval]
    candidate_history = origin.get('history', [])
    if not plan and (task.get('parent') or '').startswith('https://github.com/'):
        import github_read
        parent = github_read.issue(task['parent'])
        origin['parent'] = {'issue': task['parent'], 'body_sha256': digest(parent.get('body', '')), 'history': parent.get('comments_data', [])}
        from handoffs import block
        if not any(block(c.get('body'), 'design', required=False) for c in candidate_history):
            candidate_history = parent.get('comments_data', [])
    if not plan and candidate_history:
        from handoffs import block
        plans = []
        for comment in candidate_history:
            row = block(comment.get('body'), 'design', required=False)
            if row and row.get('schema_version') in (4, 5):
                require(row.get('creator') == comment.get('user', {}).get('login'), 'Historical design author differs')
                plans.append(row['design'])
            row = block(comment.get('body'), 'approval', required=False)
            if row and row.get('schema_version') in (4, 5):
                require(row['approval'].get('reviewer') == comment.get('user', {}).get('login'), 'Historical approval author differs')
                approvals.append(row['approval'])
        if plans:
            histories += plans[:-1]
            plan = plans[-1]
    request = Request(root, task['id'], {'command': 'adopt', 'origin': origin, 'task': original,
                       'design': plan, 'history': histories, 'approvals': approvals}, args.request_id)
    if request.cached is not None:
        return request.cached
    original_ref = request.publish('original-task.json', original)
    history_refs = [request.publish(f'history-{i}.json', v) for i, v in enumerate(histories)]
    gaps = []
    if plan:
        require(plan.get('schema_version') in (4, 5), 'Only v4/v5 structured plans can retain section approval bindings')
        if plan['schema_version'] == 4:
            import designs
            designs.validate_design(plan)
            history_refs.append(request.publish('original-design.json', plan))
            plan = copy.deepcopy(plan)
            plan['schema_version'] = 5
            plan['revision'] += 1
            plan.setdefault('issues', [])
            for decision in plan.pop('decisions', []):
                plan['issues'].append({'id': decision['id'], 'summary': decision['question'],
                    'owner': '__REPLACE__', 'affects': decision['affects'],
                    'blocks': ['implementation', 'acceptance'], 'state': 'open', 'resolution': {}})
        if origin.get('history'):
            from coordination import historical_questions
            from handoffs import block
            found = {v['id']: v for v in plan.get('issues', [])}
            for comment in origin['history']:
                row = block(comment.get('body'), 'handoff', required=False) or block(comment.get('body'), 'progress', required=False)
                if row and row.get('schema_version') in (1, 3, 4):
                    for question in historical_questions(row.get('questions', []), task['id']):
                        found.setdefault(question['id'], question)
            plan['issues'] = list(found.values())
        task['design_id'] = plan['id']
        task['acceptance_scope'] = 'requirement' if task['id'] == plan['task_id'] else 'task'
        if task['acceptance_scope'] == 'task':
            task['parent'] = plan['task_id']
        try:
            from coordination import validate_task_design
            validate_task_design(task, plan)
        except (Invalid, KeyError, TypeError) as exc:
            gaps.append(str(exc))
    else:
        gaps.append('Read the installed design template and supply the actual plan; no assessment or consent is inferred.')
    result = {'schema_version': 5, 'kind': 'adoption-draft', 'ok': True, 'scope': 'draft-only',
              'origin': origin, 'original': original_ref, 'task': request.publish('task.json', task),
              'design_history': history_refs,
              'approvals': [request.publish(f'original-approval-{i}.json', v) for i, v in enumerate(approvals)],
              'gaps': gaps, 'implementation_ready': False, 'business_accepted': False,
              'delivery_complete': False, 'closable': False,
              'next_action': 'Complete the draft, retain exact applicable approval evidence, then run prepare. Old execution verdicts are not converted.'}
    if plan:
        result['design'] = request.publish('design.json', plan)
    return request.finish(result)
