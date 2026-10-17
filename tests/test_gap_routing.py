"""E5 补查：开工、方案对账与交接按问题代码处理。"""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workflow
import test_markdown_records
import test_coordination
from test_designs import example
from common import Invalid
import coordination
import designs
import workflow


class GapRouting(unittest.TestCase):
    def test_approval_reconciliation_uses_code_with_arbitrary_message(self):
        url = 'https://github.com/example/project/issues/1'
        for message in ('任意说明甲', '完全不同的说明乙'):
            state = {'design': example(), 'task': {'section_ids': ['T1']},
                     'design_issue': url, 'design_gaps': [message],
                     'design_errors': [{'error_code': 'platform-approval-invalid', 'problem': message}],
                     'history_digest': 'a' * 64, 'approvals': [], 'history': []}
            value = {'reviewer': 'carol', 'section_ids': [],
                     'resolution': {'history_digest': 'a' * 64, 'reason': '已核对批准历史'}}
            with self.subTest(message=message), \
                    patch.object(coordination.platform_read, 'project_root', return_value=None), \
                    patch.object(coordination, 'load', return_value=state), \
                    patch.object(designs, 'approval_selection', return_value=None):
                self.assertTrue(coordination.draft_approval(url, value)['ok'])

    def test_closing_filters_gap_codes_with_arbitrary_message(self):
        for code in ('handoff-missing', 'progress-unconfirmed'):
            for message in ('任意说明甲', '完全不同的说明乙'):
                state = {'current': None, 'gaps': [message],
                         'gap_errors': [{'error_code': code, 'problem': message}],
                         'owners': ['bob'], 'roles': {'implementation_owner': 'bob'},
                         'task': {'risks': []}, 'progress': []}
                record = {'kind': 'close'}
                note = {'ok': True, 'gaps': [], 'record': record}
                with self.subTest(code=code, message=message), \
                        patch.object(coordination, 'resume', return_value=state), \
                        patch.object(coordination, 'draft', return_value=note):
                    self.assertEqual(coordination.closing(Path('/tmp/routing'), {}, 'task', (),
                                                         {'acceptance': {}}), (record, note))


class PlatformGapRouting(unittest.TestCase):
    base = test_markdown_records.MarkdownRecordCases
    setUp, git, check, prepare, body, github, publish_fixture, setup_record, make_design = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github, base.publish_fixture,
        base.setup_record, base.draft)
    handoff = test_coordination.CoordinationCases.handoff

    def prepared(self):
        self.setup_record()
        self.publish_fixture(self.make_design(), 'alice')
        self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol'}), 'carol')
        return coordination.load(self.url, root=self.root)

    def test_design_history_refusal_uses_code_with_arbitrary_message(self):
        self.setup_record()
        state = coordination.load(self.url, root=self.root)
        for message in ('任意说明甲', '完全不同的说明乙'):
            changed = {**state, 'gaps': [message],
                       'gap_errors': [{'error_code': 'platform-design-invalid', 'problem': message}]}
            with self.subTest(message=message), patch.object(coordination, 'load', return_value=changed):
                with self.assertRaises(coordination.DesignHistoryGap):
                    self.make_design()

    def test_handoff_conflict_and_requirements_use_codes_with_arbitrary_message(self):
        state = self.prepared()
        for code in ('platform-handoff-invalid', 'handoff-requirements-changed'):
            for message in ('任意说明甲', '完全不同的说明乙'):
                changed = {**state, 'gaps': [message], 'gap_errors': [{'error_code': code, 'problem': message}]}
                with self.subTest(code=code, message=message), patch.object(coordination, 'load', return_value=changed):
                    if code == 'platform-handoff-invalid':
                        with self.assertRaises(Invalid):
                            coordination.draft(self.root, self.profile, self.url, self.handoff(), kind='design')
                    else:
                        value = coordination.draft(self.root, self.profile, self.url, self.handoff(), kind='design')
                        self.assertTrue(value['ok'], value['gaps'])

    def test_start_filters_handoff_and_owner_codes_with_arbitrary_message(self):
        self.prepared()
        test_workflow.write_config(self.root, self.profile)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.main(['start', '--root', str(self.root), '--issue', self.url]), 0)
        for code in ('handoff-missing', 'owner-missing'):
            for message in ('任意说明甲', '完全不同的说明乙'):
                continuation = {'closed': False, 'gaps': [message],
                                'gap_errors': [{'error_code': code, 'problem': message}]}
                output = io.StringIO()
                with self.subTest(code=code, message=message), \
                        patch.object(coordination, 'resume', return_value=continuation), \
                        contextlib.redirect_stdout(output):
                    status = workflow.main(['start', '--root', str(self.root), '--issue', self.url])
                    result = json.loads(output.getvalue())
                    self.assertEqual(status, 0, result)
                    self.assertTrue(result['implementation_ready'], result)
                    self.assertEqual(result['gaps'], [])

    def test_platform_problem_sources_keep_codes_alongside_display_list(self):
        self.prepared()
        approval = coordination.draft_approval(self.url, {'reviewer': 'carol', 'section_ids': ['T1']})
        self.publish_fixture(approval, 'carol')
        self.publish_fixture(approval, 'carol')
        state = coordination.load(self.url, root=self.root)
        self.assertTrue(any(row['error_code'] == 'platform-approval-invalid' for row in state['design_errors']))
        self.assertEqual(state['gaps'], sorted({row['problem'] for row in state['gap_errors']}))
        resumed = coordination.resume(self.root, self.profile, self.url)
        self.assertTrue(any(row['error_code'] == 'handoff-missing' for row in resumed['gap_errors']))


if __name__ == '__main__':
    unittest.main()
