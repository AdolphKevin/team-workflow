"""Read-only v2 verification. Local traceability is not signed evidence."""
from pathlib import Path

from common import (Invalid, artifact_valid, binding, digest, inside, obj, read,
                    require, sha, strings, task_valid, text, tool_identity)
import knowledge


def passed(row, label):
    require(isinstance(row, dict) and row.get('status') == 'passed', f'{label} has not passed')
    text(row.get('summary'))


def scenario_review(root, out_path, check, captured):
    """Respect the project's separate, evidence-bound Codex scenario verdict."""
    contract = check['review']
    report_path = inside(out_path, contract['path'][len('{output}/'):])
    review = read(report_path)
    require(isinstance(review, dict), 'Invalid scenario review')
    require(review.get('schema_version') == 1 and review.get('reviewer') == 'codex', 'Unknown scenario review contract')
    require(review.get('status') == 'PASS' and review.get('scenario_run_status') == 'COMPLETED', 'Scenario review not passed')
    text(review.get('summary'))
    require(review.get('findings') == [], 'Scenario review has unresolved findings')
    reviewed = review.get('reviewed_artifacts')
    require(isinstance(reviewed, dict), 'Scenario review needs artifact hashes')
    for name in contract['required_artifacts']:
        path = inside(out_path, name)
        current = sha(path)
        require(captured.get(path.relative_to(root).as_posix()) == current, 'Scenario artifact changed after execution')
        require(reviewed.get(name) == 'sha256:' + current, 'Scenario review artifact mismatch')
    # Additional evidence cited by the reviewer must also remain current.
    for name, value in reviewed.items():
        require(value == 'sha256:' + sha(inside(out_path, name)), 'Scenario review has stale additional evidence')
    manifest = read(inside(out_path, 'manifest.json'))
    require(bool(review.get('run_id')) and review['run_id'] == manifest.get('run_id'), 'Scenario run identity mismatch')


class Incomplete(Invalid):
    def __init__(self, message, layers):
        super().__init__(message)
        self.layers = {key: ('incomplete' if state == 'checking' else state) for key, state in layers.items()}


def verify(root, profile, task, report, cs_skill):
    layers = dict.fromkeys(('materials', 'execution', 'review', 'knowledge'), 'not-evaluated')
    try:
        return verify_layers(root, profile, task, report, cs_skill, layers)
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        raise Incomplete(str(exc), layers) from exc


def verify_layers(root, profile, task, report, cs_skill, layers):
    layers['materials'] = 'checking'
    required = task_valid(task, profile, root)
    current = binding(root, profile, task)
    obj(report, {'schema_version', 'task_id', 'runs', 'review', 'knowledge'}, {'issue'})
    require(type(report['schema_version']) is int and report['schema_version'] in (2, 3), 'Expected report schema_version 2 or 3; v1 is material-only')
    require(report['task_id'] == task['id'], 'Delivery task mismatch')
    if report['schema_version'] == 3:
        import handoffs
        import github_read
        require(report.get('issue') == task['id'], 'v3 delivery needs its canonical issue')
        source = handoffs.task_source(github_read.issue(report['issue']))
        require(source['task'] == task, 'Task requirements changed on the platform')
        continuation = handoffs.resume(root, profile, report['issue'], cs_skill)
        require(continuation['ok'], 'Delivery collaboration gaps: ' + '; '.join(continuation['gaps']))
        progress = continuation['current']
        require(not progress['remaining'] and not progress['questions'], 'Delivery still has unfinished work or open questions')
    strings(report['runs'])
    for field in ('review', 'knowledge'):
        require(inside(root, report[field]).is_file(), f'Missing {field} record')
    layers['materials'] = 'passed'
    layers['execution'] = 'checking'
    results, records = {}, []
    for name in report['runs']:
        record = read(inside(root, name))
        require(isinstance(record, dict), 'Invalid execution record')
        if record.get('schema_version') == 3 and report['schema_version'] == 3:
            import portable
            row, manifest = portable.validate_import(root, profile, record)
            require(row['id'] not in results, 'Duplicate result; choose the final run for each check')
            results[row['id']] = row
            records.append({**record, 'portable_source': manifest['source_after']})
            continue
        require(record.get('schema_version') == 2 and record.get('kind') == 'execution', 'Missing execution record')
        require(record.get('project') == profile['project'] and record.get('task_id') == task['id'], 'Execution identity mismatch')
        require(record.get('binding') == current, 'Execution evidence is stale: workspace/profile/task changed')
        require(record.get('source_unchanged') is True, 'Source changed during execution')
        require(record.get('tools') == tool_identity(), 'Execution tools changed; rerun with this installed release')
        for row in record.get('results', []):
            require(isinstance(row, dict), 'Invalid execution result')
            key = row.get('id')
            require(key in profile['checks'], 'Unknown recorded check')
            require(key not in results, 'Duplicate result; choose the final run for each check')
            require(row.get('status') == 'passed' and row.get('state') == 'finished' and row.get('exit_code') == 0, f'Check did not pass: {key}')
            require(bool(row.get('artifacts')), 'Missing execution artifacts')
            for item in row['artifacts']:
                artifact_valid(root, item)
            # Re-decode native output to catch edited declarations and accidental report corruption.
            from execution import decode
            stdout = [a for a in row['artifacts'] if a['path'].endswith('/stdout.txt')]
            require(len(stdout) == 1, 'Missing stdout capture')
            out_path = inside(root, stdout[0]['path']).parent
            argv = [x.replace('{output}', str(out_path)) for x in profile['checks'][key]['argv']]
            require(row.get('argv') == argv and row.get('cwd') == profile['checks'][key]['cwd'], 'Recorded command mismatch')
            check = profile['checks'][key]
            expected = ['stdout.txt', 'stderr.txt'] + [name[len('{output}/'):] for name in check.get('artifacts', [])]
            if check.get('report'):
                expected.append(check['report'][len('{output}/'):])
            captured = {item['path'] for item in row['artifacts']}
            require(all((out_path / name).relative_to(root).as_posix() in captured for name in expected),
                    'Execution artifact manifest is incomplete')
            native = out_path / check['report'][len('{output}/'):] if check.get('report') else None
            decoded = decode(check, {'state': row['state'], 'exit_code': row['exit_code'],
                                    'stdout': inside(root, stdout[0]['path']).read_text()}, native)
            require(decoded[0] == 'passed' and decoded[1] == row.get('cases'), f'Result does not match artifacts: {key}')
            if 'review' in check:
                scenario_review(root, out_path, check, {a['path']: a['sha256'] for a in row['artifacts']})
            results[key] = row
        records.append(record)
    require(set(required) <= results.keys(), 'Required execution missing: ' + ', '.join(sorted(set(required) - results.keys())))
    layers['execution'] = 'passed'
    layers['review'] = 'checking'
    review = read(inside(root, report['review']))
    require(isinstance(review, dict), 'Invalid review record')
    require(review.get('schema_version') == 2 and review.get('kind') == 'review', 'Expected v2 review')
    require(review.get('task_id') == task['id'] and review.get('binding') == current, 'Review does not cover current task/workspace')
    text(review.get('reviewer'))
    for axis in ('standards', 'spec'):
        passed(review.get(axis), axis)
        require(bool(review[axis].get('evidence')), f'{axis} review needs evidence')
        for item in review[axis]['evidence']:
            artifact_valid(root, item)
    findings = review.get('findings')
    require(isinstance(findings, list), 'Review findings must be an array')
    for finding in findings:
        obj(finding, {'blocking', 'summary', 'resolved'})
        require(type(finding['blocking']) is bool and type(finding['resolved']) is bool, 'Invalid finding state')
        text(finding['summary'])
        require(not finding['blocking'] or finding['resolved'], 'Unresolved blocking finding')
    require(review.get('risks') == task['risks'], 'Review must assess declared risks')
    require(review.get('knowledge_conflicts_resolved') is True, 'Knowledge conflicts remain unresolved')
    assessed = {}
    require(isinstance(review.get('acceptance'), list), 'Missing acceptance review')
    for row in review['acceptance']:
        passed(row, 'Acceptance')
        key = row.get('id')
        require(key not in assessed, 'Duplicate acceptance review')
        require(bool(row.get('evidence')), 'Acceptance needs concrete evidence')
        for item in row['evidence']:
            artifact_valid(root, item)
        assessed[key] = row
    require(set(assessed) == {row['id'] for row in task['acceptance']}, 'Acceptance coverage mismatch')
    layers['review'] = 'passed'
    layers['knowledge'] = 'checking'
    completion = read(inside(root, report['knowledge']))
    require(isinstance(completion, dict), 'Invalid knowledge completion')
    require(completion.get('schema_version') == 2 and completion.get('kind') == 'knowledge-completion', 'Missing CS completion record')
    require(completion.get('task_id') == task['id'] and completion.get('task_digest') == digest(task), 'Knowledge task mismatch')
    require(completion.get('wiki_digest') == knowledge.wiki_state(root), 'Knowledge changed after completion; recapture and review')
    brief_path = artifact_valid(root, completion['brief'])
    brief = read(brief_path)
    require(isinstance(brief, dict), 'Invalid knowledge brief')
    require(brief.get('schema_version') == 2 and brief.get('kind') == 'knowledge-brief', 'Missing knowledge brief')
    require(brief.get('task_id') == task['id'] and brief.get('task_digest') == digest(task), 'Knowledge brief belongs to another task version')
    for item in completion.get('files', []):
        artifact_valid(root, item)
    require(bool(completion.get('files')), 'Knowledge files missing')
    require(completion.get('disposition') in ('none', 'reused', 'updated', 'added'), 'Unknown knowledge disposition')
    text(completion.get('reason'))
    require(review.get('knowledge') == {'brief': completion['brief'], 'completion':
            {'path': report['knowledge'], 'sha256': sha(inside(root, report['knowledge']))}},
            'Review must bind both knowledge brief and completed writeback')
    skill = knowledge.skill_path(cs_skill)
    require(completion.get('cs_identity') == knowledge.identity(skill), 'CS runtime changed; recapture completion')
    fresh = knowledge.finish(root, task, skill, completion['cs_task_id'], brief_path,
                             completion['disposition'], completion['reason'])
    require(fresh['document_state'] == completion.get('document_state'), 'Source documents changed after completion')
    require(fresh['cs_task_revision'] == completion['cs_task_revision'], 'CS task revision changed')
    require(binding(root, profile, task) == current, 'Workspace changed while verifying')
    layers['knowledge'] = 'passed'
    return {'ok': True, 'scope': 'local-workflow', 'status': 'complete', 'project': profile['project'],
            'task_id': task['id'], 'binding': current, 'checks': sorted(results),
            'layers': layers,
            'assurance': 'local-records-and-agent-review; not signed or exhaustive business proof',
            'records': records}


def review_template(root, profile, task, brief_path, completion_path):
    require(brief_path and completion_path, 'Review needs knowledge brief and completion paths')
    from common import artifact
    draft = {'status': 'pending', 'summary': '', 'evidence': []}
    return {'schema_version': 2, 'kind': 'review', 'task_id': task['id'], 'binding': binding(root, profile, task),
            'reviewer': '', 'standards': dict(draft), 'spec': dict(draft), 'risks': task['risks'],
            'knowledge_conflicts_resolved': False,
            'knowledge': {'brief': artifact(root, brief_path), 'completion': artifact(root, completion_path)},
            'acceptance': [{'id': row['id'], **draft} for row in task['acceptance']], 'findings': []}


def participants(manifest):
    obj(manifest, {'schema_version', 'task_id', 'participants', 'joint'})
    require(manifest['schema_version'] == 2, 'Expected joint schema_version 2')
    require(isinstance(manifest['participants'], list) and len(manifest['participants']) >= 2, 'At least two participating repositories required')
    seen = set()
    roots = set()
    entries = []
    from common import profile_valid
    for row in manifest['participants']:
        obj(row, {'root', 'profile', 'task', 'report'})
        root = Path(row['root']).expanduser().resolve()
        require(root not in roots, 'Duplicate participant root')
        roots.add(root)
        profile = profile_valid(read(inside(root, row['profile'])), root)
        task = read(inside(root, row['task']))
        task_valid(task, profile, root)
        require(profile['project'] not in seen, 'Duplicate participant project')
        require(task['id'] == manifest['task_id'], 'Participants must share one logical task ID')
        seen.add(profile['project'])
        entries.append((root, profile, task, row['report']))
    require(manifest['joint'] in seen, 'joint must identify the repository owning the joint check')
    return entries


def participant_binding(manifest):
    return {p['project']: binding(r, p, t) for r, p, t, _ in participants(manifest)}


def aggregate(manifest, cs_skill, repositories=None):
    if manifest.get('schema_version') == 3:
        return aggregate_v3(manifest, cs_skill, repositories or {})
    start = participant_binding(manifest)
    output = []
    joint_records = []
    for root, profile, task, report in participants(manifest):
        result = verify(root, profile, task, read(inside(root, report)), cs_skill)
        if profile['project'] == manifest['joint']:
            require('cross-service' in task['risks'], 'Joint owner must declare cross-service risk')
            joint_ids = set(profile['risk_checks']['cross-service'])
            joint_records = [rec for rec in result['records'] if joint_ids & {r['id'] for r in rec['results']}]
        result.pop('records')
        output.append(result)
    require(bool(joint_records), 'Joint execution is missing')
    for record in joint_records:
        require(record.get('participants') == start and record.get('participants_unchanged') is True,
                'Joint evidence is missing, stale, or participants changed during execution')
    require(participant_binding(manifest) == start, 'Participant changed during aggregation')
    return {'ok': True, 'scope': 'joint-local-workflow', 'status': 'complete', 'task_id': manifest['task_id'], 'participants': output}


def aggregate_v3(manifest, cs_skill, repositories):
    """Resolve portable repository identities through caller-local checkouts."""
    from common import profile_valid, git
    import github_read
    import handoffs
    import portable
    obj(manifest, {'schema_version', 'task_id', 'joint', 'participants', 'dependencies'})
    github_read.issue_ref(manifest['task_id'])
    require(len(manifest['participants']) >= 2, 'Joint delivery needs at least two participants')
    expected, output, joint_records, starts = {}, [], [], {}
    for row in manifest['participants'] + manifest['dependencies']:
        require(isinstance(row, dict), 'Invalid participant or dependency')
        github_read.repository(row['repository'])
        require(row['repository'] not in expected, 'Duplicate participant/dependency')
        expected[row['repository']] = text(row['commit'])
        root = repositories.get(row['repository'])
        require(root is not None, 'Missing local checkout mapping: ' + row['repository'])
        require(portable.repository_id(root) == row['repository'] and git(root, 'rev-parse', 'HEAD').decode().strip() == row['commit'],
                'Participant or dependency commit differs: ' + row['repository'])
        github_read.commit(row['repository'], row['commit'])
        starts[row['repository']] = portable.source_state(root, {'inputs': []})
        require(all(s['clean'] for s in starts[row['repository']]['repositories'].values()), 'Joint participant has unshared changes')
    for row in manifest['dependencies']:
        obj(row, {'repository', 'commit'})
    for row in manifest['participants']:
        obj(row, {'repository', 'commit', 'profile', 'task', 'report'})
        root = repositories[row['repository']]
        profile = profile_valid(read(inside(root, row['profile'])), root)
        task = read(inside(root, row['task']))
        source = handoffs.task_source(github_read.issue(task['id']))
        require((source['parent'] or task['id']) == manifest['task_id'], 'Participant belongs to another parent task')
        report = read(inside(root, row['report']))
        require(report.get('schema_version') == 3, 'Portable aggregation requires v3 delivery records')
        result = verify(root, profile, task, report, cs_skill)
        if row['repository'] == manifest['joint']:
            require('cross-service' in task['risks'], 'Joint owner must declare cross-service risk')
            needed = set(profile['risk_checks']['cross-service'])
            joint_records = [r for r in result['records'] if r.get('result', {}).get('id') in needed]
            require({r['result']['id'] for r in joint_records} == needed, 'Portable joint check evidence is missing')
        result.pop('records')
        output.append(result)
    require(bool(joint_records), 'Joint owner or execution is missing')
    for record in joint_records:
        actual = {repo: s['commit'] for repo, s in record['portable_source']['repositories'].items()}
        require(actual == expected, 'Joint evidence omits or mismatches a participant/shared dependency')
        require(not record['portable_source']['files'], 'Joint external file inputs need versioned repositories')
    for repo in expected:
        require(portable.source_state(repositories[repo], {'inputs': []}) == starts[repo], 'Sources changed during aggregation')
    return {'schema_version': 3, 'ok': True, 'scope': 'joint-portable-workflow', 'status': 'complete',
            'task_id': manifest['task_id'], 'versions': expected, 'participants': output}
