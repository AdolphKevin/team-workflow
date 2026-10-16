"""Existing issues are brought into the team flow with drafts only; GitHub is read, never written."""
import contextlib
import copy
import io
import json
import unittest
import test_workflow as fixtures
from unittest.mock import patch

import test_coordination
from common import Invalid, write
import coordination
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import issue_draft
import workflow
import plan_fixtures as plans

CHILD = 'https://github.com/example/project/issues/2'


class IssueAdoption(unittest.TestCase):
    base = test_coordination.CoordinationCases
    git, check, publish_fixture, body = base.git, base.check, base.publish_fixture, base.body

    def setUp(self):
        self.base.setUp(self)
        self.base.prepare(self)
        self.task = plans.written_task(self.task)
        self.issue['body'] = 'Add two inputs.\n\nOriginal MATT spec text stays as written.'
        self.design_path = plans.design_source(self.root, self.design)
        self.child = {'html_url': CHILD, 'state': 'open', 'assignees': [{'login': 'bob'}], 'comments_data': [],
                      'body': 'Follow-up: subtraction keeps working.'}
        self.child_task = copy.deepcopy(self.task)
        self.child_task.update(id=CHILD, parent=self.url, acceptance_scope='task')
        self.patch = patch.object(platform_read, 'call', side_effect=platform_transport(self.github))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def github(self, endpoint, paginate=False, binary=False):
        if endpoint.startswith('repos/example/project/issues/2'):
            return copy.deepcopy(self.child['comments_data'] if '/comments' in endpoint else self.child)
        return self.base.github(self, endpoint, paginate, binary)

    def test_legacy_issue_gets_body_design_and_approval_request_without_writes(self):
        result = issue_draft.draft(self.root, self.profile, self.task, self.design, [self.child_task], 'carol', design_path=self.design_path)
        self.assertTrue(result['read_only'])
        own, child = result['issues']
        self.assertTrue(own['body'].startswith('Add two inputs.\n\nOriginal MATT spec text stays as written.\n\n<!-- tw-task:start -->'))
        self.assertIn('`A1`', own['approval_request'])
        self.assertIn('评审人：carol', own['approval_request'])
        self.assertNotIn('design_comment', child)
        self.assertEqual(coordination.task_source({'html_url': CHILD, 'body': child['body']})['parent'], self.url)
        self.assertEqual(self.issue['comments_data'], [])  # nothing posted
        # The person posts the drafts in order; the platform then reads cleanly and approval can proceed.
        self.issue['body'] = own['body']
        self.child['body'] = child['body']
        self.publish_fixture({'markdown': own['design_comment']}, 'alice')
        state = coordination.load(self.url)
        self.assertEqual((state['design'], state['gaps']), (self.design, []))
        approval = coordination.draft_approval(self.url, {'reviewer': 'carol', 'confirmation': 'All sections approved'})
        self.publish_fixture(approval, 'carol')
        self.assertEqual(coordination.load(CHILD)['approvals'][0]['reviewer'], 'carol')

    def test_re_drafting_an_adopted_issue_replaces_only_the_structured_block(self):
        first = issue_draft.draft(self.root, self.profile, self.task)['issues'][0]['body']
        self.issue['body'] = first
        again = issue_draft.draft(self.root, self.profile, self.task)['issues'][0]
        self.assertEqual(again['body'], first)
        self.assertFalse(again['body_changed'])
        self.assertEqual(again['body'].count('<!-- tw-record '), 1)

    def test_design_history_reconciliation_keeps_task_body_titles_and_omits_design_outputs(self):
        first = issue_draft.draft(self.root, self.profile, self.task, self.design,
                                  design_path=self.design_path)['issues'][0]
        self.issue['body'] = first['body']
        self.publish_fixture({'markdown': first['design_comment']}, 'alice')
        self.publish_fixture({'markdown': first['design_comment']}, 'alice')
        self.design['revision'] = 2
        self.design_path = plans.design_source(self.root, self.design)
        fixtures.write_config(self.root, self.profile)
        task_path = '.tw/local/adopt-task.json'
        write(self.root / task_path, self.task)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['issue-draft', '--root', str(self.root), '--task', task_path,
                                  '--design', str(self.design_path), '--reviewer', 'carol'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0, result)
        self.assertTrue(result['ok'])
        own, = result['issues']
        self.assertIn('验收项：\n- A1 Addition result\n', own['body'])
        self.assertIn('Original MATT spec text stays as written.', own['body'])
        self.assertEqual(coordination.task_source({'html_url': self.url, 'body': own['body']})['task'], self.task)
        for key in ('design_comment', 'pr_description', 'approval_request'):
            self.assertNotIn(key, own)
        self.assertIn('design-draft --issue ' + self.url + ' --record <方案.md> --reconcile "<原因>"',
                      '\n'.join(result['next_steps']))
        self.assertEqual(len(self.issue['comments_data']), 2)

    def test_other_design_draft_refusals_still_refuse_issue_draft(self):
        self.design['revision'] = 2
        self.design_path = plans.design_source(self.root, self.design)
        with self.assertRaisesRegex(Invalid, 'Design revisions must advance by one'):
            issue_draft.draft(self.root, self.profile, self.task, self.design, design_path=self.design_path)

    def test_prefixed_titles_appear_once_in_visible_acceptance_and_approval_request(self):
        self.design['sections'][1]['title'] = 'A1 两个 worktree'
        self.design_path = plans.design_source(self.root, self.design)
        result = issue_draft.draft(self.root, self.profile, self.task, self.design,
                                   design_path=self.design_path)
        own, = result['issues']
        self.assertIn('验收项：\n- A1 两个 worktree\n', own['body'])
        self.assertIn('- `A1` 两个 worktree（指纹 ', own['approval_request'])
        self.assertNotIn('A1 A1 两个 worktree', own['body'])
        self.assertNotIn('`A1` A1 两个 worktree', own['approval_request'])

    def test_child_must_declare_the_shared_design_parent(self):
        self.child_task.pop('parent')
        with self.assertRaisesRegex(Invalid, 'set "parent"'):
            issue_draft.draft(self.root, self.profile, self.task, self.design, [self.child_task], design_path=self.design_path)
        with self.assertRaisesRegex(Invalid, 'owns the design'):
            issue_draft.draft(self.root, self.profile, dict(self.child_task, parent=self.url), self.design)

    def test_commands_on_an_unadopted_issue_point_to_issue_draft(self):
        fixtures.write_config(self.root, self.profile)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = workflow.main(['start', '--root', str(self.root), '--issue', self.url])
        result = json.loads(output.getvalue())
        self.assertEqual((status, result['error_code']), (1, 'issue-not-adopted'))
        self.assertIn('issue-draft', result['next_action'])

    def test_adopted_child_reports_unadopted_parent_and_its_next_action(self):
        self.child['body'] = plans.task_body(self.child_task, self.url, self.child['body'])
        fixtures.write_config(self.root, self.profile)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['start', '--root', str(self.root), '--issue', CHILD,
])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1, result)
        self.assertEqual(result['error_code'], 'parent-issue-not-adopted')
        self.assertIn(self.url, result['problem'])
        self.assertIn(self.url, result['next_action'])
        self.assertIn('issue-draft', result['next_action'])
        self.assertIn('<parent-task.json>', result['next_action'])
        self.assertNotIn(CHILD, result['next_action'])


if __name__ == '__main__':
    unittest.main()
