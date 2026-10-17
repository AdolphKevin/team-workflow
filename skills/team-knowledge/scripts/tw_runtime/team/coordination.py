"""Version 5 coordination through the project's read-only platform script.

Drafts are values, never publications. Readiness concerns continuation only;
business acceptance and permission to close belong to the delivery verifier.
"""
from error_codes import Code, gap, gap_fields
import json
import re

from common import Invalid, VERSION, digest, obj, read, require, strings, task_valid, text
import designs
import design_files
import records
from tw_runtime import Invalid as RuntimeInvalid, repo_paths
from tw_runtime.team import platform_script as platform_read
import knowledge
import validation


def platform_issue(url, root=None):
    """Keep the record parser's input view stable, using only normalized contract fields."""
    value = platform_read.task(platform_read.project_root(root), url)
    return {'html_url': value['id'], 'body': value['items'][0]['body'], 'state': value['state'],
            'repository': value['repository'], 'assignees': [{'login': owner} for owner in value['owners']],
            'comments_data': [{'html_url': item['url'], 'body': item['body'],
                               'user': {'login': item['author']}, 'created_at': item['created_at'],
                               'updated_at': item['updated_at'], 'kind': item['kind']} for item in value['items'][1:]]}


class MissingTaskBlock(Invalid):
    """Keep the issue identity when a shared task or its parent lacks structured input."""
    def __init__(self, issue_url):
        self.issue_url = issue_url
        super().__init__(issue_url + ': Missing tw-record task comment；请用 issue-draft 重新生成任务草稿')


class DesignHistoryGap(Invalid):
    """Distinguish a design-history reconciliation from other publication refusals."""
    error_code = Code.PLATFORM_DESIGN


def block(body, name, required=True):
    return records.block(body, name, required)


def validate_progress(row):
    obj(row, {'data_version', 'kind', 'task', 'request_id', 'requirements', 'author',
              'done', 'verified', 'remaining', 'questions'})
    require(row['data_version'] == 1 and row['kind'] == 'progress', 'Expected progress data_version 1')
    platform_read.task_url(row['task'])
    for name in ('request_id', 'requirements', 'author'):
        text(row[name])
    for name in ('done', 'verified', 'remaining'):
        strings(row[name])
    from contracts import issues
    issues(row['questions'])


def progress_history(issue):
    records, gaps = {}, []
    for comment in issue['comments_data']:
        if comment.get('kind') == 'change':
            continue
        try:
            row = block(comment.get('body'), 'progress', required=False)
            if row is None:
                continue
            validate_progress(row)
            require(row['task'] == issue['html_url'], 'Progress belongs to another task')
            identifier = row['request_id']
            fingerprint = digest(row)
            require(identifier not in records or records[identifier]['digest'] == fingerprint,
                    'Progress request ID reused with different content', error_code=Code.REQUEST_CONFLICT)
            records.setdefault(identifier, {'id': identifier, 'digest': fingerprint, 'url': comment['html_url'],
                                            'recorded_by': comment.get('user', {}).get('login'), 'record': row})
        except (Invalid, ValueError, KeyError, TypeError) as exc:
            gaps.append('Invalid progress ' + comment['html_url'] + ': ' + str(exc))
    return records, gaps


def pending_progress(issue, row):
    records, gaps = progress_history(issue)
    incorporated = {}
    for item in (row or {}).get('included_progress', []):
        require(item['id'] not in incorporated, 'Duplicate included progress')
        incorporated[item['id']] = item['digest']
        if item['id'] not in records or records[item['id']]['digest'] != item['digest']:
            gaps.append('Included progress missing or changed: ' + item['id'])
    return records, [value for key, value in records.items() if key not in incorporated], gaps


def task_source(issue):
    value = block(issue.get('body'), 'task', required=False)
    if value is None:
        raise MissingTaskBlock(issue['html_url'])
    obj(value, {'data_version', 'parent', 'task'})
    require(isinstance(value['task'], dict), 'Expected a structured task object')
    require(value['data_version'] == 1 and value['task'].get('data_version') == 1,
            'Expected task-platform data_version 1')
    require(value['task'].get('id') == issue['html_url'], 'Task ID must be its canonical issue URL')
    import task_inputs
    task_inputs.validate_written(value['task'])
    require(value['task'].get('parent') == value['parent'], 'Inner and shared task parent differ')
    if value['parent']:
        platform_read.task_url(value['parent'])
        require(value['parent'] != issue['html_url'], 'Task cannot be its own parent')
    # Visible Markdown is for readers; task requirements come exclusively from tw-record.
    return {**value, 'body_digest': digest('')}


def requirements_signature(source):
    import task_inputs
    task = task_inputs.written(source['task'])
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
    require(design.get('data_version') == 1, 'Current work needs a current-format plan')
    designs.validate_design(design)
    from contracts import task_scope
    task_scope(task, design)
    require(task.get('design_id') == design['id'], 'Task references another design')
    identifiers = strings(task.get('section_ids'), True)
    sections = {row['id']: row for row in design['sections']}
    require(set(identifiers) <= sections.keys(), 'Task references missing design sections')
    selected = [key for key in identifiers if sections[key]['type'] == 'task']
    require(bool(selected), 'Task must select at least one design task section')
    try:
        declared_paths = [repo_paths.normalize(path, scope=True) for key in selected for path in sections[key]['data']['scope']]
        requested_paths = [repo_paths.normalize(path, scope=True) for path in task.get('paths', [])]
    except RuntimeInvalid as exc:
        raise Invalid(str(exc)) from exc
    require(all(any(repo_paths.covers(scope, path) for scope in declared_paths)
                for path in requested_paths), 'Knowledge paths are outside the selected task scope')
    risks = {risk for assessment in designs.task_assessments(design, selected).values() for risk in assessment['risks']}
    require(set(task['risks']) == risks, 'Task risks differ from its selected design assessment')
    accepted = {key for identifier in selected for key in sections[identifier]['data']['acceptance']}
    require({row['id'] for row in task['acceptance']} == accepted,
            'Task acceptance does not cover its selected design tasks')
    for row in task['acceptance']:
        section = sections.get(row['id'], {})
        require(section.get('type') == 'acceptance', 'Missing acceptance section: ' + row['id'])
    return selected


def _history(issue):
    result = []
    for row in issue['comments_data']:
        if row.get('kind') == 'change':
            continue
        body = row.get('body', '')
        if '<!-- tw-record' not in body and not records.LEGACY.search(body):
            continue
        try:
            value = records.read(body, required=False)
            if value is None:
                continue
            if records.kind(value) not in ('design', 'approval', 'handoff', 'progress'):
                continue
            body = records.comment(value)
        except Invalid:
            pass  # Keep malformed/legacy records in the history and report their gap below.
        result.append({'url': row['html_url'], 'body': body,
                       **{key: row[key] for key in ('created_at', 'updated_at') if row.get(key)},
                       **({'author': row['user']['login']} if row.get('user', {}).get('login') else {})})
    return result


def _pointer(entry):
    return {'url': entry['url'], 'digest': entry['digest']} if entry else None


def _hash(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'Expected SHA-256 fingerprint')


def _history_change_reason(seen, comment):
    created = comment.get('created_at')
    changed = [item['url'] for item in seen if created and item.get('updated_at')
               and platform_read.timestamp(item['updated_at']) > platform_read.timestamp(created)]
    cause = '更早的历史在此记录发布后被编辑：' + '、'.join(changed) if changed else '更早的评论可能已被删除或插入'
    return cause + '；请核对历史后重新生成记录并立即发布。'


def _read(issue, root=None):
    """Keep append order and explicit conflicts; timestamps never choose a winner."""
    source = task_source(issue)
    requirements = digest(source)
    rows = {'design': [], 'approval': [], 'handoff': []}
    problems = {name: [] for name in rows}
    repairs = {name: [] for name in rows}
    seen = []
    for comment in _history(issue):
        try:
            value = records.read(comment['body'], required=False)
            present = [name for name in rows if value is not None and records.kind(value) == name]
        except Invalid as exc:
            legacy = re.search(r'```team-workflow-(design|approval|handoff)', comment['body'])
            name = legacy[1] if legacy else 'design'
            problems[name].append(gap('Invalid ' + name + ' ' + comment['url'] + ': ' + str(exc),
                                      record_error_code(name)))
            seen.append(comment)
            continue
        for name in present:
            try:
                require(len(present) == 1, 'One platform record is allowed per comment')
                row = block(comment['body'], name)
                record_digest = digest(row)
                source_reference, source_markdown = None, None
                required = {'data_version', 'kind', 'task', 'requirements', 'history_digest', 'previous'}
                if name == 'design':
                    obj(row, required | {'creator', 'design'}, {'resolution', 'requirements_signature'})
                    require(row['kind'] == 'design-record', 'Expected design-record envelope')
                    source_reference = row['design']
                    design, source_markdown = design_files.source(platform_read.project_root(root), source_reference)
                    row = {**row, 'design': design}
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
                elif name == 'approval':
                    obj(row, required | {'approval'}, {'resolution'})
                    require(row['kind'] == 'approval-record' and isinstance(row['approval'], dict),
                            'Expected approval-record envelope', error_code=Code.APPROVAL_INCOMPLETE)
                    require(row['approval'].get('task_id') == issue['html_url'], 'Approval belongs to another task', error_code=Code.APPROVAL_INCOMPLETE)
                    text(row['approval'].get('reviewer'))
                else:
                    _validate_handoff(row)
                require(row['data_version'] == 1 and row['task'] == issue['html_url'],
                        'Platform record version or task differs')
                _hash(row['requirements'])
                require(row['history_digest'] == digest(seen),
                        'Preceding history changed or concurrent record was appended; reconcile explicitly'
                        + '；' + _history_change_reason(seen, comment))
                require(not (comment.get('created_at') and comment.get('updated_at'))
                        or platform_read.timestamp(comment['created_at']) == platform_read.timestamp(comment['updated_at']),
                        'An edited platform record cannot serve as immutable history; append a reconciliation')
                latest = rows[name][-1] if rows[name] else None
                resolution = row.get('resolution')
                if resolution:
                    obj(resolution, {'history_digest', 'reason'})
                    text(resolution['reason'])
                    require(resolution['history_digest'] == digest(seen) and row['previous'] is None,
                            'Resolution no longer covers the preceding history')
                else:
                    require(row['previous'] == _pointer(latest), 'Missing or edited predecessor; reconcile explicitly')
                if name == 'design' and latest and not resolution:
                    old, current = latest['record']['design'], row['design']
                    require(current['id'] == old['id'] and current['revision'] == old['revision'] + 1,
                            'Design revisions must advance by one without changing identity')
                elif name == 'design':
                    require(row['design']['revision'] == 1, 'Design history must begin with revision 1')
                if resolution:
                    problems[name] = []
                    repairs[name] = []
                    if name == 'design':
                        rows['design'], rows['approval'] = [], []
                        problems['approval'] = []
                        repairs['approval'] = []
                rows[name].append({'url': comment['url'], 'digest': record_digest, 'record': row,
                                   'recorded_by': comment.get('author'),
                                   **({'source': source_reference, 'markdown': source_markdown} if name == 'design' else {})})
            except (Invalid, ValueError, KeyError, TypeError) as exc:
                problems[name].append(gap('Invalid ' + name + ' ' + comment['url'] + ': ' + str(exc),
                                          record_error_code(name)))
                if getattr(exc, 'next_action', None):
                    repairs[name].append(exc.next_action)
        seen.append(comment)
    return {'source': source, 'requirements': requirements, 'rows': rows,
            **gap_fields([value for group in problems.values() for value in group]),
            'problems': problems, 'repairs': repairs,
            'history_digest': digest(seen), 'platform_history': seen}


def record_error_code(name):
    return {'design': Code.PLATFORM_DESIGN, 'approval': Code.PLATFORM_APPROVAL,
            'handoff': Code.PLATFORM_HANDOFF}[name]


def load(url, issue=None, root=None):
    """Read task, versioned design, explicit approvals and all outstanding progress.

    issue: a fetched issue with a drafted body, used to prepare records before the body is posted."""
    issue = issue or platform_issue(url, root)
    state = _read(issue, root)
    design_state, design_issue = state, issue
    parent = state['source']['parent']
    if parent and not state['rows']['design']:
        design_issue = platform_issue(parent, root)
        design_state = _read(design_issue, root)
    entries = design_state['rows']['design']
    latest = entries[-1] if entries else None
    design = latest['record']['design'] if latest else None
    errors = list(state['gap_errors'])
    design_errors = design_state['problems']['design'] + design_state['problems']['approval']
    if design_state is not state:
        errors += design_errors
    if latest and latest['record']['requirements'] != design_state['requirements']:
        design_errors.append(gap('Requirements changed after the current design; append a reviewed revision'))
    task = state['source']['task']
    if design:
        try:
            validate_task_design(task, design)
            import task_inputs
            task = task_inputs.expand(task, design)
        except (Invalid, KeyError, TypeError) as exc:
            design_errors.append(gap(str(exc), exc.error_code if isinstance(exc, Invalid) else Code.INVALID))
    errors += design_errors
    approvals = [item['record']['approval'] for item in design_state['rows']['approval']
                 if reusable_approval(item, design_state)]
    current = state['rows']['handoff'][-1] if state['rows']['handoff'] else None
    progress, pending, progress_gaps = pending_progress(issue, current['record'] if current else None)
    errors += [gap(message) for message in progress_gaps]
    if current and current['record']['requirements'] != state['requirements']:
        errors.append(gap('Requirements changed after this handoff', Code.HANDOFF_REQUIREMENTS))
    from contracts import reconcile
    known = {v['id']: v for v in (design or {}).get('issues', [])}
    for entry in state['rows']['handoff']:
        for item in entry['record']['questions']:
            if item['id'] in known:
                reconcile([known[item['id']]], [item])
            known[item['id']] = item
    for entry in progress.values():
        for item in entry['record']['questions']:
            if item['id'] not in known:
                known[item['id']] = item
    descriptions = [item for item in design_issue['comments_data']
                    if item.get('kind') == 'change']
    warnings = (['变更请求描述与最新发布的方案原文不一致，请更新展示内容。']
                if latest and descriptions and descriptions[-1].get('body', '')
                != design_files.display(latest['markdown'], latest['record']['design'], latest['source'],
                                        root=platform_read.project_root(root)) else [])
    return {'data_version': 1, 'kind': 'platform-task', 'ok': not errors, 'issue': url,
            'task_state': issue.get('state', 'open'),
            'assurance': 'continuation-only', 'delivery': 'not-evaluated',
            'known_issues': list(known.values()), 'warnings': warnings,
            'task': task, 'source': state['source'], 'parent': parent,
            'requirements': state['requirements'], 'history_digest': state['history_digest'],
            'platform_history': state['platform_history'], 'design': design,
            'design_source': latest['source'] if latest else None,
            'history': [entry['record']['design'] for entry in entries[:-1]],
            'approvals': approvals, 'roles': dict(design['roles']) if design else {},
            'approval_records': [{'url': item['url'], 'reviewer': item['record']['approval']['reviewer'],
                                  'recorded_by': item['recorded_by']} for item in design_state['rows']['approval']],
            'design_previous': _pointer(latest), 'design_issue': design['task_id'] if design else url,
            'design_requirements': design_state['requirements'],
            'approval_previous': _pointer(design_state['rows']['approval'][-1]) if design_state['rows']['approval'] else None,
            'design_history_digest': design_state['history_digest'],
            'current': current['record'] if current else None, 'previous': _pointer(current),
            'owners': [row['login'] for row in issue.get('assignees', [])],
            'design_gaps': gap_fields(design_errors)['gaps'], 'design_errors': design_errors,
            'design_repair': next(iter(design_state['repairs']['design']), None),
            'progress': list(progress.values()), 'pending_progress': pending, **gap_fields(errors)}


def approval_sentence(approval, design=None):
    sections = (design or {}).get('sections', [])
    selected = '、'.join(designs.section_label(section) for section in sections
                        if section['id'] in approval['sections']) if design else '、'.join(approval['sections'])
    deleted = ['删除章节 ' + row['id'] for row in approval.get('deletions', [])]
    selected = records.prose('、'.join([selected, *deleted]).strip('、'))
    action = {'approved': '批准', 'changes-requested': '要求修改', 'deferred': '暂缓'}.get(approval.get('decision'), '批准')
    confirmation = approval.get('confirmation', '')
    return (f'{records.prose(approval["reviewer"])} {action}方案第 {approval["design_revision"]} 版：{selected}。'
            + ('依据：' + records.prose(confirmation) if confirmation.strip() else ''))


def _markdown(name, row, heading, design=None):
    if name == 'design':
        ref = row['design']
        prose = f'方案第 {ref["revision"]} 版已发布：{records.prose(ref["path"])}，提交 {ref["commit"][:7]}。'
    elif name == 'approval':
        prose = approval_sentence(row['approval'], design)
    else:
        owner = records.prose(row.get('owner') or row.get('author', ''))
        responsibility = (f'负责人 {owner}；实施 {records.prose(row["creator"])}'
                          if row.get('handoff_kind') == 'close' else f'负责人：{owner}')
        status = '已完成' if not row.get('remaining') else '进行中'
        prose = f'{responsibility}\n\n状态：{status}\n\n剩余事项：\n'
        prose += '\n'.join('- ' + records.prose(item) for item in row.get('remaining', [])) or '- 无'
        if row.get('handoff_kind') == 'close':
            prose += '\n\n' + records.prose(row['close']['summary'])
    return '## ' + heading + '\n\n' + prose + '\n\n' + records.comment(row) + '\n'


def _draft_result(name, url, row, gaps=(), *, design=None):
    headings = {'design': '方案记录', 'approval': '方案评审', 'handoff': '工作交接', 'progress': '工作进度'}
    heading = '收尾说明' if row.get('handoff_kind') == 'close' else headings[name]
    body = _markdown(name, row, heading, design)
    return {'data_version': 1, 'kind': name + '-draft', 'ok': not gaps,
            'issue': url, 'record': row, 'markdown': body,
            'history_digest': row.get('history_digest'), 'gaps': list(gaps),
            'assurance': 'continuation-only', 'delivery': 'not-evaluated',
            'publication': 'draft-only; re-read history before an authorized append, then run tw team start'}


DESIGN_PUBLICATION_STEPS = [
    '先完成任务正文、变更请求描述等其他编辑。',
    '最后生成方案记录，并立即发布到承载方案的变更请求；没有变更请求时发布到任务上。',
    '发布后不要再编辑之前的评论。',
]


def draft_design(url, design, resolution=None, issue=None, *, path=None, root=None):
    designs.validate_design(design)
    reference, markdown = design_files.publication(platform_read.project_root(root), path, design)
    state = load(url, issue, root=root)
    require(design['task_id'] == url, 'Append the design to its own task issue')
    require(not state['design'] or state['design_issue'] == url,
            'Update the shared design on its own task issue')
    validate_task_design(state['task'], design)
    prior = None if resolution else state['design']
    require(design['revision'] == (prior['revision'] + 1 if prior else 1), 'Design revisions must advance by one')
    require(not prior or prior['id'] == design['id'], 'Cannot change a design identity')
    row = {'data_version': 1, 'kind': 'design-record', 'task': url,
           'creator': text(design['roles']['design_owner']), 'requirements': state['requirements'],
           'requirements_signature': requirements_signature(state['source']),
           'history_digest': state['history_digest'], 'previous': state['design_previous'], 'design': reference}
    if resolution:
        require(resolution.get('history_digest') == state['history_digest'], 'History changed since reconciliation')
        text(resolution.get('reason'))
        row.update(resolution=resolution, previous=None)
    if any(row['error_code'] == Code.PLATFORM_DESIGN for row in state['gap_errors']) and not resolution:
        raise DesignHistoryGap('方案历史有缺口；请核对全部方案分支，用 design-draft --reconcile "<原因>" 发布对账记录')
    return {**_draft_result('design', url, row), 'pr_description': markdown,
            'next_steps': list(DESIGN_PUBLICATION_STEPS)}


def draft_approval(url, value, *, root=None):
    obj(value, {'reviewer'}, {'confirmation', 'decision', 'section_ids', 'code_digest', 'run_refs', 'mode', 'deletion_ids', 'resolution', 'revision'})
    root = platform_read.project_root(root)
    state = load(url, root=root)
    require(state['design'] is not None, 'Missing versioned design; append it before review')
    task_sections = state['task']['section_ids']
    if state['design_issue'] != url:
        url = state['design_issue']
        state = load(url, root=root)
    resolution = value.get('resolution')
    if resolution:
        obj(resolution, {'history_digest', 'reason'})
        require(resolution['history_digest'] == state['history_digest'], 'History changed since reconciliation')
        text(resolution['reason'])
    gaps = [row['problem'] for row in state['design_errors']
            if not (resolution and row['error_code'] == Code.PLATFORM_APPROVAL)]
    require(not gaps, '; '.join(gaps))
    kwargs = {key: item for key, item in value.items() if key != 'resolution'}
    if resolution and 'section_ids' not in kwargs:
        status = designs.approval_status(state['design'], state['approvals'], history=state['history'],
                                         section_ids=task_sections, changed_paths=[])
        kwargs['section_ids'] = status['required_sections']
    profile = None
    if root is not None:
        from common import load_profile
        profile = load_profile(root)
    kwargs = designs.approval_selection(state['design'], state['approvals'], task_sections, state['history'], kwargs,
                                       root=root, profile=profile)
    if kwargs is None:
        return {'ok': True, 'summary': '没有需要批准的章节'}
    approval = designs.approval_draft(state['design'], history=state['history'], **kwargs)
    row = {'data_version': 1, 'kind': 'approval-record', 'task': url,
           'requirements': state['requirements'], 'history_digest': state['history_digest'],
           'previous': state['approval_previous'], 'approval': approval}
    if resolution:
        row.update(resolution=resolution, previous=None)
    return _draft_result('approval', url, row, design=state['design'])


HANDOFF_KINDS = ('design', 'implementation', 'close')
NO_HANDOFF = 'No confirmed handoff; establish current progress before continuing'


def closable_alone(state, profile):
    """Why one person cannot close this task with a single note (empty when they can)."""
    reasons = []
    if not state['owners']:
        reasons.append('请先将 Issue 指派给一位负责人')
    elif len(state['owners']) > 1:
        reasons.append('任务有多名负责人，请发布实施交接')
    shared = sorted(v['repository'] for v in profile.get('external_inputs', {}).values()
                    if v.get('kind') == 'repository' and v.get('role', 'build') != 'build')
    if shared:
        reasons.append('modified or joint repositories need their own responsibility: ' + ', '.join(shared))
    if 'cross-service' in state['task']['risks']:
        reasons.append('cross-service work needs a joint verification owner')
    return reasons


def closing(root, profile, url, completed_tasks, close, questions=()):
    """The record that hands over or closes delivered work: a posted handoff, or a drafted close note.

    questions: the review's findings, which the close note must carry with their dispositions."""
    continuation = resume(root, profile, url, completed_tasks)
    current = continuation.get('current')
    if current and current['handoff_kind'] in ('implementation', 'close') and not current['remaining']:
        require(continuation['ok'], 'Delivery handoff incomplete: ' + str(continuation['gaps']))
        require(not continuation.get('pending_progress'), 'Handoff still has unfinished work or unconfirmed progress')
        return current, None
    require(not current or current['handoff_kind'] == 'design',
            'Handoff still has unfinished work or unconfirmed progress')
    reasons = closable_alone(continuation, profile)
    gaps = [row['problem'] for row in continuation['gap_errors']
            if row['error_code'] not in (Code.HANDOFF_MISSING, Code.PROGRESS_UNCONFIRMED)]
    require(not reasons and not gaps, 'Delivery handoff incomplete: ' + '; '.join(gaps + reasons)
            + ('; post an implementation handoff instead of a close note' if reasons else ''))
    implementer = continuation['roles']['implementation_owner']
    note = draft(root, profile, url, {
        'creator': implementer, 'owner': continuation['owners'][0], 'done': ['Business acceptance and knowledge disposition recorded'],
        'verified': [close['acceptance']], 'remaining': [],
        'next': 'Close the issue once the named close authorization is recorded.', 'questions': list(questions),
        'included_progress': [{'id': item['id'], 'digest': item['digest']} for item in continuation['progress']]},
        kind='close', completed_tasks=completed_tasks, close=close)
    require(note['ok'], 'Close note incomplete: ' + '; '.join(note['gaps']))
    return note['record'], note


def _validate_handoff(row):
    obj(row, {'data_version', 'kind', 'task', 'requirements', 'history_digest', 'previous',
              'handoff_kind', 'creator', 'owner', 'roles', 'design', 'approved_sections',
              'source_digest', 'versions', 'done', 'verified', 'remaining', 'questions', 'next',
              'references', 'participants', 'contracts', 'dependencies', 'joint_owner',
              'included_progress'}, {'resolution', 'close'})
    require(row['data_version'] == 1 and row['kind'] == 'handoff', 'Expected data_version 1 handoff')
    require(row['handoff_kind'] in HANDOFF_KINDS, 'Unknown handoff kind')
    platform_read.task_url(row['task'])
    for name in ('creator', 'owner', 'next'):
        text(row[name])
    obj(row['roles'], {'design_owner', 'implementation_owner', 'acceptance_owner'})
    for value in row['roles'].values():
        text(value)
    role = 'design_owner' if row['handoff_kind'] == 'design' else 'implementation_owner'
    require(row['creator'] == row['roles'][role], 'Handoff creator must confirm their declared role')
    if row['handoff_kind'] != 'close':
        require(row['owner'] in row['roles'].values(), 'Handoff receiver needs a declared responsibility')
    require((row['handoff_kind'] == 'close') == ('close' in row), 'Close details belong only to a close note')
    if row['handoff_kind'] == 'close':
        require(row['remaining'] == [], '收尾说明必须没有剩余事项')
        close = obj(row['close'], {'acceptance', 'knowledge', 'summary'}, {'close_authorization'})
        obj(close['acceptance'], {'path', 'sha256'})
        text(close['acceptance']['path']); _hash(close['acceptance']['sha256'])
        knowledge.disposition(close['knowledge'])
        text(close['summary'])
        if 'close_authorization' in close:
            authorization = obj(close['close_authorization'], {'confirmed_by', 'reference'})
            text(authorization['confirmed_by']); text(authorization['reference'])
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
    from contracts import issues
    issues(row['questions'])
    require(isinstance(row['verified'], list), 'Verified results must be artifact references')
    for ref in row['verified']:
        obj(ref, {'path', 'sha256'}, {'repository'})
        text(ref['path']); _hash(ref['sha256'])
    require(isinstance(row['versions'], list) and bool(row['versions']), 'Source versions are required')
    seen = set()
    for version in row['versions']:
        obj(version, {'repository', 'commit', 'content'})
        platform_read.repository(version['repository'])
        require(version['repository'] not in seen, 'Duplicate repository version')
        seen.add(version['repository'])
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(version['commit'])), 'Expected full commit ID')
        _hash(version['content'])
    for name in ('participants', 'contracts', 'dependencies', 'included_progress'):
        require(isinstance(row[name], list), name + ' must be a list')
    for item in row['participants']:
        obj(item, {'issue', 'repository', 'owner', 'role'})
        platform_read.task_url(item['issue'])
        platform_read.repository(item['repository'])
        text(item['owner'])
        text(item['role'])
    for item in row['contracts']:
        obj(item, {'document', 'sha256', 'provider', 'consumer', 'confirmation'})
        for name in item:
            text(item[name])
        _hash(item['sha256'])
    for item in row['dependencies']:
        obj(item, {'repository', 'role', 'commit'}, {'issue', 'evidence'})
        platform_read.repository(item['repository'])
        require(item['role'] in ('build', 'modified', 'joint'), 'Unknown dependency responsibility')
        require(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(item['commit'])), 'Expected full dependency commit')
        if item.get('issue'):
            platform_read.task_url(item['issue'])
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


def _knowledge(root, task, design):
    sections = {row['id']: row for row in design['sections']}
    paths = set(task.get('paths', []))
    for key in task['section_ids']:
        if sections[key]['type'] == 'task':
            paths.update(sections[key]['data']['scope'])
    return knowledge.brief(root, task, knowledge.relative_paths(root, sorted(paths)), task.get('symbols', []))


def _approval(root, profile, state, completed_tasks=()):
    require(state['design'] is not None, 'Missing versioned design')
    validate_task_design(state['task'], state['design'])
    return designs.approval_status(state['design'], state['approvals'], history=state['history'],
        root=root, profile=profile,
        changed_paths=validation.changed_paths(root, state['task'], profile, state['design']),
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
    if row['handoff_kind'] == 'close':
        if state['owners'] != [row['owner']]:
            gaps.append('收尾说明的接收负责人必须是任务唯一的平台负责人')
    elif row['owner'] not in state['owners']:
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
            changes = version.get('changes', [])
            gaps.append('Unshared working changes: ' + repo + (': ' + ', '.join(changes) if changes else '')
                        + ' (commit them, or add local-only files such as .DS_Store to .git/info/exclude)')
    if set(versions) != set(current['repositories']):
        gaps.append('Handoff repository set differs from declared source inputs')
    if current['files']:
        gaps.append('External file inputs need a shared repository version for handoff')
    for repo, version in versions.items():
        try:
            platform_read.commit(root, repo, version['commit'])
        except Invalid as exc:
            gaps.append(str(exc))
    for url in row['references']:
        try:
            platform_read.reference(root, url)
        except Invalid as exc:
            gaps.append(str(exc))
    from contracts import reconcile, unresolved
    try:
        reconcile(state.get('known_issues', []), row['questions'])
        if unresolved(row['questions'], required, 'implementation'):
            gaps.append('Handoff has unresolved implementation issues')
        from delivery import evidence
        checked = set()
        for ref in row['verified']:
            path = evidence(root, profile, ref)
            try:
                value = read(path)
            except Invalid:
                value = {}
            require(isinstance(value, dict) and value.get('data_version') == 1 and value.get('kind') in
                    {'execution', 'imported-execution', 'acceptance'},
                    'Handoff needs original execution/acceptance records, not source-file links')
            if 'repository' not in ref:
                checked.update(validation.inspect_record(root, profile, value))
            else:
                from common import external_path, load_profile
                entry = next(v for v in profile['external_inputs'].values() if v.get('repository') == ref['repository'])
                target = external_path(root, ref['repository'], entry)
                other_profile = load_profile(target)
                validation.inspect_record(target, other_profile, value)
        if row['handoff_kind'] in ('implementation', 'close') and not row['remaining']:
            require(set(task_valid(state['task'], profile, root)) <= checked,
                    'Completed handoff omits required original check results')
        if row['handoff_kind'] == 'close':
            reasons = closable_alone(state, profile)
            require(not reasons, 'A close note cannot stand in for a handoff: ' + '; '.join(reasons))
            from delivery import evidence as material
            material(root, profile, row['close']['acceptance'])
            knowledge.verify(root, row['close']['knowledge'], state['task'].get('base'))
            require(row['close']['acceptance'] in row['verified'], 'Close note must cite its business acceptance')
    except (Invalid, ValueError, TypeError, KeyError) as exc:
        gaps.append(str(exc))
    if row['handoff_kind'] in ('implementation', 'close') and not row['remaining'] and not row['verified']:
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
                require(platform_issue(dependency['issue'], root)['repository'] == repo, 'Dependency task belongs to another repository')
            if dependency.get('evidence'):
                platform_read.reference(root, dependency['evidence'])
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
            require(platform_issue(participant['issue'], root)['repository'] == repo, 'Participant task belongs to another repository')
            if participant['issue'] == state['issue']:
                source, owners = state['source'], state['owners']
            else:
                child = platform_issue(participant['issue'], root)
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
            platform_read.reference(root, contract['confirmation'])
        except Invalid as exc:
            gaps.append(str(exc))
    return gaps


def resume(root, profile, url, completed_tasks=()):
    state = load(url, root=root)
    task_valid(state['task'], profile, root)
    errors = list(state['gap_errors'])
    from validation_session import active
    if active(root):
        errors.append(gap('Validation is active; keep the shared workspace unchanged', Code.VALIDATION_ACTIVE))
    status, brief = None, None
    if state['design'] is None:
        errors.append(gap('Missing versioned design'))
    else:
        try:
            status = _approval(root, profile, state, completed_tasks)
            errors += [gap(message) for message in status['gaps']]
            if not status['implementation_ready']:
                errors.append(gap('Selected task sections are not ready for implementation; resolve approval, decisions or assignment'))
            if not status['scope']['complete']:
                errors.append(gap('Changed source paths cannot all be assigned to declared design task scopes'))
            brief = _knowledge(root, state['task'], state['design'])
            documents = knowledge.documents(root)
            if state['current']:
                errors += [gap(message) for message in _handoff_gaps(root, profile, state, state['current'], status, documents)]
        except (Invalid, KeyError, TypeError) as exc:
            errors.append(gap(str(exc), exc.error_code if isinstance(exc, Invalid) else Code.INVALID))
    if not state['current']:
        errors.append(gap(NO_HANDOFF, Code.HANDOFF_MISSING))
    if not state['owners']:
        errors.append(gap('Task has no assigned owner', Code.OWNER_MISSING))
    if state['pending_progress']:
        errors.append(gap('New progress has not been confirmed in the current handoff', Code.PROGRESS_UNCONFIRMED))
    fresh = load(url, root=root)
    observed = ('requirements', 'history_digest', 'design_history_digest', 'owners')
    if any(fresh[key] != state[key] for key in observed):
        errors.append(gap('Platform changed while reading; refresh requirements, responsibilities and progress'))
    errors += fresh['gap_errors']
    closed = bool(state['current'] and state['current']['handoff_kind'] == 'close')
    return {**state, 'kind': 'continuation', 'ok': not errors, 'scope': 'continuation-only',
            'knowledge': brief, 'approval_status': status, 'ready_to_implement': not errors and not closed,
            'closed': closed, 'closable': False, 'delivery': 'not-evaluated', **gap_fields(errors)}


def draft(root, profile, url, progress, kind='implementation', completed_tasks=(), close=None):
    state = load(url, root=root)
    task_valid(state['task'], profile, root)
    require(kind in HANDOFF_KINDS, 'Handoff kind must be design, implementation or close')
    require((kind == 'close') == (close is not None), 'A close note is drafted by final delivery verification')
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
    conflicts = [row['problem'] for row in state['gap_errors'] if row['error_code'] == Code.PLATFORM_HANDOFF]
    require(not conflicts or resolution, '; '.join(conflicts) + '; provide an explicit resolution')
    sources = _shared(root, profile)
    included = {row['id']: row for row in (state['current'] or {}).get('included_progress', [])}
    included.update({row['id']: row for row in progress.get('included_progress', [])})
    dependencies = [{'repository': value['repository'], 'role': value.get('role', 'build'),
                     'commit': sources['repositories'][value['repository']]['commit']}
                    for value in profile.get('external_inputs', {}).values() if value['kind'] == 'repository']
    questions = {v['id']: v for v in state.get('known_issues', [])}
    questions.update({v['id']: v for v in progress.get('questions', [])})
    row = {'data_version': 1, 'kind': 'handoff', 'task': url, 'handoff_kind': kind,
           'creator': progress['creator'], 'owner': progress['owner'], 'roles': dict(state['roles']),
           'requirements': state['requirements'], 'history_digest': state['history_digest'],
           'previous': None if resolution else state['previous'],
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
    if close is not None:
        row['close'] = close
    _validate_handoff(row)
    brief = _knowledge(root, state['task'], state['design'])
    documents = knowledge.documents(root)
    gaps = [row['problem'] for row in state['gap_errors'] if row['error_code'] != Code.HANDOFF_REQUIREMENTS
            and not (resolution and row['error_code'] == Code.PLATFORM_HANDOFF)]
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
    if kind != 'close':
        from delivery import evidence
        from execution import output_excerpt
        from common import external_path
        excerpts = []
        for ref in row['verified']:
            try:
                value = read(evidence(root, profile, ref))
                evidence_root = root
                if 'repository' in ref:
                    entry = next(item for item in profile['external_inputs'].values()
                                 if item.get('repository') == ref['repository'])
                    evidence_root = external_path(root, ref['repository'], entry)
                rows = value.get('results', []) if value.get('kind') == 'execution' else (
                    [value['result']] if value.get('kind') == 'imported-execution' else [])
                outputs = {item['id']: output_excerpt(evidence_root, item['artifacts']) for item in rows}
                outputs.update(value.get('output_excerpts', {}))
                for key, lines in outputs.items():
                    excerpts += ['- ' + key + ' 原始输出摘录：'] + ['    ' + line for line in lines]
            except (Invalid, OSError, ValueError, TypeError, KeyError, StopIteration):
                continue  # 证据缺口已由交接核对列出。
        if excerpts:
            result['markdown'] = result['markdown'].replace('\n\n<!-- tw-record',
                '\n\n' + records.prose('\n'.join(excerpts)) + '\n\n<!-- tw-record', 1)
    result.update(knowledge=brief, approval_status=status)
    return result


def progress_draft(root, profile, url, progress, request_id):
    issue = platform_issue(url, root)
    source = task_source(issue)
    task_valid(source['task'], profile, root, written=True)
    obj(progress, {'author', 'done', 'verified', 'remaining', 'questions'})
    row = {**progress, 'data_version': 1, 'kind': 'progress', 'task': url,
           'request_id': request_id, 'requirements': digest(source)}
    validate_progress(row)
    records, gaps = progress_history(issue)
    if request_id in records:
        require(records[request_id]['digest'] == digest(row), 'Progress request ID already has different content', error_code=Code.REQUEST_CONFLICT)
    return _draft_result('progress', url, row, gaps)
