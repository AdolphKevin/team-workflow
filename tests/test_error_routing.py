"""E5：报错文字用于显示，修复命令由代码和字段决定。"""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workflow
from common import Invalid
import commands
import repairs
import workflow
import designs
import reviews
import artifacts
import contracts
from test_designs import example


class ErrorRouting(unittest.TestCase):
    def test_error_codes_choose_same_repair_for_arbitrary_messages(self):
        cases = [
            ('review', 'review-binding-stale', 'run', 'review'),
            ('review', 'review-file-unreadable', 'run', 'review'),
            ('review', 'review-run-incomplete', 'run', 'review'),
            ('accept', 'independence-required', 'review', '--submit'),
            ('run', 'validation-active', 'status', '--format text'),
            ('run', 'request-conflict', 'run', '--task task-1'),
            ('accept', 'approval-incomplete', 'review', 'approval-draft'),
            ('deliver', 'report-incomplete', 'deliver', '--reason'),
            ('run', 'tool-defect', 'project', '保留请求目录'),
        ]
        for command, code, first, second in cases:
            observed = []
            for message in ('甲方材料待补齐', '任意说明乙，内容完全不同'):
                with self.subTest(command=command, code=code, message=message):
                    exc = Invalid(message)
                    exc.error_code = code
                    output = io.StringIO()
                    with patch.object(commands, 'dispatch', side_effect=exc), contextlib.redirect_stdout(output):
                        status = workflow.main([command, '--root', '/tmp/routing', '--task', 'task-1'])
                    result = json.loads(output.getvalue())
                    observed.append(result['next_action'])
                    self.assertEqual(status, 1)
                    self.assertEqual(result['error_code'], code)
                    self.assertIn('tw team ' + first, result['next_action'])
                    self.assertIn(second, result['next_action'])
            self.assertEqual(observed[0], observed[1])

    def test_source_action_has_priority_over_command_default(self):
        for code in ('invalid-or-incomplete-input', 'review-incomplete', 'review-not-submitted',
                     'review-not-passed', 'tool-modified', 'import-incomplete',
                     'task-input-invalid', 'design-input-invalid', 'design-markdown-invalid',
                     'review-materials-incomplete', 'source-stale', 'run-binding-stale'):
            for message in ('approval report implementation owner', 'Request ID source 已过期'):
                with self.subTest(code=code, message=message):
                    exc = Invalid(message)
                    exc.error_code, exc.next_action = code, '按来源指引补齐材料'
                    output = io.StringIO()
                    with patch.object(commands, 'dispatch', side_effect=exc), contextlib.redirect_stdout(output):
                        status = workflow.main(['review', '--root', '/tmp/routing', '--task', 'task-1'])
                    result = json.loads(output.getvalue())
                    self.assertEqual(status, 1)
                    self.assertEqual(result['next_action'], '按来源指引补齐材料')

    def test_display_words_do_not_change_command_default(self):
        observed = []
        for message in ('approval report implementation owner', 'Request ID source 已过期'):
            args = workflow.parser().parse_args(['accept', '--root', '/tmp/routing', '--task', 'task-1'])
            result = repairs.annotate(args, {'ok': False, 'problem': message,
                                            'error_code': 'invalid-or-incomplete-input'})
            observed.append(result['next_action'])
        self.assertEqual(observed[0], observed[1])
        self.assertIn('tw team run', observed[0])
        self.assertIn('tw team review', observed[0])

    def test_cli_uses_command_default_when_source_has_no_next_action(self):
        output = io.StringIO()
        with patch.object(commands, 'dispatch', return_value={'ok': False, 'problem': '任意说明'}), \
                contextlib.redirect_stdout(output):
            code = workflow.main(['accept', '--root', '/tmp/routing', '--task', 'task-1'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertIn('tw team run', result['next_action'])
        self.assertIn('tw team review', result['next_action'])

    def test_review_error_keeps_section_and_line_with_arbitrary_reason(self):
        for reason in ('任意说明甲', '另一个说明乙'):
            with self.subTest(reason=reason):
                exc = reviews.ReviewError('规范 standards', 27, reason)
                self.assertEqual(getattr(exc, 'section', None), '规范 standards')
                self.assertEqual(getattr(exc, 'line', None), 27)

    def test_error_sources_supply_repair_codes(self):
        args = workflow.parser().parse_args(['accept', '--root', '/tmp/routing', '--task', 'task-1'])
        cases = [
            ('request-input-invalid', lambda: artifacts.directory(Path('/tmp/routing'), 'task-1', '!')),
            ('independence-required', lambda: contracts.independent(example(), 'bob', 'Reviewer')),
            ('approval-incomplete', lambda: designs.approval_draft(example(), 'carol', decision='unknown')),
            ('design-input-invalid', lambda: commands.report_input(args, Path('/tmp/routing'), {})),
        ]
        for code, operation in cases:
            with self.subTest(code=code), self.assertRaises(Invalid) as raised:
                operation()
            self.assertEqual(raised.exception.error_code, code)

    def test_design_line_uses_structured_key_with_arbitrary_reason(self):
        raw = designs.render(example())
        number = next(i for i, line in enumerate(raw.splitlines(), 1) if 'id=api-1 ' in line)
        for reason in ('任意说明甲', 'Role 任意说明乙 api-2'):
            exc = Invalid(reason, key='api-1')
            with self.subTest(reason=reason), patch.object(designs, 'validate_design', side_effect=exc):
                with self.assertRaises(Invalid) as raised:
                    designs.load(raw)
                self.assertEqual(getattr(raised.exception, 'line', None), number)

    def test_invalid_identifier_keeps_original_line_with_arbitrary_reason(self):
        raw = designs.render(example()).replace('api-1', '_api-1')
        number = next(i for i, line in enumerate(raw.splitlines(), 1) if 'id=_api-1 ' in line)
        for reason in ('任意说明甲', 'Role 任意说明乙 api-2'):
            with self.subTest(reason=reason), patch.object(Invalid, '__str__', return_value=reason):
                with self.assertRaises(Invalid) as raised:
                    designs.load(raw)
                self.assertEqual(getattr(raised.exception, 'line', None), number)


class StructuredDelivery(unittest.TestCase):
    base = __import__('test_four_command_delivery').FourCommandDelivery
    setUp, git, check, configure, command, start = (
        base.setUp, base.git, base.check, base.configure, base.command, base.start)
    run_checks, current_path, current, draft_path, submit, reviewed, field, completed = (
        base.run_checks, base.current_path, base.current, base.draft_path, base.submit,
        base.reviewed, base.field, base.completed)

    def test_internal_tool_defect_repair_is_applied_once(self):
        self.start()
        for index, message in enumerate(('任意说明甲', '完全不同的说明乙')):
            output = io.StringIO()
            with self.subTest(message=message), patch.object(commands, 'produce', side_effect=RuntimeError(message)), \
                    contextlib.redirect_stdout(output):
                code = workflow.main(['run', '--root', str(self.root), '--task', self.task['id'],
                                      '--request-id', 'internal-defect-' + str(index)])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['error_code'], 'tool-defect')
            self.assertEqual(result['next_action'].count('tw team project'), 1)
            saved = json.loads((self.root / result['request_directory'] / 'response.json').read_text())
            self.assertEqual(saved['next_action'], result['next_action'])

    def test_material_and_close_repairs_use_fields_with_arbitrary_messages(self):
        self.start()
        group = self.current()
        for code in ('current-materials-incomplete', 'close-authorization-incomplete'):
            observed = []
            for message in ('任意说明甲', '任意说明乙'):
                args = workflow.parser().parse_args(['verify', '--root', str(self.root), '--task', self.task['id'],
                                                      '--report', '.tw/local/report.json'])
                args.material_selection = {'task_id': self.task['id'], 'effective': group}
                value = repairs.annotate(args, {'ok': False, 'error_code': code, 'problem': message})
                observed.append(value['next_action'])
            self.assertEqual(observed[0], observed[1])
            if code == 'current-materials-incomplete':
                self.assertIn('tw team start --task', observed[0])
                self.assertIn('--design', observed[0])
            else:
                self.assertIn('cp -n', observed[0])
                self.assertIn('tw team verify', observed[0])

    def test_review_format_errors_keep_section_when_reason_changes(self):
        import delivery
        self.reviewed()
        task = self.task
        group = self.current()
        review = json.loads((self.root / group['review']['path']).read_text())
        for label, section in [('standards', '规范 standards'), ('spec', '需求 spec')]:
            for message in ('任意说明甲', '任意说明乙'):
                changed = json.loads(json.dumps(review))
                changed[label]['status'] = 'pending'
                with self.subTest(label=label, message=message), patch.object(Invalid, '__str__', return_value=message):
                    with self.assertRaises(Invalid) as raised:
                        delivery.check_review_format(self.root, self.profile, task, changed, review['sections'], self.design)
                    self.assertEqual(getattr(raised.exception, 'section', None), section)

    def test_stale_source_and_runs_emit_codes_at_real_sources(self):
        import delivery
        import validation
        self.reviewed()
        group = self.current()
        review = json.loads((self.root / group['review']['path']).read_text())
        (self.root / 'app.py').write_text('def add(a, b):\n    return sum((a, b))\n')
        operations = [
            ('source-stale', lambda: delivery.check_review_format(
                self.root, self.profile, self.task, review, review['sections'], self.design)),
            ('run-binding-stale', lambda: validation.verify_runs(
                self.root, self.profile, self.task, [row['path'] for row in group['runs']], live=False)),
        ]
        for code, operation in operations:
            with self.subTest(code=code):
                with self.assertRaises(Invalid) as raised:
                    operation()
                self.assertEqual(raised.exception.error_code, code)

    def test_acceptance_stop_uses_error_code_for_source_and_run_binding(self):
        import artifacts
        import delivery_sequence
        self.start()
        for code, expected in [('source-stale', 'run'), ('run-binding-stale', 'run'),
                               ('invalid-or-incomplete-input', 'review')]:
            for index, message in enumerate(('任意说明甲', 'source 源码 任意说明乙')):
                args = workflow.parser().parse_args(['deliver', '--root', str(self.root), '--task', self.task['id']])
                request = artifacts.Request(self.root, self.task['id'], {}, code + str(index))
                with self.subTest(code=code, message=message), patch.object(commands, 'dispatch', return_value={
                        'ok': False, 'error_code': code, 'problem': message}):
                    result = delivery_sequence.deliver(args, self.root, self.profile, self.task, request)
                self.assertEqual(result['stopped_at'], 'acceptance')
                self.assertEqual(result['next_action'], 'tw team ' + expected + ' --task ' + self.task['id']
                                 + (' --submit' if expected == 'review' else ''))


if __name__ == '__main__':
    unittest.main()
