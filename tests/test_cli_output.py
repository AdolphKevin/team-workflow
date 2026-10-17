"""E4：两个命令入口按所选格式输出成功、输入错误和工具缺陷。"""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import test_workflow
from common import Invalid
from tw_fixtures import Case
from tw_runtime import cli, init
import commands


class CLIOutput(Case):
    def test_summary_joins_expectation_and_case_with_one_separator(self):
        import summary
        value = summary.render({'named_cases': {'A1': ['CalcTests::test_add']}},
            {'id': 'T', 'acceptance': [{'id': 'A1', 'expectation': '结果正确。'}]})
        self.assertIn('A1：结果正确；用例 CalcTests::test_add', value)
        self.assertNotIn('。；', value)

    def test_team_results_use_selected_format(self):
        cases = [
            ('success', {'ok': True, 'summary': '检查完成',
                         'checks': [{'id': 'unit', 'status': 'passed'}]}, 0),
            ('input', Invalid('任务材料缺少来源'), 1),
            ('defect', RuntimeError('工具执行中断'), 1),
        ]
        for kind, value, expected_code in cases:
            for fmt in ('text', 'json'):
                with self.subTest(kind=kind, fmt=fmt):
                    options = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
                    with patch.object(commands, 'dispatch', **options):
                        code, out, err = self.tw('team', 'status', '--task', 'nope', '--format', fmt)
                    self.assertEqual(code, expected_code)
                    self.assertEqual(err, '')
                    if fmt == 'json':
                        result = json.loads(out)
                        self.assertEqual(result['ok'], kind == 'success')
                        if kind == 'input':
                            self.assertEqual(set(result), {'ok', 'scope', 'status', 'problem', 'error_code', 'next_action'})
                            self.assertEqual(result['error_code'], 'invalid-or-incomplete-input')
                            self.assertEqual(result['problem'], '任务材料缺少来源')
                        if kind == 'defect':
                            self.assertEqual(set(result), {'ok', 'scope', 'status', 'problem', 'error_code', 'next_action', 'traceback'})
                            self.assertEqual(result['error_code'], 'tool-defect')
                            self.assertTrue(result['traceback'])
                    else:
                        self.assertNotIn('{', out)
                        self.assertNotIn('"ok"', out)
                        if kind == 'success':
                            self.assertIn('unit', out)
                            self.assertIn('passed', out)
                        else:
                            self.assertIn(str(value), out)
                            self.assertIn('下一步', out)
                        if kind == 'defect':
                            self.assertIn('调用位置：', out)

    def test_knowledge_results_use_selected_format(self):
        for kind in ('success', 'input', 'defect'):
            for fmt in ('text', 'json'):
                with self.subTest(kind=kind, fmt=fmt):
                    args = ('read', 'missing.md') if kind == 'input' else ('init',)
                    with contextlib.ExitStack() as stack:
                        if kind == 'defect':
                            stack.enter_context(patch.object(init, 'run', side_effect=RuntimeError('工具执行中断')))
                        code, out, err = self.tw(*args, '--format', fmt)
                    self.assertEqual(code, {'success': 0, 'input': 2, 'defect': 1}[kind])
                    if fmt == 'json':
                        self.assertEqual(err, '')
                        result = json.loads(out)
                        if kind != 'success':
                            self.assertEqual(set(result), {'ok', 'problem'})
                            self.assertIs(result['ok'], False)
                            self.assertTrue(result['problem'])
                    elif kind == 'success':
                        self.assertTrue(out)
                        self.assertEqual(err, '')
                        self.assertNotIn('"actions"', out)
                    else:
                        self.assertEqual(out, '')
                        self.assertTrue(err.startswith('tw: '), err)

    def test_text_tool_defect_includes_retained_request_directory(self):
        value = {'ok': False, 'error_code': 'tool-defect', 'problem': '工具执行中断',
                 'request_directory': '.tw/local/tasks/sample/requests/failed',
                 'traceback': ['commands.py:1 dispatch'], 'next_action': '检查安装'}
        with patch.object(commands, 'dispatch', return_value=value):
            code, out, err = self.tw('team', 'status', '--task', 'nope', '--format', 'text')
        self.assertEqual((code, err), (1, ''))
        self.assertIn('请求目录：.tw/local/tasks/sample/requests/failed', out)

    def test_text_preserves_all_existing_check_shapes(self):
        cases = [(['unit'], ['unit']),
                 ([{'operation': 'task-read', 'ok': True}], ['task-read', 'True']),
                 ({'unit': {'runs': 2, 'seconds': 0.5}}, ['unit', '2', '0.5']),
                 ([{'id': 'unit', 'status': 'failed', 'detail': '断言失败'}], ['unit', 'failed', '断言失败'])]
        for checks, expected in cases:
            with self.subTest(checks=checks), patch.object(commands, 'dispatch', return_value={
                    'ok': True, 'summary': '核对完成', 'checks': checks}):
                code, out, err = self.tw('team', 'status', '--task', 'nope', '--format', 'text')
                self.assertEqual((code, err), (0, ''))
                self.assertNotIn('{', out)
                for value in expected:
                    self.assertIn(value, out)


if __name__ == '__main__':
    unittest.main()
