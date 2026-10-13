#!/usr/bin/env python3
"""Exercise v5 acceptance and structured knowledge against the real independent CS CLI."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'skills/team-workflow/scripts'))
from common import Invalid, create, read, write
from test_delivery_v4 import DeliveryCases
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
        case.setup_v4()
        normalized = knowledge.call(skill, case.root, ['template', '--external-ref', 'github=https://github.com/Example/Project/issues/017'])
        assert normalized['task']['external_refs'] == [knowledge.external_ref({'id': 'https://github.com/Example/Project/issues/17'})]
        accepted = delivery.verify(case.root, case.profile, case.task, case.report, skill, 'acceptance')
        assert accepted['business_accepted'] and not accepted['delivery_complete']
        case.write('acceptance', accepted)
        external = knowledge.external_ref(case.task)
        template = knowledge.completion_template(case.root, case.profile, case.task, skill,
            case.root / case.name('acceptance'))
        template['task'].update(request='Verify addition at the public entry.', summary='Executed the arithmetic entry assertion.',
            result='The assertion 1+2=3 passed and the actual plan/code review was recorded.',
            scopes=[{'repository': 'self', 'path': 'app.py'}],
            verification=['Executed the configured Python assertion and v5 business acceptance.'],
            knowledge_summary='The existing public requirement owns the behavior; no additional durable fact is needed.')
        with tempfile.TemporaryDirectory(prefix='workflow-v5-cs-plan-') as temporary:
            payload, plan = Path(temporary) / 'learning.json', Path(temporary) / 'plan.token'
            write(payload, template)
            knowledge.call(skill, case.root, ['learn', '--file', str(payload), '--dry-run', '--plan-out', str(plan)])
            learned = knowledge.call(skill, case.root, ['learn', '--file', str(payload), '--plan-file', str(plan)])
        knowledge.call(skill, case.root, ['doctor'])
        case.git('add', '.codestable')
        case.git('commit', '-qm', 'fixture knowledge only')
        captured = knowledge.finish_v4(case.root, case.profile, case.task, skill, learned['task_id'],
            case.root / case.name('brief'), 'none', 'Original requirement owns the behavior',
            case.root / case.name('acceptance'))
        assert captured['external_refs'] == [external]
        case.write('knowledge', captured)
        case.report['knowledge'] = case.name('knowledge')
        result = delivery.verify(case.root, case.profile, case.task, case.report, skill)
        assert result['delivery_complete'] and not result['closable']
        assert knowledge.call(skill, case.root, ['task-files', '--task-id', learned['task_id'], '--format', 'json'])['external_refs'] == [external]
        return {'ok': True, 'checks': ['real-v5-acceptance-before-learn', 'structured-external-task-association',
                    'github-identity-normalization-agrees-with-cs',
                    'knowledge-only-commit-reuses-business-execution', 'real-v5-final-delivery-without-close-permission'],
                'scope': 'isolated-public-interface-fixture; not a human pilot'}
    finally:
        case.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs-skill', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.cs_skill.resolve()), ensure_ascii=False, indent=2))
    except Invalid as exc:
        print(json.dumps({'ok': False, 'problem': str(exc), 'next_action': 'Use a CS runtime declaring the v5 integration capabilities; do not downgrade task verification.'}))
        sys.exit(1)
