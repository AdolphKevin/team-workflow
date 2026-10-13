"""Pure versioned design contracts, section fingerprints and review accounting.

Callers own history, artifact reads, code enumeration and platform publication.
This module never reads a file, changes an input, or interprets prose as consent.
"""
import hashlib
import json
import math
from pathlib import PurePosixPath
import re

from common import Invalid, obj, require, strings, text

SCHEMA_VERSION = 5
FINGERPRINT_VERSION = 1
SECTION_TYPES = {'global-scope', 'scope', 'interface', 'data', 'acceptance', 'task'}
DECISIONS = {'approved', 'changes-requested', 'deferred'}
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
SHA256 = re.compile(r'[0-9a-f]{64}')


def _normalized(value):
    if isinstance(value, str):
        return value.replace('\r\n', '\n').replace('\r', '\n')
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict):
        require(all(isinstance(key, str) for key in value), 'JSON keys must be text')
        require(all('\r' not in key for key in value), 'JSON keys cannot contain carriage returns')
        return {key: _normalized(item) for key, item in value.items()}
    require(value is None or isinstance(value, (bool, int, float)), 'Expected a JSON-compatible value')
    require(not isinstance(value, float) or math.isfinite(value), 'JSON numbers must be finite')
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(_normalized(value), sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _identifier(value):
    text(value)
    require(IDENTIFIER.fullmatch(value) is not None, 'Invalid section identifier: ' + value)


def _path(value):
    text(value)
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in value and '\x00' not in value,
            'Expected a repository-relative path: ' + value)
    require(not any(char in value for char in '*?[]'), 'Scope paths are literal paths, not patterns: ' + value)
    return path.as_posix()


def _sections(design):
    return {row['id']: row for row in design['sections']}


def _dependencies(design):
    result = {}
    for row in design['sections']:
        values = set(row['depends_on'])
        if row['id'] != 'scope-global':
            values.add('scope-global')
        if row['type'] == 'task':
            values.update(row['data']['acceptance'])
        result[row['id']] = values
    return result


def _ancestors(graph):
    result, visiting = {}, set()

    def visit(identifier):
        require(identifier not in visiting, 'Dependency cycle at section: ' + identifier)
        if identifier not in result:
            visiting.add(identifier)
            found = set(graph[identifier])
            for dependency in graph[identifier]:
                require(dependency in graph, 'Missing section reference: ' + dependency)
                found.update(visit(dependency))
            visiting.remove(identifier)
            result[identifier] = found
        return result[identifier]

    for identifier in graph:
        visit(identifier)
    return result


def validate_assessment(assessment):
    obj(assessment, {'complexity', 'risks', 'effort', 'drivers', 'uncertainties', 'required_skills'})
    require(assessment['complexity'] in ('simple', 'medium', 'complex'), 'Invalid design complexity')
    text(assessment['effort'])
    for key in ('risks', 'drivers', 'uncertainties', 'required_skills'):
        strings(assessment[key])
    from common import RISKS
    require(set(assessment['risks']) <= RISKS, 'Unknown assessed risk')
    return assessment


def task_assessments(design, section_ids):
    rows = _sections(design)
    return {key: rows[key]['data'].get('assessment', design['assessment']) for key in section_ids
            if key in rows and rows[key]['type'] == 'task'}


def validate_design(design):
    """Validate a plan without mutating it; implementation-blocking questions are shared issues."""
    obj(design, {'schema_version', 'kind', 'id', 'revision', 'task_id', 'assessment', 'roles', 'sections', 'issues'})
    require(type(design['schema_version']) is int and design['schema_version'] == SCHEMA_VERSION
            and design['kind'] == 'design', 'Expected a schema_version 5 design')
    text(design['id'])
    text(design['task_id'])
    require(type(design['revision']) is int and design['revision'] > 0, 'Design revision must be a positive integer')
    validate_assessment(design['assessment'])
    roles = obj(design['roles'], {'design_owner', 'implementation_owner', 'acceptance_owner'})
    for value in roles.values():
        require(isinstance(value, str), 'Role assignments must be text; use empty text for unassigned')
        if value:
            text(value)
    require(isinstance(design['sections'], list) and bool(design['sections']), 'Design needs sections')
    identifiers, globals_ = set(), []
    for row in design['sections']:
        obj(row, {'id', 'type', 'title', 'body', 'data', 'depends_on'})
        _identifier(row['id'])
        require(row['id'] not in identifiers, 'Duplicate section: ' + row['id'])
        identifiers.add(row['id'])
        require(isinstance(row['type'], str) and row['type'] in SECTION_TYPES, 'Unknown section type: ' + str(row['type']))
        text(row['title'])
        text(row['body'])
        require(isinstance(row['data'], dict), 'Section data must be an object')
        strings(row['depends_on'])
        if row['type'] == 'global-scope':
            globals_.append(row['id'])
            require(not row['depends_on'], 'Global scope cannot depend on another section')
        elif row['type'] == 'acceptance':
            require('checks' in row['data'], 'Acceptance section needs checks')
            strings(row['data']['checks'])
        elif row['type'] == 'task':
            if 'assessment' in row['data']:
                validate_assessment(row['data']['assessment'])
            require({'acceptance', 'scope', 'blocked_by'} <= row['data'].keys(),
                    'Task section needs acceptance, scope and blocked_by')
            strings(row['data']['acceptance'], nonempty=True)
            strings(row['data']['scope'])
            strings(row['data']['blocked_by'])
            for path in row['data']['scope']:
                _path(path)
    require(globals_ == ['scope-global'], 'Exactly one global-scope section named scope-global is required')
    rows = _sections(design)
    for row in rows.values():
        if row['type'] != 'task':
            continue
        for identifier in row['data']['acceptance']:
            require(identifier in rows and rows[identifier]['type'] == 'acceptance',
                    'Task acceptance must reference an acceptance section: ' + identifier)
        for identifier in row['data']['blocked_by']:
            require(identifier in rows and rows[identifier]['type'] == 'task',
                    'Execution dependency must reference a task section: ' + identifier)
    _ancestors(_dependencies(design))
    _ancestors({row['id']: set(row['data']['blocked_by']) for row in rows.values() if row['type'] == 'task'})
    from contracts import design as validate_business
    validate_business(design)
    _normalized(design)
    return design


def fingerprints(design):
    """Own hashes cover content; effective hashes also bind all transitive constraints."""
    validate_design(design)
    dependencies = _dependencies(design)
    ancestors = _ancestors(dependencies)
    own = {row['id']: _hash({'fingerprint_version': FINGERPRINT_VERSION,
                            **row, 'depends_on': sorted(dependencies[row['id']])})
           for row in design['sections']}
    # The key stays "decisions" so fingerprints of existing plans keep their values.
    decisions = sorted((v for v in design['issues'] if 'implementation' in v['blocks']), key=lambda row: row['id'])
    return {'fingerprint_version': FINGERPRINT_VERSION,
            'sections': {identifier: {'own': own[identifier],
                                     'effective': _hash({'fingerprint_version': FINGERPRINT_VERSION,
                                                         'own': own[identifier],
                                                         'dependencies': {key: own[key] for key in sorted(ancestors[identifier])},
                                                         'decisions': [{**row, 'affects': sorted(row['affects'])} for row in decisions
                                                                       if not row['affects'] or set(row['affects']) &
                                                                       (ancestors[identifier] | {identifier})]})}
                         for identifier in sorted(own)}}


def scope_coverage(design, changed_paths):
    """Map caller-enumerated changed paths to task scopes; unknown input stays unknown."""
    validate_design(design)
    tasks = {row['id']: row for row in design['sections'] if row['type'] == 'task'}
    missing = sorted(key for key, row in tasks.items() if not row['data']['scope'])
    result = {'checked': changed_paths is not None, 'complete': False,
              'mapped': {}, 'unmapped': [], 'missing_scopes': missing}
    if changed_paths is None:
        return result
    strings(changed_paths)
    for path in sorted({_path(item) for item in changed_paths}):
        matches = sorted(key for key, row in tasks.items() if any(
            scope == '.' or path == scope or path.startswith(scope + '/')
            for scope in (_path(item) for item in row['data']['scope'])))
        result['mapped'][path] = matches
        if not matches:
            result['unmapped'].append(path)
    result['complete'] = bool(tasks) and not missing and not result['unmapped']
    return result


def _closure(graphs, seeds):
    affected = set(seeds)
    reverse = {}
    for graph in graphs:
        for identifier, dependencies in graph.items():
            for dependency in dependencies:
                reverse.setdefault(dependency, set()).add(identifier)
    pending = list(affected)
    while pending:
        for identifier in reverse.get(pending.pop(), ()):
            if identifier not in affected:
                affected.add(identifier)
                pending.append(identifier)
    return affected


def _transition(previous, current, changed_paths=None):
    """Compare revisions using both dependency graphs, including deleted edges."""
    validate_design(previous)
    validate_design(current)
    require(previous['id'] == current['id'] and previous['task_id'] == current['task_id'],
            'Cannot compare different designs or tasks')
    require(previous['revision'] < current['revision'], 'Design revisions must increase')
    from contracts import reconcile
    reconcile(previous['issues'], current['issues'])
    old, new = _sections(previous), _sections(current)
    before, after = fingerprints(previous)['sections'], fingerprints(current)['sections']
    added, removed = set(new) - set(old), set(old) - set(new)
    changed = {key for key in set(old) & set(new) if before[key]['own'] != after[key]['own']}
    assessment_changed = _hash(previous['assessment']) != _hash(current['assessment'])
    seeds = set(old) | set(new) if assessment_changed else added | removed | changed
    old_decisions = {row['id']: row for row in previous['issues'] if 'implementation' in row['blocks']}
    new_decisions = {row['id']: row for row in current['issues'] if 'implementation' in row['blocks']}
    decision_changes = {key for key in old_decisions.keys() | new_decisions.keys()
                        if _decision_hash(old_decisions.get(key)) != _decision_hash(new_decisions.get(key))}
    for key in decision_changes:
        for row in (old_decisions.get(key), new_decisions.get(key)):
            if row is not None:
                seeds.update(row['affects'] or set(old) | set(new))
    affected = _closure([_dependencies(previous), _dependencies(current)], seeds)
    scope = scope_coverage(current, changed_paths)
    return {'schema_version': SCHEMA_VERSION, 'kind': 'design-impact', 'ok': True,
            'fingerprint_version': FINGERPRINT_VERSION, 'design_id': current['id'],
            'previous_revision': previous['revision'], 'revision': current['revision'],
            'assessment_changed': assessment_changed,
            'decision_changes': sorted(decision_changes),
            'added': sorted(added), 'changed': sorted(changed), 'removed': sorted(removed),
            'affected': sorted(affected), 'unaffected': sorted(set(new) - affected),
            'affected_acceptance': sorted(key for key in affected if (new.get(key) or old[key])['type'] == 'acceptance'),
            'affected_tasks': sorted(key for key in affected if (new.get(key) or old[key])['type'] == 'task'),
            'deletions': [{'id': key, **before[key], 'previous_revision': previous['revision'],
                           'removed_in_revision': current['revision']} for key in sorted(removed)],
            'scope': scope, 'full_review_required': not scope['complete']}


def _history(current, previous=None, history=None):
    values = list(history or [])
    if previous is not None:
        values.append(previous)
    values.append(current)
    by_revision = {}
    for value in values:
        validate_design(value)
        require(value['id'] == current['id'] and value['task_id'] == current['task_id'],
                'History belongs to a different design or task')
        require(value['revision'] <= current['revision'], 'History contains a future revision')
        revision = value['revision']
        require(revision not in by_revision or by_revision[revision] == value,
                'Conflicting design snapshots at revision ' + str(revision))
        by_revision[revision] = value
    chain = [by_revision[key] for key in sorted(by_revision)]
    complete = all(row['revision'] == index for index, row in enumerate(chain, start=1))
    transitions = [_transition(left, right, []) for left, right in zip(chain, chain[1:])]
    return chain, transitions, complete


def _decision_hash(row):
    return _hash({**row, 'affects': sorted(row['affects'])} if row else None)


def impact(previous, current, changed_paths=None, *, history=None):
    """Report the immediate change plus retained deletion records from supplied history."""
    result = _transition(previous, current, changed_paths)
    _, transitions, complete = _history(current, previous, history)
    result['deletions'] = [row for change in transitions for row in change['deletions']]
    result['history_complete'] = complete
    result['full_review_required'] = result['full_review_required'] or not complete
    return result


def _run_refs(values):
    require(isinstance(values, list), 'Combined review needs explicit run_refs (empty only when no execution is required)')
    seen = set()
    result = []
    for value in values:
        obj(value, {'path', 'sha256'})
        text(value['path'])
        require(isinstance(value['sha256'], str) and SHA256.fullmatch(value['sha256']) is not None,
                'Run reference needs a lowercase SHA-256 digest')
        require(value['path'] not in seen, 'Duplicate run reference path')
        seen.add(value['path'])
        result.append(dict(value))
    return sorted(result, key=lambda row: (row['path'], row['sha256']))


def approval_draft(design, reviewer, confirmation, decision='approved', section_ids=None,
                   previous=None, code_digest=None, run_refs=None, mode=None, *, history=None, deletion_ids=None):
    """Build a review record after explicit confirmation; this function never publishes."""
    validate_design(design)
    text(reviewer)
    text(confirmation)
    require(isinstance(decision, str) and decision in DECISIONS, 'Invalid approval decision')
    mode = mode or ('combined' if code_digest is not None or run_refs is not None else 'design')
    require(isinstance(mode, str) and mode in {'design', 'combined'}, 'Review mode must be design or combined')
    hashes = fingerprints(design)['sections']
    identifiers = sorted(hashes) if section_ids is None else list(section_ids)
    strings(identifiers)
    require(set(identifiers) <= hashes.keys(), 'Review references an unknown current section')
    _, transitions, _ = _history(design, previous, history)
    deletions = [row for change in transitions for row in change['deletions']]
    if deletion_ids is None:
        if section_ids is not None:
            deletions = []
    else:
        strings(deletion_ids)
        require(set(deletion_ids) <= {row['id'] for row in deletions}, 'Unknown deleted section')
        deletions = [row for row in deletions if row['id'] in deletion_ids]
    require(bool(identifiers) or bool(deletions), 'Review must cover sections or explicit deletions')
    result = {'schema_version': SCHEMA_VERSION, 'kind': 'approval',
              'fingerprint_version': FINGERPRINT_VERSION,
              'design_id': design['id'], 'task_id': design['task_id'], 'design_revision': design['revision'],
              'assessment_hash': _hash(design['assessment']), 'reviewer': reviewer, 'confirmation': confirmation,
              'decision': decision, 'mode': mode,
              'sections': {key: dict(hashes[key]) for key in sorted(identifiers)},
              'deletions': deletions}
    if mode == 'combined':
        require(isinstance(code_digest, str) and SHA256.fullmatch(code_digest) is not None,
                'Combined review needs a lowercase SHA-256 code_digest')
        result.update(code_digest=code_digest, run_refs=_run_refs(run_refs))
    else:
        require(code_digest is None and run_refs is None, 'Code and runs belong to a combined review')
    return result


def _validate_approval(row):
    obj(row, {'schema_version', 'kind', 'fingerprint_version', 'design_id', 'task_id', 'design_revision',
              'assessment_hash', 'reviewer', 'confirmation', 'decision', 'mode', 'sections', 'deletions'},
        {'code_digest', 'run_refs'})
    require(type(row['schema_version']) is int and row['schema_version'] == SCHEMA_VERSION
            and row['kind'] == 'approval', 'Expected a schema_version 5 approval')
    require(type(row['fingerprint_version']) is int and row['fingerprint_version'] == FINGERPRINT_VERSION,
            'Unsupported fingerprint version; review again using the current format')
    for key in ('design_id', 'task_id', 'reviewer', 'confirmation'):
        text(row[key])
    require(type(row['design_revision']) is int and row['design_revision'] > 0, 'Invalid approval design revision')
    require(isinstance(row['decision'], str) and row['decision'] in DECISIONS, 'Invalid approval decision')
    require(isinstance(row['mode'], str) and row['mode'] in {'design', 'combined'}, 'Invalid approval mode')
    require(isinstance(row['sections'], dict) and isinstance(row['deletions'], list),
            'Approval needs explicit section and deletion records')
    require(bool(row['sections']) or bool(row['deletions']), 'Empty approval')
    require(isinstance(row['assessment_hash'], str) and SHA256.fullmatch(row['assessment_hash']) is not None,
            'Invalid assessment fingerprint')
    for key, value in row['sections'].items():
        _identifier(key)
        obj(value, {'own', 'effective'})
        for digest in value.values():
            require(isinstance(digest, str) and SHA256.fullmatch(digest) is not None, 'Invalid section fingerprint')
    seen = set()
    for value in row['deletions']:
        obj(value, {'id', 'own', 'effective', 'previous_revision', 'removed_in_revision'})
        _identifier(value['id'])
        for key in ('own', 'effective'):
            require(isinstance(value[key], str) and SHA256.fullmatch(value[key]) is not None, 'Invalid deletion fingerprint')
        require(type(value['previous_revision']) is int and type(value['removed_in_revision']) is int
                and 0 < value['previous_revision'] < value['removed_in_revision'] <= row['design_revision'],
                'Invalid deletion revisions')
        identity = (value['id'], value['removed_in_revision'])
        require(identity not in seen, 'Duplicate deletion record')
        seen.add(identity)
    if row['mode'] == 'combined':
        require(isinstance(row.get('code_digest'), str) and SHA256.fullmatch(row['code_digest']) is not None,
                'Combined review needs code content fingerprint')
        _run_refs(row.get('run_refs'))
    else:
        require('code_digest' not in row and 'run_refs' not in row, 'Design review cannot contain code evidence')


def _combined_matches(row, code_digest, run_refs):
    return (row is not None and row['decision'] == 'approved' and row['mode'] == 'combined'
            and row['code_digest'] == code_digest and run_refs is not None
            and _run_refs(row['run_refs']) == run_refs)


def approval_status(design, approvals, previous=None, changed_paths=None, code_digest=None,
                    run_refs=None, completed_tasks=(), *, history=None, section_ids=None):
    """Evaluate oldest-to-newest reviews; missing history or mapping never implies success."""
    validate_design(design)
    require(isinstance(approvals, list), 'Approvals must be an oldest-to-newest list')
    chain, transitions, history_complete = _history(design, previous, history)
    snapshots = {value['revision']: value for value in chain}
    current = fingerprints(design)['sections']
    ancestors = _ancestors(_dependencies(design))
    required = set(current)
    if section_ids is not None:
        strings(section_ids, nonempty=True)
        require(set(section_ids) <= current.keys(), 'Selected review references an unknown section')
        required = set(section_ids)
        for identifier in section_ids:
            required.update(ancestors[identifier])
    deleted = [row for change in transitions for row in change['deletions']]
    deletion_by_key = {(row['id'], row['removed_in_revision']): row for row in deleted}
    deletion_impact = {}
    for before, after, change in zip(chain, chain[1:], transitions):
        for row in change['deletions']:
            deletion_impact[(row['id'], row['removed_in_revision'])] = _closure(
                [_dependencies(before), _dependencies(after)], {row['id']})
    scope = scope_coverage(design, changed_paths)
    valid, gaps = [], []
    for index, row in enumerate(approvals):
        try:
            _validate_approval(row)
            require(row['design_id'] == design['id'] and row['task_id'] == design['task_id'],
                    'Approval belongs to another design or task')
            require(row['design_revision'] in snapshots, 'Missing design snapshot for approval revision')
            source = snapshots[row['design_revision']]
            source_hashes = fingerprints(source)['sections']
            require(row['assessment_hash'] == _hash(source['assessment']), 'Approval assessment differs from its revision')
            require(all(key in source_hashes and value == source_hashes[key] for key, value in row['sections'].items()),
                    'Approval fingerprints differ from their design revision')
            require(all(deletion_by_key.get((value['id'], value['removed_in_revision'])) == value
                        for value in row['deletions']), 'Approval deletion differs from design history')
            valid.append(row)
        except (Invalid, TypeError, KeyError) as exc:
            gaps.append(f'Approval {index + 1}: {exc}')
    sections = {}
    combined = []
    current_runs = _run_refs(run_refs) if run_refs is not None else None
    for key, hashes in current.items():
        reviews = [row for row in valid if key in row['sections']]
        row = reviews[-1] if reviews else None
        state = 'unreviewed'
        if row:
            affected_later = any(change['revision'] > row['design_revision'] and key in change['affected']
                                 for change in transitions)
            if row['sections'][key] != hashes or affected_later or row['assessment_hash'] != _hash(design['assessment']):
                state = 'needs-review'
            else:
                state = row['decision']
                if _combined_matches(row, code_digest, current_runs):
                    combined.append(key)
        sections[key] = {'state': state, **hashes}
        if row:
            sections[key].update(reviewer=row['reviewer'], confirmation=row['confirmation'],
                                 reviewed_revision=row['design_revision'])
    deletions = []
    for value in deleted:
        reviews = [row for row in valid if value in row['deletions']]
        latest = reviews[-1] if reviews else None
        affected = deletion_impact[(value['id'], value['removed_in_revision'])]
        deletions.append({**value, 'state': latest['decision'] if latest else 'unreviewed',
                          'combined_current': _combined_matches(latest, code_digest, current_runs),
                          'affected': sorted(affected), 'required': section_ids is None or bool(affected & required)})
    pending = [{**v, 'question': v['summary'], 'status': 'pending'} for v in design['issues']
               if v['state'] == 'open' and 'implementation' in v['blocks']]
    blocked = {}
    for row in pending:
        for key in _closure([_dependencies(design)], row['affects'] or current.keys()):
            blocked.setdefault(key, []).append(row['id'])
    rows = _sections(design)
    task_ids = {key for key, value in rows.items() if value['type'] == 'task'}
    required_tasks = task_ids & required
    completed = set(completed_tasks)
    require(completed <= task_ids, 'Completed task list references an unknown task section')
    tasks = {}
    assessments = task_assessments(design, task_ids)
    simple_tasks = {key for key, value in assessments.items() if value['complexity'] == 'simple'}
    simple = bool(required_tasks) and required_tasks <= simple_tasks
    combined_required = set()
    for key in required_tasks & simple_tasks:
        combined_required.update(ancestors[key] | {key})
    for key in sorted(task_ids):
        task_simple = key in simple_tasks
        waiting = sorted(set(rows[key]['data']['blocked_by']) - completed)
        unreviewed_deletions = sorted(row['id'] for row in deletions
                                      if row['state'] != 'approved' and key in row['affected'])
        if blocked.get(key):
            state = 'pending-decision'
        elif waiting:
            state = 'waiting-for-tasks'
        elif not design['roles']['implementation_owner'].strip():
            state = 'unassigned'
        elif not rows[key]['data']['scope']:
            state = 'scope-unknown'
        elif not task_simple and not history_complete:
            state = 'needs-history'
        elif not task_simple and unreviewed_deletions:
            state = 'needs-review'
        elif not task_simple and any(sections[dependency]['state'] != 'approved'
                                for dependency in ancestors[key] | {key}):
            state = 'needs-review'
        else:
            state = 'ready'
        tasks[key] = {'state': state, 'ready': state == 'ready', 'pending_decisions': sorted(blocked.get(key, [])),
                      'waiting_for_tasks': waiting, 'unreviewed_deletions': unreviewed_deletions}
    approved = sorted(key for key, row in sections.items() if row['state'] == 'approved')
    required_deletions = [row for row in deletions if row['required']]
    required_pending = [row for row in pending if not row['affects'] or
                        _closure([_dependencies(design)], row['affects']) & required]
    scope['missing_scopes'] = sorted(set(scope['missing_scopes']) & required_tasks)
    scope['outside_selection'] = sorted(path for path, targets in scope['mapped'].items()
                                        if targets and not set(targets) & required_tasks)
    scope['complete'] = scope['checked'] and bool(required_tasks) and not scope['missing_scopes'] and not scope['unmapped']
    fully_approved = (required <= set(approved) and all(row['state'] == 'approved' for row in required_deletions)
                      and history_complete and not gaps)
    combined_deletions = []
    for row in required_deletions:
        if section_ids is None:
            old = snapshots[row['previous_revision']]
            old_tasks = [s['id'] for s in old['sections'] if s['type'] == 'task' and s['id'] in row['affected']]
            needed = any(a['complexity'] == 'simple' for a in task_assessments(old, old_tasks).values())
        else:
            needed = bool(set(row['affected']) & combined_required)
        if needed:
            combined_deletions.append(row)
    combined_complete = combined_required <= set(combined) and all(row['combined_current'] for row in combined_deletions)
    from contracts import unresolved
    required_pending += unresolved(design['issues'], required, 'acceptance')
    assigned = all(value.strip() for value in design['roles'].values())
    acceptance_ready = (fully_approved and combined_complete and not required_pending and assigned
                        and scope['complete'] and all(not tasks[key]['waiting_for_tasks'] for key in required_tasks))
    affected = set(transitions[-1]['affected']) & required if transitions else set()
    return {'schema_version': SCHEMA_VERSION, 'kind': 'design-approval-status', 'ok': not gaps,
            'fingerprint_version': FINGERPRINT_VERSION, 'design_id': design['id'], 'revision': design['revision'],
            'history_complete': history_complete, 'review_mode': 'combined' if simple else 'mixed' if required_tasks & simple_tasks else 'design-first',
            'task_assessments': assessments,
            'required_sections': sorted(required), 'required_tasks': sorted(required_tasks),
            'affected_sections': sorted(affected), 'affected_tasks': sorted(affected & task_ids),
            'affected_acceptance': sorted(key for key in affected if rows[key]['type'] == 'acceptance'),
            'sections': sections, 'deletions': deletions, 'approved': approved,
            'stale': sorted(key for key, row in sections.items() if row['state'] == 'needs-review'),
            'missing': sorted(key for key, row in sections.items() if row['state'] == 'unreviewed'),
            'fully_approved': fully_approved, 'combined_complete': combined_complete,
            'implementation_ready': bool(required_tasks) and all(tasks[key]['ready'] for key in required_tasks) and not gaps,
            'acceptance_ready': acceptance_ready,
            'local_review_valid': fully_approved and scope['complete'] and combined_complete,
            'tasks': tasks, 'pending_decisions': pending, 'required_pending_decisions': required_pending,
            'uncertainties': list(design['assessment']['uncertainties']),
            'scope': scope, 'gaps': gaps}
