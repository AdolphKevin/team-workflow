"""Task-platform records and read-only continuation checks; no issue writes."""
import json
import re

from common import Invalid, digest, git, obj, require, strings, task_valid, text
import github_read as github
import knowledge


def block(body, name, required=True):
    matches = re.findall(r'^```team-workflow-' + name + r'\s*\n(.*?)^```\s*$', body or '', re.M | re.S)
    require(len(matches) <= 1, 'Multiple structured ' + name + ' records')
    if not matches and not required:
        return None
    require(bool(matches), 'Missing team-workflow-' + name + ' block; keep the MATT spec and add its structured record')
    try:
        value = json.loads(matches[0])
    except ValueError as exc:
        raise Invalid('Invalid ' + name + ' JSON') from exc
    require(isinstance(value, dict), 'Expected a ' + name + ' object')
    return value


def task_source(issue):
    value = block(issue.get('body'), 'task')
    obj(value, {'schema_version', 'task', 'parent'})
    require(value['schema_version'] == 3, 'Expected task-platform record version 3')
    require(value['task'].get('id') == issue['html_url'], 'Task ID must be the canonical issue URL')
    if value['parent']:
        github.issue_ref(value['parent'])
    # Prose is part of the platform specification too. Editing it must not
    # leave a handoff looking current merely because its JSON stayed unchanged.
    return {**value, 'body_digest': digest(issue.get('body', ''))}


def history(issue):
    return [{'url': c['html_url'], 'body': c.get('body', ''), **({'author': c['user']['login']} if c.get('user', {}).get('login') else {})} for c in issue['comments_data']
            if '```team-workflow-handoff' in c.get('body', '')]


def progress_history(issue):
    records, gaps = {}, []
    for comment in issue['comments_data']:
        try:
            row = block(comment.get('body'), 'progress', required=False)
            if row is None:
                continue
            validate_progress(row)
            require(row['task'] == issue['html_url'], 'Progress belongs to another task')
            author = comment.get('user', {}).get('login')
            require(not author or author == row['author'], 'Progress author differs from comment author')
            identifier = row['request_id']
            fingerprint = digest(row)
            require(identifier not in records or records[identifier]['digest'] == fingerprint,
                    'Progress request ID reused with different content')
            records.setdefault(identifier, {'id': identifier, 'digest': fingerprint,
                                            'url': comment['html_url'], 'record': row})
        except (Invalid, ValueError, KeyError, TypeError) as exc:
            gaps.append('Invalid progress ' + comment['html_url'] + ': ' + str(exc))
    return records, gaps


def validate_progress(row):
    obj(row, {'schema_version', 'kind', 'task', 'request_id', 'requirements', 'author',
              'done', 'verified', 'remaining', 'questions'})
    require(row['schema_version'] == 1 and row['kind'] == 'progress', 'Expected progress record version 1')
    github.issue_ref(row['task'])
    for name in ('request_id', 'requirements', 'author'):
        text(row[name])
    for name in ('done', 'verified', 'remaining'):
        strings(row[name])
    require(isinstance(row['questions'], list), 'Questions must be a list')
    for item in row['questions']:
        obj(item, {'question', 'owner'})
        text(item['question'])
        text(item['owner'])


def progress_draft(root, profile, url, progress, request_id):
    issue = github.issue(url)
    source = task_source(issue)
    task_valid(source['task'], profile, root)
    row = {**progress, 'schema_version': 1, 'kind': 'progress', 'task': url,
           'request_id': request_id, 'requirements': digest(source)}
    validate_progress(row)
    records, gaps = progress_history(issue)
    if request_id in records:
        require(records[request_id]['digest'] == digest(row), 'Progress request ID already has different content')
    body = '## 工作进度\n\n```team-workflow-progress\n' + json.dumps(row, ensure_ascii=False, indent=2) + '\n```\n'
    return {'ok': not gaps, 'kind': 'progress-draft', 'record': row, 'markdown': body,
            'gaps': gaps, 'publication': 'draft-only; append using existing authorization; identical request IDs are counted once'}


def chain(issue):
    records, gaps = {}, []
    seen = []
    for comment in history(issue):
        try:
            row = block(comment.get('body'), 'handoff', required=False)
            if row is None:
                continue
            validate(row)
            require(row['task'] == issue['html_url'], 'Handoff belongs to another task')
            require(not comment.get('author') or comment['author'] == row['owner'], 'Handoff must be confirmed by its owner')
            if row.get('resolution'):
                require(row['resolution']['history_digest'] == digest(seen), 'Resolution no longer covers the preceding history')
                # An explicit, reviewed checkpoint retains all earlier comments on the platform.
                records, gaps = {}, []
            records[comment['url']] = {'record': row, 'digest': digest(row)}
        except (Invalid, ValueError, KeyError, TypeError) as exc:
            gaps.append('Invalid handoff ' + comment['url'] + ': ' + str(exc))
        seen.append(comment)
    referenced = set()
    for url, item in records.items():
        previous = item['record']['previous']
        if previous:
            parent = records.get(previous['url'])
            if parent is None or parent['digest'] != previous['digest'] or previous['url'] == url:
                gaps.append('Missing or edited predecessor: ' + url)
            else:
                referenced.add(previous['url'])
    tips = sorted(set(records) - referenced)
    if records and len(tips) != 1:
        gaps.append('Concurrent or cyclic handoffs; reconcile explicitly: ' + ', '.join(tips))
    # A single tip does not prove an unrelated closed cycle is connected to it.
    visited = set()
    cursor = tips[0] if len(tips) == 1 else None
    while cursor and cursor in records and cursor not in visited:
        visited.add(cursor)
        previous = records[cursor]['record']['previous']
        cursor = previous['url'] if previous else None
    if set(records) != visited:
        gaps.append('Handoff history is disconnected or cyclic')
    tip = tips[0] if len(tips) == 1 and not gaps else None
    return records.get(tip), tip, gaps


def validate(row):
    obj(row, {'schema_version', 'kind', 'task', 'requirements', 'previous', 'owner', 'done', 'verified',
              'remaining', 'questions', 'next', 'versions', 'references', 'participants', 'contracts',
              'dependencies', 'joint_owner', 'workflow_version'}, {'resolution', 'included_progress'})
    require(row['schema_version'] == 3 and row['kind'] == 'handoff', 'Expected v3 handoff')
    github.issue_ref(row['task'])
    for name in ('requirements', 'owner', 'next', 'workflow_version'):
        text(row[name])
    for name in ('done', 'verified', 'remaining', 'references'):
        strings(row[name])
    if row['previous'] is not None:
        obj(row['previous'], {'url', 'digest'})
        text(row['previous']['url'])
        text(row['previous']['digest'])
    if 'resolution' in row:
        obj(row['resolution'], {'history_digest', 'reason'})
        text(row['resolution']['reason'])
        require(bool(re.fullmatch(r'[a-f0-9]{64}', text(row['resolution']['history_digest']))), 'Invalid history digest')
        require(row['previous'] is None, 'Resolution must start an explicit history checkpoint')
    for key in ('questions', 'versions', 'participants', 'contracts', 'dependencies'):
        require(isinstance(row[key], list), key + ' must be a list')
    for item in row['questions']:
        obj(item, {'question', 'owner'})
        text(item['question'])
        text(item['owner'])
    repos = set()
    for item in row['versions']:
        obj(item, {'repository', 'commit'})
        github.repository(item['repository'])
        require(item['repository'] not in repos, 'Duplicate repository version')
        repos.add(item['repository'])
        require(bool(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(item['commit']))), 'Expected full commit ID')
    for item in row['participants']:
        obj(item, {'issue', 'repository', 'owner', 'role'})
        github.issue_ref(item['issue'])
        github.repository(item['repository'])
        text(item['owner'])
        text(item['role'])
    for item in row['contracts']:
        obj(item, {'document', 'sha256', 'provider', 'consumer', 'confirmation'})
        for key in ('document', 'sha256', 'provider', 'consumer'):
            text(item[key])
        require(isinstance(item['confirmation'], str), 'Expected confirmation link or empty text')
    for item in row['dependencies']:
        obj(item, {'issue', 'repository', 'commit', 'evidence'})
        github.issue_ref(item['issue'])
        github.repository(item['repository'])
        text(item['commit'])
        require(isinstance(item['evidence'], str), 'Expected dependency evidence link')
    require(isinstance(row['joint_owner'], str), 'Expected joint owner or empty text')
    require(isinstance(row.get('included_progress', []), list), 'Included progress must be a list')
    seen_progress = set()
    for item in row.get('included_progress', []):
        obj(item, {'id', 'digest'})
        text(item['id'])
        text(item['digest'])
        require(item['id'] not in seen_progress, 'Duplicate included progress')
        seen_progress.add(item['id'])


def pending_progress(issue, row):
    records, gaps = progress_history(issue)
    incorporated = {}
    for item in (row or {}).get('included_progress', []):
        require(item['id'] not in incorporated, 'Duplicate included progress')
        incorporated[item['id']] = item['digest']
        if item['id'] not in records or records[item['id']]['digest'] != item['digest']:
            gaps.append('Included progress missing or changed: ' + item['id'])
    return records, [value for key, value in records.items() if key not in incorporated], gaps


def gaps_for(root, profile, source, row, documents):
    from portable import source_state
    gaps = []
    if documents.get('findings'):
        gaps.append('CS source references need review: ' + json.dumps(documents['findings'], ensure_ascii=False))
    if row['requirements'] != digest(source):
        gaps.append('Requirements changed after this handoff')
    versions = {r['repository']: r['commit'] for r in row['versions']}
    current = source_state(root, profile)
    for repo, state in current['repositories'].items():
        if versions.get(repo) != state['commit']:
            gaps.append('Version missing or different: ' + repo)
        if not state['clean']:
            gaps.append('Unshared working changes: ' + repo)
    if current['files']:
        gaps.append('External file inputs need a shared repository version before cross-machine handoff')
    for repo, revision in versions.items():
        try:
            github.commit(repo, revision)
        except Invalid as exc:
            gaps.append(str(exc))
    for url in row['references'] + row['verified']:
        try:
            github.reachable(url)
        except Invalid as exc:
            gaps.append(str(exc))
    participants = row['participants']
    shared = len(current['repositories']) > 1 or 'cross-service' in source['task']['risks']
    if shared:
        if len(participants) < 2 or not row['joint_owner'] or not row['contracts']:
            gaps.append('Cross-service handoff needs participants, contracts and a joint owner')
        for participant in participants:
            if participant['repository'] not in versions:
                gaps.append('Participant version missing: ' + participant['repository'])
            try:
                child = github.issue(participant['issue'])
                child_source = task_source(child)
                group = source['parent'] or row['task']
                require((child_source['parent'] or child['html_url']) == group, 'Participant belongs to another parent task')
                require(participant['owner'] in [a['login'] for a in child.get('assignees', [])], 'Participant owner is not assigned')
            except Invalid as exc:
                gaps.append(str(exc))
        participant_repos = {p['repository'] for p in participants}
        if not set(current['repositories']) <= participant_repos:
            gaps.append('A participating repository or shared dependency has no declared responsibility')
        if row['joint_owner'] not in {p['owner'] for p in participants}:
            gaps.append('Joint owner is not a participant')
    by_id = {d['id']: d for d in documents.get('documents', [])}
    for contract in row['contracts']:
        doc = by_id.get(contract['document'])
        if not doc or doc.get('sha256') != contract['sha256'] or doc.get('status') != 'current':
            gaps.append('Contract source missing, changed or not current: ' + contract['document'])
        if contract['provider'] not in versions or contract['consumer'] not in versions or not contract['confirmation']:
            gaps.append('Contract needs provider, consumer and confirmation: ' + contract['document'])
        elif contract['confirmation']:
            try:
                github.reachable(contract['confirmation'])
            except Invalid as exc:
                gaps.append(str(exc))
    for dep in row['dependencies']:
        try:
            require(versions.get(dep['repository']) == dep['commit'], 'Dependency version differs from the handoff: ' + dep['repository'])
            require(bool(dep['evidence']), 'Dependency has no delivery evidence: ' + dep['issue'])
            github.issue(dep['issue'])
            github.commit(dep['repository'], dep['commit'])
            github.reachable(dep['evidence'])
        except Invalid as exc:
            gaps.append(str(exc))
    return sorted(set(gaps))


def resume(root, profile, url, cs_skill):
    issue = github.issue(url)
    source = task_source(issue)
    task_valid(source['task'], profile, root)
    brief = knowledge.brief(root, source['task'], cs_skill, [], [])
    documents = knowledge.call(cs_skill, root, ['documents', 'list'])
    latest, tip, gaps = chain(issue)
    owners = [a['login'] for a in issue.get('assignees', [])]
    if not owners:
        gaps.append('Task has no assigned owner')
    if latest:
        gaps += gaps_for(root, profile, source, latest['record'], documents)
        if latest['record']['owner'] not in owners:
            gaps.append('Handoff owner differs from current assignees')
    else:
        gaps.append('No unambiguous handoff; establish current progress before continuing')
    progress, pending, progress_gaps = pending_progress(issue, latest['record'] if latest else None)
    gaps += progress_gaps
    return {'schema_version': 3, 'kind': 'continuation', 'ok': not gaps, 'scope': 'continuation-only',
            'delivery': 'not-evaluated', 'issue': url, 'issue_updated_at': issue['updated_at'],
            'requirements': digest(source), 'source': source, 'owners': owners,
            'history_digest': digest(history(issue)),
            'current': latest['record'] if latest else None, 'previous': {'url': tip, 'digest': latest['digest']} if latest else None,
            'knowledge': brief, 'progress': list(progress.values()), 'pending_progress': pending, 'gaps': sorted(set(gaps))}


def draft(root, profile, url, progress, cs_skill):
    from common import VERSION
    issue = github.issue(url)
    source = task_source(issue)
    task_valid(source['task'], profile, root)
    latest, tip, conflicts = chain(issue)
    resolution = progress.get('resolution')
    require(not conflicts or resolution, '; '.join(conflicts) + '; read all branches and provide an explicit resolution')
    if resolution:
        require(resolution.get('history_digest') == digest(history(issue)), 'History changed since reconciliation; read it again')
    row = {**progress, 'schema_version': 3, 'kind': 'handoff', 'task': url,
           'requirements': digest(source), 'previous': {'url': tip, 'digest': latest['digest']} if latest and not resolution else None,
           'workflow_version': VERSION}
    validate(row)
    if latest and not resolution:
        included = {item['id']: item for item in latest['record'].get('included_progress', [])}
        included.update({item['id']: item for item in row.get('included_progress', [])})
        row['included_progress'] = list(included.values())
    _, _, progress_gaps = pending_progress(issue, row)
    require(not progress_gaps, '; '.join(progress_gaps))
    brief = knowledge.brief(root, source['task'], cs_skill, [], [])
    documents = knowledge.call(cs_skill, root, ['documents', 'list'])
    gaps = gaps_for(root, profile, source, row, documents)
    if row['owner'] not in [a['login'] for a in issue.get('assignees', [])]:
        gaps.append('Handoff owner is not assigned to this issue')
    body = '## 工作交接\n\n' + row['next'] + '\n\n```team-workflow-handoff\n' + json.dumps(row, ensure_ascii=False, indent=2) + '\n```\n'
    return {'schema_version': 3, 'kind': 'handoff-draft', 'ok': not gaps, 'scope': 'continuation-only',
            'delivery': 'not-evaluated', 'issue': url, 'requirements': digest(source), 'previous': row['previous'],
            'record': row, 'markdown': body, 'gaps': gaps, 'knowledge': brief,
            'publication': 'draft-only; re-read the issue before an authorized append, then resume to detect concurrent handoffs'}
