"""Version 5 platform coordination. Every network operation is a GitHub GET.

Drafts are values, never publications. Readiness concerns continuation only;
business acceptance and permission to close belong to the delivery verifier.
"""
import json
import re

from common import Invalid, VERSION, digest, obj, require, strings, task_valid, text
import designs
import github_read as github
import handoffs
import knowledge
import validation


def task_source(issue):
    value = handoffs.block(issue.get('body'), 'task')
    obj(value, {'schema_version', 'parent', 'task'})
    require(isinstance(value['task'], dict), 'Expected a structured task object')
    require(value['schema_version'] == 5 and value['task'].get('schema_version') == 5,
            'Expected explicitly adopted task-platform version 5')
    require(value['task'].get('id') == issue['html_url'], 'Task ID must be its canonical issue URL')
    require(value['task'].get('parent') == value['parent'], 'Inner and shared task parent differ')
    if value['parent']:
        github.issue_ref(value['parent'])
        require(value['parent'] != issue['html_url'], 'Task cannot be its own parent')
    prose = re.sub(r'```team-workflow-task\s*\n.*?\n```', '', issue.get('body', ''), count=1, flags=re.S)
    return {**value, 'body_digest': digest(prose.replace('\r\n', '\n').replace('\r', '\n').strip())}


def requirements_signature(source):
    task = source['task']
    global_fields = {key: value for key, value in task.items()
                     if key not in ('acceptance', 'section_ids', 'paths', 'symbols', 'scopes')}
    return {'global': digest({'task': global_fields, 'parent': source['parent'], 'prose': source['body_digest']}),
            'acceptance': {row['id']: digest(row) for row in task['acceptance']}}


def reusable_approval(entry, design_state):
    """Retain sectional consent only when requirement changes are mapped to design nodes."""
    if entry['record']['requirements'] == design_state['requirements']:
        return True
    approval = entry['record']['approval']
    revisions = [item['record'] for item in design_state['rows']['design']
                 if item['record']['design']['revision'] >= approval['design_revision']]
    if not revisions or revisions[0]['design']['revision'] != approval['design_revision']:
        return False
    if revisions[0]['requirements'] != entry['record']['requirements']:
        return False
    for before, after in zip(revisions, revisions[1:]):
        old, new = before.get('requirements_signature'), after.get('requirements_signature')
        if not old or not new or old['global'] != new['global']:
            return False
        changed = {key for key in set(old['acceptance']) | set(new['acceptance'])
                   if old['acceptance'].get(key) != new['acceptance'].get(key)}
        old_hashes, new_hashes = designs.fingerprints(before['design'])['sections'], designs.fingerprints(after['design'])['sections']
        if any(old_hashes.get(key) == new_hashes.get(key) for key in changed):
            return False
    return revisions[-1]['requirements'] == design_state['requirements']


def validate_task_design(task, design):
    """Ensure task acceptance and its selected work match the shared design."""
    require(design.get('schema_version') == 5, 'Current work needs a v5 plan; use adopt for historical plans')
    designs.validate_design(design)
    from contracts_v5 import task_scope
    task_scope(task, design)
    require(task.get('design_id') == design['id'], 'Task references another design')
    identifiers = strings(task.get('section_ids'), True)
    sections = {row['id']: row for row in design['sections']}
    require(set(identifiers) <= sections.keys(), 'Task references missing design sections')
    selected = [key for key in identifiers if sections[key]['type'] == 'task']
    require(bool(selected), 'Task must select at least one design task section')
    declared_paths = [path for key in selected for path in sections[key]['data']['scope']]
    require(all(any(scope == '.' or path == scope or path.startswith(scope.rstrip('/') + '/') for scope in declared_paths)
                for path in task.get('paths', [])), 'Knowledge paths are outside the selected task scope')
    risks = {risk for assessment in designs.task_assessments(design, selected).values() for risk in assessment['risks']}
    require(set(task['risks']) == risks, 'Task risks differ from its selected design assessment')
    accepted = {key for identifier in selected for key in sections[identifier]['data']['acceptance']}
    require({row['id'] for row in task['acceptance']} == accepted,
            'Task acceptance does not cover its selected design tasks')
    for row in task['acceptance']:
        section = sections.get(row['id'], {})
        require(section.get('type') == 'acceptance'
                and row['expectation'].replace('\r\n', '\n').replace('\r', '\n') == section['body'].replace('\r\n', '\n').replace('\r', '\n')
                and set(row['checks']) == set(section['data']['checks']),
                'Task acceptance differs from design section: ' + row['id'])
    return selected


def _history(issue):
    return [{'url': row['html_url'], 'body': row.get('body', ''),
             **{key: row[key] for key in ('created_at', 'updated_at') if row.get(key)},
             **({'author': row['user']['login']} if row.get('user', {}).get('login') else {})}
            for row in issue['comments_data'] if '```team-workflow-' in row.get('body', '')]


def _pointer(entry):
    return {'url': entry['url'], 'digest': entry['digest']} if entry else None


def _hash(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'Expected SHA-256 fingerprint')


def _read(issue):
    """Keep append order and explicit conflicts; timestamps never choose a winner."""
    source = task_source(issue)
    requirements = digest(source)
    rows = {'design': [], 'approval': [], 'handoff': []}
    problems = {name: [] for name in rows}
    seen = []
    historical_issues = []
    for comment in _history(issue):
        present = [name for name in rows if '```team-workflow-' + name in comment['body']]
        for name in present:
            try:
                require(len(present) == 1, 'One platform record is allowed per comment')
                row = handoffs.block(comment['body'], name)
                if name == 'handoff' and row.get('schema_version') in (3, 4):
                    require(row.get('task') == issue['html_url'], 'Historical handoff belongs to another task')
                    require(comment.get('author') == row.get('creator', row.get('owner')), 'Historical handoff author differs')
                    historical_issues += historical_questions(row.get('questions', []), issue['html_url'])
                    continue  # Keep its body in history; it cannot become the current handoff.
                required = {'schema_version', 'kind', 'task', 'requirements', 'history_digest', 'previous'}
                if name == 'design':
                    obj(row, required | {'creator', 'design'}, {'resolution', 'requirements_signature'})
                    require(row['kind'] == 'design-record', 'Expected design-record envelope')
                    designs.validate_design(row['design'])
                    if 'requirements_signature' in row:
                        signature = obj(row['requirements_signature'], {'global', 'acceptance'})
                        _hash(signature['global'])
                        require(isinstance(signature['acceptance'], dict), 'Requirement signature needs acceptance hashes')
                        for value in signature['acceptance'].values():
                            _hash(value)
                        if row.get('requirements') == requirements:
                            require(signature == requirements_signature(source), 'Requirement signature differs from current task')
                    require(row['design']['task_id'] == issue['html_url'], 'Design belongs to another task')
                    require(row['creator'] == row['design']['roles']['design_owner'],
                            'Design must be confirmed by its design owner')
                    author = row['creator']
                elif name == 'approval':
                    obj(row, required | {'approval'}, {'resolution'})
                    require(row['kind'] == 'approval-record' and isinstance(row['approval'], dict),
                            'Expected approval-record envelope')
                    require(row['approval'].get('task_id') == issue['html_url'], 'Approval belongs to another task')
                    author = row['approval'].get('reviewer')
                    text(author)
                else:
                    _validate_handoff(row)
                    author = row['creator']
                require((row['schema_version'] == 5 or (row['schema_version'] == 4 and name in ('design', 'approval')))
                        and row['task'] == issue['html_url'],
                        'Platform record version or task differs')
                _hash(row['requirements'])
                require(row['history_digest'] == digest(seen),
                        'Preceding history changed or concurrent record was appended; reconcile explicitly')
                require(bool(comment.get('author')) and comment['author'] == author,
                        'Record author differs from the actual comment author')
                require(not (comment.get('created_at') and comment.get('updated_at'))
                        or comment['created_at'] == comment['updated_at'],
                        'An edited platform record cannot serve as immutable history; append a reconciliation')
                latest = rows[name][-1] if rows[name] else None
                resolution = row.get('resolution')
                if resolution:
                    obj(resolution, {'history_digest', 'reason'})
                    text(resolution['reason'])
                    require(resolution['history_digest'] == digest(seen) and row['previous'] is None,
                            'Resolution no longer covers the preceding history')
                    problems[name] = []
                else:
                    require(row['previous'] == _pointer(latest), 'Missing or edited predecessor; reconcile explicitly')
                if name == 'design' and latest:
                    old, current = latest['record']['design'], row['design']
                    require(current['id'] == old['id'] and current['revision'] == old['revision'] + 1,
                            'Design revisions must advance by one without changing identity')
                elif name == 'design':
                    require(row['design']['revision'] == 1, 'Design history must begin with revision 1')
                rows[name].append({'url': comment['url'], 'digest': digest(row), 'record': row})
            except (Invalid, ValueError, KeyError, TypeError) as exc:
                problems[name].append('Invalid ' + name + ' ' + comment['url'] + ': ' + str(exc))
        seen.append(comment)
    return {'source': source, 'requirements': requirements, 'rows': rows,
            'gaps': [value for group in problems.values() for value in group],
            'problems': problems, 'historical_issues': historical_issues,
            'history_digest': digest(seen), 'platform_history': seen}


def load(url):
    """Read task, versioned design, explicit approvals and all outstanding progress."""
    issue = github.issue(url)
    state = _read(issue)
    design_state = state
    parent = state['source']['parent']
    if parent and not state['rows']['design']:
        design_state = _read(github.issue(parent))
    entries = design_state['rows']['design']
    latest = entries[-1] if entries else None
    design = latest['record']['design'] if latest else None
    gaps = list(state['gaps'])
    design_gaps = design_state['problems']['design'] + design_state['problems']['approval']
    if design_state is not state:
        gaps += design_gaps
    if latest and latest['record']['requirements'] != design_state['requirements']:
        design_gaps.append('Requirements changed after the current design; append a reviewed revision')
    if design:
        try:
            validate_task_design(state['source']['task'], design)
        except (Invalid, KeyError, TypeError) as exc:
            design_gaps.append(str(exc))
    gaps += design_gaps
    approvals = [item['record']['approval'] for item in design_state['rows']['approval']
                 if reusable_approval(item, design_state)]
    current = state['rows']['handoff'][-1] if state['rows']['handoff'] else None
    progress, pending, progress_gaps = handoffs.pending_progress(issue, current['record'] if current else None)
    gaps += progress_gaps
    if current and current['record']['requirements'] != state['requirements']:
        gaps.append('Requirements changed after this handoff')
    from contracts_v5 import reconcile
    known = {v['id']: v for v in state.get('historical_issues', [])}
    known.update({v['id']: v for v in (design or {}).get('issues', [])})
    for entry in state['rows']['handoff']:
        for item in entry['record']['questions']:
            if item['id'] in known:
                reconcile([known[item['id']]], [item])
            known[item['id']] = item
    for entry in progress.values():
        recorded = entry['record']['questions']
        if entry['record'].get('schema_version') != 5:
            recorded = historical_questions(recorded, url)
        for item in recorded:
            if 'id' in item and item['id'] not in known:
                known[item['id']] = item
    return {'schema_version': 5, 'kind': 'platform-task', 'ok': not gaps, 'issue': url,
            'assurance': 'continuation-only', 'delivery': 'not-evaluated',
            'known_issues': list(known.values()),
            'task': state['source']['task'], 'source': state['source'], 'parent': parent,
            'requirements': state['requirements'], 'history_digest': state['history_digest'],
            'platform_history': state['platform_history'], 'design': design,
            'history': [entry['record']['design'] for entry in entries[:-1]],
            'approvals': approvals, 'roles': dict(design['roles']) if design else {},
            'design_previous': _pointer(latest), 'design_issue': design['task_id'] if design else url,
            'design_requirements': design_state['requirements'],
            'approval_previous': _pointer(design_state['rows']['approval'][-1]) if design_state['rows']['approval'] else None,
            'design_history_digest': design_state['history_digest'],
            'current': current['record'] if current else None, 'previous': _pointer(current),
            'owners': [row['login'] for row in issue.get('assignees', [])],
            'design_gaps': sorted(set(design_gaps)),
            'progress': list(progress.values()), 'pending_progress': pending, 'gaps': sorted(set(gaps))}


def _markdown(name, row, heading):
    return '## ' + heading + '\n\n```team-workflow-' + name + '\n' + json.dumps(row, ensure_ascii=False, indent=2) + '\n```\n'


def _draft_result(name, url, row, gaps=()):
    headings = {'design': '方案记录', 'approval': '方案评审', 'handoff': '工作交接', 'progress': '工作进度'}
    return {'schema_version': 5, 'kind': name + '-draft', 'ok': not gaps,
            'issue': url, 'record': row, 'markdown': _markdown(name, row, headings[name]),
            'history_digest': row.get('history_digest'), 'gaps': list(gaps),
            'assurance': 'continuation-only', 'delivery': 'not-evaluated',
            'publication': 'draft-only; re-read history before an authorized append, then resume'}


def draft_design(url, design, resolution=None):
    designs.validate_design(design)
    state = load(url)
    require(design['task_id'] == url, 'Append the design to its own task issue')
    require(not state['design'] or state['design_issue'] == url,
            'Update the shared design on its own task issue')
    validate_task_design(state['task'], design)
    prior = state['design']
    require(design['revision'] == (prior['revision'] + 1 if prior else 1), 'Design revisions must advance by one')
    require(not prior or prior['id'] == design['id'], 'Cannot change a design identity')
    row = {'schema_version': 5, 'kind': 'design-record', 'task': url,
           'creator': text(design['roles']['design_owner']), 'requirements': state['requirements'],
           'requirements_signature': requirements_signature(state['source']),
           'history_digest': state['history_digest'], 'previous': state['design_previous'], 'design': design}
    if resolution:
        require(resolution.get('history_digest') == state['history_digest'], 'History changed since reconciliation')
        text(resolution.get('reason'))
        row.update(resolution=resolution, previous=None)
    require(not any('Invalid design ' in gap for gap in state['gaps']) or resolution,
            'Read all design branches and provide an explicit resolution')
    return _draft_result('design', url, row)


def draft_approval(url, value):
    obj(value, {'reviewer', 'confirmation'}, {'decision', 'section_ids', 'code_digest', 'run_refs', 'mode', 'deletion_ids', 'resolution'})
    state = load(url)
    require(state['design'] is not None, 'Missing versioned design; append it before review')
    require(state['design_issue'] == url, 'Review the shared design on its own task issue')
    resolution = value.get('resolution')
    if resolution:
        obj(resolution, {'history_digest', 'reason'})
        require(resolution['history_digest'] == state['history_digest'], 'History changed since reconciliation')
        text(resolution['reason'])
    gaps = [gap for gap in state['design_gaps'] if not (resolution and gap.startswith('Invalid approval '))]
    require(not gaps, '; '.join(gaps))
    kwargs = {key: item for key, item in value.items() if key != 'resolution'}
    approval = designs.approval_draft(state['design'], history=state['history'], **kwargs)
    row = {'schema_version': 5, 'kind': 'approval-record', 'task': url,
           'requirements': state['requirements'], 'history_digest': state['history_digest'],
           'previous': state['approval_previous'], 'approval': approval}
    if resolution:
        row.update(resolution=resolution, previous=None)
    return _draft_result('approval', url, row)


def _validate_handoff(row):
    obj(row, {'schema_version', 'kind', 'task', 'requirements', 'history_digest', 'previous',
              'handoff_kind', 'creator', 'owner', 'roles', 'design', 'approved_sections',
              'source_digest', 'versions', 'done', 'verified', 'remaining', 'questions', 'next',
              'references', 'participants', 'contracts', 'dependencies', 'joint_owner',
              'included_progress', 'workflow_version'}, {'resolution'})
    require(row['schema_version'] == 5 and row['kind'] == 'handoff', 'Expected version 5 handoff')
    require(row['handoff_kind'] in ('design', 'implementation'), 'Unknown handoff kind')
    github.issue_ref(row['task'])
    for name in ('creator', 'owner', 'next', 'workflow_version'):
        text(row[name])
    obj(row['roles'], {'design_owner', 'implementation_owner', 'acceptance_owner'})
    for value in row['roles'].values():
        text(value)
    role = 'design_owner' if row['handoff_kind'] == 'design' else 'implementation_owner'
    require(row['creator'] == row['roles'][role], 'Handoff creator must confirm their declared role')
    require(row['owner'] in row['roles'].values(), 'Handoff receiver needs a declared responsibility')
    obj(row['design'], {'id', 'revision'})
    text(row['design']['id'])
    require(type(row['design']['revision']) is int and row['design']['revision'] > 0, 'Invalid design revision')
    require(isinstance(row['approved_sections'], dict), 'Approved sections must be a fingerprint map')
    for key, hashes in row['approved_sections'].items():
        text(key)
        obj(hashes, {'own', 'effective'})
        for value in hashes.values():
            _hash(value)
    _hash(row['source_digest'])
    for name in ('done', 'remaining', 'references'):
        strings(row[name])
    from contracts_v5 import issues
    issues(row['questions'])
    require(isinstance(row['verified'], list), 'Verified results must be artifact references')
    for ref in row['verified']:
        obj(ref, {'path', 'sha256'}, {'repository'})
        text(ref['path']); _hash(ref['sha256'])
    require(isinstance(row['versions'], list) and bool(row['versions']), 'Source versions are required')
    seen = set()
    for version in row['versions']:
        obj(version, {'repository', 'commit', 'content'})
        github.repository(version['repository'])
        require(version['repository'] not in seen, 'Duplicate repository version')
        seen.add(version['repository'])
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(version['commit'])), 'Expected full commit ID')
        _hash(version['content'])
    for name in ('participants', 'contracts', 'dependencies', 'included_progress'):
        require(isinstance(row[name], list), name + ' must be a list')
    for item in row['participants']:
        obj(item, {'issue', 'repository', 'owner', 'role'})
        github.issue_ref(item['issue'])
        github.repository(item['repository'])
        text(item['owner'])
        text(item['role'])
    for item in row['contracts']:
        obj(item, {'document', 'sha256', 'provider', 'consumer', 'confirmation'})
        for name in item:
            text(item[name])
        _hash(item['sha256'])
    for item in row['dependencies']:
        obj(item, {'repository', 'role', 'commit'}, {'issue', 'evidence'})
        github.repository(item['repository'])
        require(item['role'] in ('build', 'modified', 'joint'), 'Unknown dependency responsibility')
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(item['commit'])), 'Expected full dependency commit')
        if item.get('issue'):
            github.issue_ref(item['issue'])
        if item.get('evidence'):
            text(item['evidence'])
    require(isinstance(row['joint_owner'], str), 'Joint owner must be text')
    seen = set()
    for item in row['included_progress']:
        obj(item, {'id', 'digest'})
        text(item['id'])
        _hash(item['digest'])
        require(item['id'] not in seen, 'Duplicate included progress')
        seen.add(item['id'])


def _knowledge(root, task, design, skill):
    sections = {row['id']: row for row in design['sections']}
    paths = set(task.get('paths', []))
    for key in task['section_ids']:
        if sections[key]['type'] == 'task':
            paths.update(sections[key]['data']['scope'])
    return knowledge.brief(root, task, skill, sorted(paths), task.get('symbols', []))


def _approval(root, profile, state, completed_tasks=()):
    require(state['design'] is not None, 'Missing versioned design')
    validate_task_design(state['task'], state['design'])
    return designs.approval_status(state['design'], state['approvals'], history=state['history'],
        changed_paths=validation.changed_paths(root, state['task']),
        code_digest=validation.source_digest(root, profile), section_ids=state['task']['section_ids'], completed_tasks=completed_tasks)


def _shared(root, profile):
    from portable import source_state
    return source_state(root, profile)


def _handoff_gaps(root, profile, state, row, status, documents):
    gaps = []
    if row['requirements'] != state['requirements']:
        gaps.append('Requirements changed after this handoff')
    if row['roles'] != state['roles']:
        gaps.append('Responsibilities changed after this handoff')
    if row['owner'] not in state['owners']:
        gaps.append('Handoff receiver is not assigned to this task')
    required = set(status['required_sections'])
    snapshots = state['history'] + [state['design']]
    revision = row['design']['revision']
    if row['design']['id'] != state['design']['id'] or revision not in {item['revision'] for item in snapshots}:
        gaps.append('Handoff refers to a missing design version')
    else:
        for before, after in zip(snapshots, snapshots[1:]):
            if before['revision'] < revision:
                continue
            change = designs.impact(before, after, [], history=[item for item in snapshots if item['revision'] < after['revision']])
            if required.intersection(change['affected']):
                gaps.append('Relevant design sections changed after this handoff; refresh the affected material')
                break
    approved = {key: {'own': value['own'], 'effective': value['effective']}
                for key, value in status['sections'].items() if value['state'] == 'approved'}
    if any(approved.get(key) != value for key, value in row['approved_sections'].items() if key in required):
        gaps.append('Handoff cites approval fingerprints that are no longer approved')
    if status['review_mode'] != 'combined' and not required <= row['approved_sections'].keys():
        gaps.append('Handoff does not record approval for all selected sections')
    if row['source_digest'] != validation.source_digest(root, profile):
        gaps.append('Source content changed after this handoff')
    current = _shared(root, profile)
    versions = {value['repository']: value for value in row['versions']}
    for repo, version in current['repositories'].items():
        if versions.get(repo) != {'repository': repo, 'commit': version['commit'], 'content': version['content']}:
            gaps.append('Source version missing or different: ' + repo)
        if not version['clean']:
            gaps.append('Unshared working changes: ' + repo)
    if set(versions) != set(current['repositories']):
        gaps.append('Handoff repository set differs from declared source inputs')
    if current['files']:
        gaps.append('External file inputs need a shared repository version for handoff')
    for repo, version in versions.items():
        try:
            github.commit(repo, version['commit'])
        except Invalid as exc:
            gaps.append(str(exc))
    for url in row['references']:
        try:
            github.reachable(url)
        except Invalid as exc:
            gaps.append(str(exc))
    from contracts_v5 import reconcile, unresolved
    try:
        reconcile(state.get('known_issues', []), row['questions'])
        if unresolved(row['questions'], required, 'implementation'):
            gaps.append('Handoff has unresolved implementation issues')
        from delivery import evidence
        checked = set()
        for ref in row['verified']:
            path = evidence(root, profile, ref)
            value = read(path)
            require(value.get('schema_version') == 5 and value.get('kind') in
                    {'execution', 'imported-execution', 'acceptance'},
                    'Handoff needs original execution/acceptance records, not source-file links')
            if 'repository' not in ref:
                checked.update(validation.inspect_record(root, profile, value))
            else:
                from common import external_path, profile_valid
                entry = next(v for v in profile['external_inputs'].values() if v.get('repository') == ref['repository'])
                target = external_path(root, ref['repository'], entry)
                other_profile = profile_valid(read(target / '.team-workflow.json'), target)
                validation.inspect_record(target, other_profile, value)
        if row['handoff_kind'] == 'implementation' and not row['remaining']:
            require(set(task_valid(state['task'], profile, root)) <= checked,
                    'Completed handoff omits required original check results')
    except (Invalid, ValueError, TypeError, KeyError) as exc:
        gaps.append(str(exc))
    if row['handoff_kind'] == 'implementation' and not row['remaining'] and not row['verified']:
        gaps.append('Completed handoff needs original verification records')
    declared = {value['repository']: value.get('role', 'build')
                for value in profile.get('external_inputs', {}).values() if value['kind'] == 'repository'}
    dependencies = {}
    for dependency in row['dependencies']:
        repo = dependency['repository']
        if repo in dependencies:
            gaps.append('Duplicate dependency: ' + repo)
        dependencies[repo] = dependency
        if repo not in declared or dependency['role'] != declared[repo]:
            gaps.append('Dependency responsibility differs from project configuration: ' + repo)
        if dependency['commit'] != versions.get(repo, {}).get('commit'):
            gaps.append('Dependency version differs from source: ' + repo)
        if dependency['role'] != 'build' and not dependency.get('evidence'):
            gaps.append('Modified or joint dependency needs delivery evidence: ' + repo)
        try:
            if dependency.get('issue'):
                require(github.issue_ref(dependency['issue'])[0] == repo, 'Dependency task belongs to another repository')
                github.issue(dependency['issue'])
            if dependency.get('evidence'):
                github.reachable(dependency['evidence'])
        except Invalid as exc:
            gaps.append(str(exc))
    for repo in set(declared) - set(dependencies):
        gaps.append('Declared dependency missing: ' + repo)
    collaborating = {repo for repo, role in declared.items() if role != 'build'}
    if collaborating:
        from portable import repository_id
        collaborating.add(repository_id(root))
    joint = 'cross-service' in state['task']['risks'] or 'joint' in declared.values()
    if joint and not collaborating:
        gaps.append('Joint work must declare its modified or joint repositories')
    participant_repos, participant_owners = set(), set()
    for participant in row['participants']:
        repo = participant['repository']
        if repo in participant_repos:
            gaps.append('Duplicate repository responsibility: ' + repo)
        participant_repos.add(repo)
        participant_owners.add(participant['owner'])
        try:
            require(repo in versions, 'Participant version missing: ' + repo)
            require(github.issue_ref(participant['issue'])[0] == repo, 'Participant task belongs to another repository')
            if participant['issue'] == state['issue']:
                source, owners = state['source'], state['owners']
            else:
                child = github.issue(participant['issue'])
                source = task_source(child)
                owners = [value['login'] for value in child.get('assignees', [])]
            require((source['parent'] or source['task']['id']) == (state['parent'] or state['issue']),
                    'Participant belongs to another parent task')
            require(participant['owner'] in owners, 'Participant owner is not assigned: ' + repo)
        except Invalid as exc:
            gaps.append(str(exc))
    for repo in collaborating - participant_repos:
        gaps.append('Modified or joint repository has no declared responsibility: ' + repo)
    if joint and (not row['joint_owner'] or row['joint_owner'] not in participant_owners or not row['contracts']):
        gaps.append('Joint work needs confirmed contracts and a participant responsible for joint verification')
    current_documents = {value['id']: value for value in documents.get('documents', [])}
    for contract in row['contracts']:
        document = current_documents.get(contract['document'], {})
        if document.get('sha256') != contract['sha256'] or document.get('status') != 'current':
            gaps.append('Contract source missing, changed or not current: ' + contract['document'])
        if contract['provider'] not in versions or contract['consumer'] not in versions:
            gaps.append('Contract provider or consumer has no source version: ' + contract['document'])
        try:
            github.reachable(contract['confirmation'])
        except Invalid as exc:
            gaps.append(str(exc))
    return gaps


def resume(root, profile, url, cs_skill, completed_tasks=()):
    state = load(url)
    task_valid(state['task'], profile, root)
    gaps = list(state['gaps'])
    from validation_session import active
    if active(root):
        gaps.append('Validation is active; keep the shared workspace unchanged')
    status, brief = None, None
    if state['design'] is None:
        gaps.append('Missing versioned design')
    else:
        try:
            status = _approval(root, profile, state, completed_tasks)
            gaps += status['gaps']
            if not status['implementation_ready']:
                gaps.append('Selected task sections are not ready for implementation; resolve approval, decisions or assignment')
            if not status['scope']['complete']:
                gaps.append('Changed source paths cannot all be assigned to declared design task scopes')
            brief = _knowledge(root, state['task'], state['design'], cs_skill)
            documents = knowledge.call(cs_skill, root, ['documents', 'list'])
            if state['current']:
                gaps += _handoff_gaps(root, profile, state, state['current'], status, documents)
        except (Invalid, KeyError, TypeError) as exc:
            gaps.append(str(exc))
    if not state['current']:
        gaps.append('No confirmed handoff; establish current progress before continuing')
    if not state['owners']:
        gaps.append('Task has no assigned owner')
    if state['pending_progress']:
        gaps.append('New progress has not been confirmed in the current handoff')
    fresh = load(url)
    observed = ('requirements', 'history_digest', 'design_history_digest', 'owners')
    if any(fresh[key] != state[key] for key in observed):
        gaps.append('Platform changed while reading; refresh requirements, responsibilities and progress')
    gaps += fresh['gaps']
    gaps = sorted(set(gaps))
    return {**state, 'kind': 'continuation', 'ok': not gaps, 'scope': 'continuation-only',
            'knowledge': brief, 'approval_status': status, 'ready_to_implement': not gaps,
            'closable': False, 'delivery': 'not-evaluated', 'gaps': gaps}


def draft(root, profile, url, progress, cs_skill, kind='implementation', completed_tasks=()):
    state = load(url)
    task_valid(state['task'], profile, root)
    require(kind in ('design', 'implementation'), 'Handoff kind must be design or implementation')
    require(state['design'] is not None, 'Missing versioned design')
    status = _approval(root, profile, state, completed_tasks)
    allowed = {'creator', 'owner', 'done', 'verified', 'remaining', 'questions', 'next',
               'references', 'participants', 'contracts', 'dependencies', 'joint_owner', 'included_progress', 'resolution'}
    obj(progress, {'creator', 'owner', 'next'}, allowed)
    resolution = progress.get('resolution')
    if resolution:
        obj(resolution, {'history_digest', 'reason'})
        require(resolution['history_digest'] == state['history_digest'], 'History changed since reconciliation')
        text(resolution['reason'])
    conflicts = [gap for gap in state['gaps'] if 'Invalid handoff ' in gap]
    require(not conflicts or resolution, '; '.join(conflicts) + '; provide an explicit resolution')
    sources = _shared(root, profile)
    included = {row['id']: row for row in (state['current'] or {}).get('included_progress', [])}
    included.update({row['id']: row for row in progress.get('included_progress', [])})
    dependencies = [{'repository': value['repository'], 'role': value.get('role', 'build'),
                     'commit': sources['repositories'][value['repository']]['commit']}
                    for value in profile.get('external_inputs', {}).values() if value['kind'] == 'repository']
    questions = {v['id']: v for v in state.get('known_issues', [])}
    questions.update({v['id']: v for v in progress.get('questions', [])})
    row = {'schema_version': 5, 'kind': 'handoff', 'task': url, 'handoff_kind': kind,
           'creator': progress['creator'], 'owner': progress['owner'], 'roles': dict(state['roles']),
           'requirements': state['requirements'], 'history_digest': state['history_digest'],
           'previous': None if resolution else state['previous'], 'workflow_version': VERSION,
           'design': {'id': state['design']['id'], 'revision': state['design']['revision']},
           'approved_sections': {key: {'own': value['own'], 'effective': value['effective']}
                                 for key, value in status['sections'].items()
                                 if key in status['required_sections'] and value['state'] == 'approved'},
           'source_digest': validation.source_digest(root, profile),
           'versions': [{'repository': repo, 'commit': value['commit'], 'content': value['content']}
                        for repo, value in sorted(sources['repositories'].items())],
           'done': progress.get('done', []), 'verified': progress.get('verified', []),
           'remaining': progress.get('remaining', []), 'questions': list(questions.values()),
           'next': progress['next'], 'references': progress.get('references', []),
           'participants': progress.get('participants', []), 'contracts': progress.get('contracts', []),
           'dependencies': progress.get('dependencies', dependencies), 'joint_owner': progress.get('joint_owner', ''),
           'included_progress': list(included.values())}
    if resolution:
        row['resolution'] = resolution
    _validate_handoff(row)
    brief = _knowledge(root, state['task'], state['design'], cs_skill)
    documents = knowledge.call(cs_skill, root, ['documents', 'list'])
    gaps = [gap for gap in state['gaps'] if not gap.startswith('Requirements changed after this handoff')
            and not (resolution and gap in conflicts)]
    gaps += status['gaps']
    if not status['implementation_ready']:
        gaps.append('Selected task sections require approval, decisions or assignment before implementation')
    if not status['scope']['complete']:
        gaps.append('Changed source paths cannot all be assigned to declared design task scopes')
    gaps += _handoff_gaps(root, profile, state, row, status, documents)
    available = {item['id']: item for item in state['progress']}
    for identifier, item in included.items():
        if identifier not in available or available[identifier]['digest'] != item['digest']:
            gaps.append('Included progress missing or changed: ' + identifier)
    if set(available) - set(included):
        gaps.append('New progress must be read and explicitly included before handoff')
    result = _draft_result('handoff', url, row, sorted(set(gaps)))
    result.update(knowledge=brief, approval_status=status)
    return result


def progress_draft(root, profile, url, progress, request_id):
    issue = github.issue(url)
    source = task_source(issue)
    task_valid(source['task'], profile, root)
    obj(progress, {'author', 'done', 'verified', 'remaining', 'questions'})
    row = {**progress, 'schema_version': 5, 'kind': 'progress', 'task': url,
           'request_id': request_id, 'requirements': digest(source)}
    handoffs.validate_progress(row)
    records, gaps = handoffs.progress_history(issue)
    if request_id in records:
        require(records[request_id]['digest'] == digest(row), 'Progress request ID already has different content')
    return _draft_result('progress', url, row, gaps)


def historical_questions(values, task_id):
    """Retain unstructured historical questions as unresolved, never as consent."""
    require(isinstance(values, list), 'Historical questions must be a list')
    result = []
    for value in values:
        require(isinstance(value, dict), 'Historical question must be an object')
        summary = text(value.get('question') or value.get('summary'))
        owner = text(value.get('owner') or 'unassigned historical owner')
        result.append({'id': 'legacy-' + digest([task_id, owner, summary])[:16],
            'summary': summary, 'owner': owner, 'affects': [], 'blocks': ['implementation', 'acceptance'],
            'state': 'open', 'resolution': {}})
    return result
