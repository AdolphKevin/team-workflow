"""Start names each section needing consent and gives the approval command."""
import contextlib
import copy
import io
import json
import shlex
import unittest
from unittest.mock import patch

import test_four_command_delivery as four
import test_coordination as shared
import test_workflow as fixtures
from common import write
import commands
import coordination
import designs
import plan_fixtures as plans
from platform_fixtures import transport
from tw_runtime.team import platform_script
import workflow


class PendingSections(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, command = base.setUp, base.git, base.check, base.configure, base.command

    def revise(self):
        self.configure('medium')
        self.before = copy.deepcopy(self.design)
        write(self.root / '.tw/local/approval.json', designs.approval_draft(self.before, 'carol'))
        plans.write_design(self.root / '.tw/local/before.md', self.before)
        self.design['revision'] = 2
        self.design['sections'][1]['body'] = 'Addition now also specifies a negative example'
        plans.write_design(self.root / '.tw/local/design.md', self.design)

    def test_start_lists_changed_and_dependency_reasons_in_document_order(self):
        self.revise()
        args = ('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                '--design-history', '.tw/local/before.md', '--approval', '.tw/local/approval.json')
        code, result = self.command(*args)
        self.assertEqual(code, 0, result)
        self.assertEqual([(row['id'], row['title'], row['reason']) for row in result['pending_sections']],
                         [('A1', 'Result', '内容已改'), ('T1', 'Implement', '依赖 A1 已改')])
        self.assertIn('approval-draft', result['next_action'])
        self.assertIn('--task', result['next_action'])
        self.assertIn('--design', result['next_action'])
        self.assertIn('<评审人>', result['next_action'])
        text = commands.readable(result)
        self.assertIn('待确认章节：\nA1 Result：内容已改\nT1 Implement：依赖 A1 已改', text)
        # The checklist must not point past the missing consent.
        self.assertIn('下一步：取得待确认章节的批准\n' + result['next_action'], text)
        self.assertNotIn('下一步：运行检查', text)
        code, continued = self.command(*args)
        self.assertEqual(code, 0, continued)
        self.assertTrue(continued['continued'])
        self.assertEqual(continued['pending_sections'], result['pending_sections'])
        self.assertIn('approval-draft', continued['next_action'])
        text = commands.readable(continued)
        self.assertIn('下一步：取得待确认章节的批准\n' + continued['next_action'], text)
        self.assertNotIn('下一步：运行检查', text)

    def test_approval_status_explains_assessment_and_each_unapproved_state(self):
        self.configure('medium')
        before = copy.deepcopy(self.design)
        approval = designs.approval_draft(before, 'carol')
        self.design['revision'] = 2
        self.design['assessment']['effort'] = 'two hours'
        status = designs.approval_status(self.design, [approval], history=[before], changed_paths=[])
        self.assertEqual({row['reason'] for row in status['sections'].values()}, {'评估已改'})
        for decision, reason in [('changes-requested', '评审人要求修改'), ('deferred', '暂缓')]:
            status = designs.approval_status(before, [designs.approval_draft(before, 'carol', decision=decision)], changed_paths=[])
            self.assertEqual({row['reason'] for row in status['sections'].values()}, {reason})
        status = designs.approval_status(before, [], changed_paths=[])
        self.assertEqual({row['reason'] for row in status['sections'].values()}, {'未评审'})


class ParentApprovalCommand(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def test_child_start_approval_command_targets_design_owner(self):
        self.prepare()
        fixtures.write_config(self.root, self.profile)
        child_url = 'https://github.com/example/project/issues/2'
        child_task = {**copy.deepcopy(self.task), 'id': child_url, 'parent': self.url, 'acceptance_scope': 'task'}
        self.design['sections'] += [
            {'id': 'A2', 'type': 'acceptance', 'title': 'Other result', 'body': 'Other behavior',
             'data': {'checks': ['unit']}, 'depends_on': []},
            {'id': 'T2', 'type': 'task', 'title': 'Other work', 'body': 'Other implementation',
             'data': {'acceptance': ['A2'], 'scope': ['other.py'], 'blocked_by': []}, 'depends_on': []}]
        plans.plan(self.design)
        self.task['section_ids'] = ['T1', 'T2']
        self.task['acceptance'].append({'id': 'A2'})
        self.issue['body'] = self.body()
        child = {'html_url': child_url, 'state': 'open', 'comments_data': [], 'assignees': [],
                 'body': plans.task_body(child_task, self.url)}

        def api(endpoint, **kwargs):
            if endpoint == 'repos/example/project/issues/2':
                return copy.deepcopy(child)
            if endpoint.startswith('repos/example/project/issues/2/comments'):
                return []
            return self.github(endpoint, **kwargs)

        with patch.object(platform_script, 'call', side_effect=transport(api)):
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = workflow.main(['start', '--root', str(self.root), '--issue', child_url])
            result = json.loads(output.getvalue())
            suggested = shlex.split(result['next_action'].replace('<评审人>', 'carol'))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                approval_code = workflow.main(suggested[2:])
            approval = json.loads(output.getvalue())
        self.assertEqual(code, 0, result)
        self.assertEqual([row['id'] for row in result['pending_sections']], ['scope-global', 'A1', 'T1'])
        self.assertIn('--issue ' + self.url, result['next_action'])
        self.assertNotIn(child_url, result['next_action'])
        self.assertEqual(approval_code, 0, approval)
        self.assertEqual(set(approval['record']['approval']['sections']), {'scope-global', 'A1', 'T1'})
