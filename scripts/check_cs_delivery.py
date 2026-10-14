#!/usr/bin/env python3
"""Exercise business acceptance and structured knowledge delivery against the real independent CS CLI."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'skills/team-workflow/scripts'))
from common import Invalid, create, write
from test_delivery import DeliveryCases
import delivery
import knowledge


def run(skill):
    case = DeliveryCases()
    case.setUp()
    try:
        def initialize():
            knowledge.call(skill, case.root, [], bootstrap=True)
            create(case.root / '.codestable/documents/rules.json', {
                'repository': 'self', 'path': 'AGENTS.md', 'title': 'Public behavior',
                'category': 'requirements', 'always': True})
            return skill
        case.fake_cs = initialize
        case.setup_task()
        normalized = knowledge.call(skill, case.root, ['template', '--external-ref', 'github=https://github.com/Example/Project/issues/017'])
        assert normalized['task']['external_refs'] == [knowledge.external_ref({'id': 'https://github.com/Example/Project/issues/17'})]
        accepted = delivery.verify(case.root, case.profile, case.task, case.report, skill, 'acceptance')
        assert accepted['business_accepted'] and not accepted['delivery_complete']
        case.write('acceptance', accepted)
        external = knowledge.external_ref(case.task)
        template = knowledge.completion_template(case.root, case.profile, case.task, skill,
            [case.root / case.name('acceptance')])
        template['task'].update(request='Verify addition at the public entry.', summary='Executed the arithmetic entry assertion.',
            result='The assertion 1+2=3 passed and the actual plan/code review was recorded.',
            scopes=[{'repository': 'self', 'path': 'app.py'}],
            verification=['Executed the configured Python assertion and business acceptance.'],
            knowledge_summary='The existing public requirement owns the behavior; no additional durable fact is needed.')
        with tempfile.TemporaryDirectory(prefix='workflow-cs-plan-') as temporary:
            payload, plan = Path(temporary) / 'learning.json', Path(temporary) / 'plan.token'
            write(payload, template)
            knowledge.call(skill, case.root, ['learn', '--file', str(payload), '--dry-run', '--plan-out', str(plan)])
            learned = knowledge.call(skill, case.root, ['learn', '--file', str(payload), '--plan-file', str(plan)])
        knowledge.call(skill, case.root, ['doctor'])
        case.git('add', '.codestable')
        case.git('commit', '-qm', 'fixture knowledge only')
        captured = knowledge.finish(case.root, case.profile, case.task, skill, learned['task_id'],
            case.root / case.name('brief'), 'none', 'Original requirement owns the behavior',
            case.root / case.name('acceptance'))
        assert captured['external_refs'] == [external]
        case.write('knowledge', captured)
        case.report['knowledge'] = case.name('knowledge')
        result = delivery.verify(case.root, case.profile, case.task, case.report, skill)
        assert result['delivery_complete'] and not result['closable']
        assert knowledge.call(skill, case.root, ['task-files', '--task-id', learned['task_id'], '--format', 'json'])['external_refs'] == [external]
        return {'ok': True, 'checks': ['real-acceptance-before-learn', 'structured-external-task-association',
                    'github-identity-normalization-agrees-with-cs',
                    'knowledge-only-commit-reuses-business-execution', 'real-final-delivery-without-close-permission'],
                'scope': 'isolated-public-interface-fixture; not a human pilot'}
    finally:
        case.doCleanups()


def learn(skill, root, payload):
    with tempfile.TemporaryDirectory(prefix='workflow-cs-plan-') as temporary:
        source, plan = Path(temporary) / 'learning.json', Path(temporary) / 'plan.token'
        write(source, payload)
        preview = knowledge.call(skill, root, ['learn', '--file', str(source), '--dry-run', '--plan-out', str(plan)])
        if preview.get('plan_state') == 'not-needed':
            return preview  # already applied exactly; nothing to write
        return knowledge.call(skill, root, ['learn', '--file', str(source), '--plan-file', str(plan)])


def fill(payload, summary):
    payload['task'].update(request='Fix two issues that share one implementation.', summary=summary,
        result='Each issue was accepted separately against the same executed checks.',
        verification=['Executed the configured Python assertion and business acceptance per issue.'],
        knowledge_summary='The shared requirement owns the behavior; no additional durable fact is needed.')
    return payload


def run_shared(skill):
    """Two issues share one implementation and one CS task; each keeps its own acceptance."""
    import copy
    from test_knowledge_multi import FIRST, SECOND, SharedKnowledgeRecord
    case = SharedKnowledgeRecord('test_both_issues_complete_one_record_with_their_own_acceptance')
    SharedKnowledgeRecord.base.setUp(case)  # not SharedKnowledgeRecord.setUp: that replaces CS with a stub
    try:
        case.fake_cs = lambda: knowledge.call(skill, case.root, [], bootstrap=True) and skill
        case.first_task = copy.deepcopy(case.task)
        task_a, accepted_a = case.accept(FIRST, 'a-')
        task_b, accepted_b = case.accept(SECOND, 'b-')
        first = knowledge.completion_template(case.root, case.profile, task_a, skill, [accepted_a], siblings=[task_b])
        assert first['task']['status'] == 'in-progress'
        assert knowledge.pending_acceptance(first, [task_a, task_b]) == [SECOND]
        created = learn(skill, case.root, fill(first, 'Issue 149 accepted; 150 pending.'))
        task_id = created['task_id']
        second = knowledge.completion_template(case.root, case.profile, task_b, skill, [accepted_b], task_id, siblings=[task_a])
        assert second['task']['status'] == 'completed', second['task']['status']
        learn(skill, case.root, fill(second, 'Both issues accepted.'))
        # An agent working from a stale template resubmits only its own entry; CS keeps the sibling's.
        stale = knowledge.call(skill, case.root, ['template', '--task-id', task_id])
        stale['task']['source']['workflow_acceptances'] = [knowledge.acceptance_entry(case.root, task_a, accepted_a)]
        assert learn(skill, case.root, stale).get('plan_state') == 'not-needed'
        stored = knowledge.call(skill, case.root, ['template', '--task-id', task_id])['task']['source']['workflow_acceptances']
        assert [row['task_id'] for row in stored] == [FIRST, SECOND], stored
        knowledge.call(skill, case.root, ['doctor'])
        case.git('add', '.codestable')
        case.git('commit', '-qm', 'fixture knowledge only')
        for task, accepted, prefix in ((task_a, accepted_a, 'a-'), (task_b, accepted_b, 'b-')):
            completion = knowledge.finish(case.root, case.profile, task, skill, task_id,
                case.root / ('.team-workflow/' + prefix + 'brief.json'), 'none', 'Shared fix', accepted)
            assert completion['acceptance']['path'] == accepted.relative_to(case.root).as_posix()
            assert completion['cs']['integrity'] == 'intact' and completion['cs']['contract_version'] == 1
        return ['shared-record-incremental-acceptance', 'stale-list-keeps-sibling-acceptance',
                'each-issue-finishes-with-own-acceptance']
    finally:
        case.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.cs_skill.resolve())
        result['checks'] += run_shared(args.cs_skill.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Invalid as exc:
        print(json.dumps({'ok': False, 'problem': str(exc), 'next_action': 'Use a CS runtime declaring the required integration capabilities; do not downgrade task verification.'}))
        sys.exit(1)
