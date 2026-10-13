"""Acceptance can precede CS completion; final delivery cannot bypass either review."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workflow as fixtures
import v5_fixtures as v5
from common import Invalid, artifact, create, read, write
import delivery
import designs
import knowledge
import validation
import workflow
import coordination
import github_read


class DeliveryCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs

    def setup_v4(self, complexity='simple', task_id=None, design_task_id=None, extra_check=False):
        self.profile['schema_version'] = 5
        self.check('import app; assert app.add(1,2)==3', environment={'kind': 'stateless'})
        if extra_check:
            self.profile['checks']['safety'] = copy.deepcopy(self.profile['checks']['unit'])
            self.profile['checks']['safety']['purpose'] = 'Additional required project behavior'
            self.profile['required_checks']['code'].append('safety')
        self.task.update(schema_version=5, design_id='D-add', section_ids=['T1'], paths=['app.py'], acceptance_scope='requirement')
        if task_id:
            self.task['id'] = task_id
        self.design = {'schema_version': 5, 'kind': 'design', 'id': 'D-add', 'revision': 1,
            'task_id': design_task_id or self.task['id'], 'assessment': {'complexity': complexity, 'risks': [],
                'effort': 'one hour', 'drivers': ['single function'], 'uncertainties': [], 'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Addition', 'body': self.task['goal'], 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Result', 'body': self.task['acceptance'][0]['expectation'], 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Implement', 'body': 'Implement addition',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []}, 'depends_on': []}]}
        v5.plan(self.design)
        if self.task['id'] != self.design['task_id']:
            self.task.update(acceptance_scope='task', parent=self.design['task_id'])
        self.skill = self.fake_cs()
        write(self.root / '.team-workflow.json', self.profile)
        self.write('task', self.task)
        self.write('design', self.design)
        self.write('brief', knowledge.brief(self.root, self.task, self.skill, [], []))
        run, _ = validation.run_batch(self.root, self.profile, [self.task])
        self.runs = [run.relative_to(self.root).as_posix()]
        approval = designs.approval_draft(self.design, 'carol', 'Explicit plan and code approval',
                    code_digest=validation.source_digest(self.root, self.profile), run_refs=[artifact(self.root, run)])
        self.write('approval', approval)
        self.report = {'schema_version': 5, 'task_id': self.task['id'], 'design': self.name('design'),
            'approvals': [self.name('approval')], 'brief': self.name('brief'), 'runs': self.runs, 'review': self.name('review')}
        review = delivery.review_template(self.root, self.profile, self.task, self.report)
        ref = artifact(self.root, run)
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read public behavior and actual assertion output', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Executed assertion 1+2=3', 'evidence': [ref], 'observations': [v5.observation(ref)]}]
        self.write('review', review)
        self.write('report', self.report)

    def name(self, name):
        return '.team-workflow/' + name + '.json'

    def write(self, name, value):
        write(self.root / self.name(name), value)

    def test_acceptance_needs_no_completed_knowledge_and_final_delivery_does(self):
        self.setup_v4()
        result = delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')
        self.assertTrue(result['business_accepted'])
        self.assertFalse(result['delivery_complete'])
        self.assertFalse(result['closable'])
        with self.assertRaisesRegex(Invalid, 'Knowledge completion'):
            delivery.verify(self.root, self.profile, self.task, self.report, self.skill)
        self.write('acceptance', result)
        completion = knowledge.finish_v4(self.root, self.profile, self.task, self.skill, 'CS-T',
            self.root / self.name('brief'), 'none', 'Existing source owns the requirement', self.root / self.name('acceptance'))
        self.write('knowledge', completion)
        self.report['knowledge'] = self.name('knowledge')
        delivered = delivery.verify(self.root, self.profile, self.task, self.report, self.skill)
        self.assertTrue(delivered['delivery_complete'])
        self.assertFalse(delivered['closable'])
        self.report['close_authorization'] = {'confirmed_by': 'carol', 'reference': 'Explicit user authorization to close this task'}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report, self.skill)['closable'])

    def test_missing_or_stale_combined_approval_cannot_accept(self):
        self.setup_v4()
        self.report['approvals'] = []
        with self.assertRaisesRegex(Invalid, 'approval|review'):
            delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')
        self.report['approvals'] = [self.name('approval')]
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        with self.assertRaisesRegex(Invalid, 'approval|review'):
            delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')

    def test_late_brief_does_not_backdate_reading(self):
        self.setup_v4()
        value = read(self.root / self.name('brief'))
        value['at'] = '2099-01-01T00:00:00+00:00'
        self.write('brief', value)
        with self.assertRaisesRegex(Invalid, 'after execution'):
            delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')

    def test_weakening_required_checks_does_not_reuse_old_review(self):
        self.setup_v4(extra_check=True)
        self.profile['checks']['unrelated'] = copy.deepcopy(self.profile['checks']['unit'])
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')['business_accepted'])
        self.profile['required_checks']['code'] = ['unit']
        with self.assertRaisesRegex(Invalid, 'validation policy'):
            delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')

    def test_prepare_context_and_verify_cli_roundtrip(self):
        self.setup_v4()
        def cli(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = workflow.main([*args, '--root', str(self.root), '--cs-skill', str(self.skill)])
            return code, json.loads(output.getvalue())
        code, prepared = cli('prepare', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, prepared)
        self.assertTrue(prepared['implementation_ready'])
        code, status = cli('status', '--context', prepared['artifact']['path'])
        self.assertEqual(code, 0, status)
        self.assertFalse(status['closable'])
        code, result = cli('verify', '--task', self.name('task'), '--report', self.name('report'), '--phase', 'acceptance')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'])

    def test_document_only_acceptance_does_not_invent_execution(self):
        self.setup_v4()
        self.task['kind'] = 'docs'
        self.task['acceptance'][0]['checks'] = []
        self.design['sections'][1]['data']['checks'] = []
        self.design['sections'][1]['data']['verification'] = {'method': 'manual', 'coverage': v5.coverage('manual'), 'cases': []}
        self.write('design', self.design)
        self.write('brief', knowledge.brief(self.root, self.task, self.skill, [], []))
        self.report['runs'] = []
        approval = designs.approval_draft(self.design, 'carol', 'Read the content and its scope',
                    code_digest=validation.source_digest(self.root, self.profile), run_refs=[])
        self.write('approval', approval)
        review = delivery.review_template(self.root, self.profile, self.task, self.report)
        ref = artifact(self.root, self.root / 'app.py')
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read actual content against the requirement', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Content requirement inspected', 'evidence': [ref], 'observations': [{'kind': 'manual', 'observer': 'carol', 'at': '2026-01-01T00:00:00+00:00', 'steps': ['Read content against the requirement'], 'result': 'Required content present', 'coverage': v5.coverage('manual'), 'evidence': [ref]}]}]
        self.write('review', review)
        result = delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')
        self.assertEqual(result['checks'], [])

    def test_readable_pending_status_and_report_status_execute_no_project_commands(self):
        self.setup_v4(complexity='medium')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['status', '--root', str(self.root), '--task', self.name('task'),
                                  '--design', self.name('design'), '--format', 'text'])
        self.assertEqual(code, 0)
        self.assertNotIn('通过', output.getvalue())
        self.assertIn('scope-global', output.getvalue())
        marker = self.root / 'should-not-be-created'
        import sys
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture',
            'identity': [sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).write_text("bad"); print("fixture")']}
        write(self.root / '.team-workflow.json', self.profile)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['status', '--root', str(self.root), '--task', self.name('task'), '--report', self.name('report')])
        self.assertEqual(code, 0, output.getvalue())
        self.assertFalse(marker.exists())
        self.assertFalse(json.loads(output.getvalue())['business_accepted'])

    def test_parent_withdrawal_during_child_acceptance_is_rejected(self):
        parent = 'https://github.com/example/project/issues/1'
        child = 'https://github.com/example/project/issues/2'
        self.setup_v4(task_id=child, design_task_id=parent)
        parent_task = {**self.task, 'id': parent, 'acceptance_scope': 'requirement'}
        parent_task.pop('parent', None)
        def issue(url, task, parent_url=None):
            return {'html_url': url, 'body': '```team-workflow-task\n' + json.dumps(
                {'schema_version': 5, 'parent': parent_url, 'task': task}) + '\n```',
                'assignees': [{'login': 'bob'}], 'comments_data': []}
        parent_issue, child_issue = issue(parent, parent_task), issue(child, self.task, parent)
        withdrawal, watching, count = None, False, 0
        def append(draft):
            parent_issue['comments_data'].append({'html_url': parent + '#issuecomment-' + str(len(parent_issue['comments_data']) + 1),
                'body': draft['markdown'], 'user': {'login': draft['record'].get('creator', 'carol')}})
        def api(endpoint, **kwargs):
            nonlocal count
            selected = parent_issue if '/issues/1' in endpoint else child_issue
            if selected is parent_issue and watching and '/comments' not in endpoint:
                count += 1
                if count == 2:
                    append(withdrawal)
            return copy.deepcopy(selected['comments_data'] if '/comments' in endpoint else selected)
        with patch.object(github_read, 'api', side_effect=api):
            append(coordination.draft_design(parent, self.design))
            accepted = coordination.draft_approval(parent, {'reviewer': 'carol', 'confirmation': 'Final code and plan accepted',
                'code_digest': validation.source_digest(self.root, self.profile),
                'run_refs': [artifact(self.root, self.root / path) for path in self.runs]})
            append(accepted)
            self.write('approval', accepted['record']['approval'])
            withdrawal = coordination.draft_approval(parent, {'reviewer': 'carol', 'confirmation': 'A contract requirement needs correction',
                'decision': 'changes-requested'})
            watching = True
            with self.assertRaisesRegex(Invalid, 'Platform requirements, approvals'):
                delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')


if __name__ == '__main__':
    unittest.main()
