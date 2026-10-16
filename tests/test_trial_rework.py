"""独立试用 T1–T8 的真实命令回归，复用试用的本地平台脚本。"""
import json
import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_platform_review
from tw_fixtures import Case
from common import Invalid, read, write
import commands
from tw_runtime.team import platform_script


class PlatformTrial(unittest.TestCase):
    base = test_platform_review.PlatformReview
    setUp, git, check, current_path, current, draft_path, run_checks, field, completed, command, prepare = (
        base.setUp, base.git, base.check, base.current_path, base.current, base.draft_path,
        base.run_checks, base.field, base.completed, base.command, base.prepare)

    def configure(self, complexity='simple'):
        self.profile['platform']['argv'] = [sys.executable,
            str(Path(__file__).with_name('trial_platform.py'))]
        self.base.configure(self, complexity)

    def response(self):
        path = self.root / '.tw/local/platform.json'
        write(path, {'tasks': {self.url: self.platform}})
        os.environ['FAKE_PLATFORM_FILE'] = str(path)
        platform_script.clear_cache()

    def post(self, body, kind='review', author='reviewer-account'):
        item = self.base.post(self, body, kind, author)
        if kind == 'review' and '<!-- tw-review:binding:start -->' in body:
            item['updated_at'] = '2099-01-01T00:00:00Z'
            self.response()
        return item

    def approved_local(self):
        source = self.prepare('simple')
        source = self.field(source, '## 评审信息', '批准方案与代码', '是')
        source = self.field(source, '## 评审信息', '批准说明', '已核对当前方案、代码和原始结果。')
        self.draft_path().write_text(source)
        code, submitted = self.command('review', '--task', self.url, '--submit')
        self.assertEqual(code, 0, submitted)
        return source, submitted

    def test_t1_replacing_review_replaces_only_its_combined_approval(self):
        source, submitted = self.approved_local()
        plan = [ref for ref in self.current()['approvals'] if ref != submitted['approval']]
        latest = self.field(source, '## 需求 spec', '理由', '第二轮独立核对了当前行为。')
        latest = self.field(latest, '## 评审信息', '批准说明', '第二轮重新确认方案与代码。')
        self.post(latest)
        code, result = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'])
        current = self.current()
        self.assertNotIn(submitted['approval'], current['approvals'])
        self.assertEqual(len(current['approvals']), len(plan) + 1)
        self.assertTrue(all(ref in current['approvals'] for ref in plan))
        imported = result['steps'][0]['result']
        self.assertIn(imported['approval'], current['approvals'])

    def test_t2_unshared_approval_points_to_publishing_the_review(self):
        self.approved_local()
        code, result = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, result)
        failed = result['steps'][-1]['result']
        self.assertEqual(failed['error_code'], 'approval-not-shared')
        self.assertIn(self.draft_path().relative_to(self.root).as_posix(), result['next_action'])
        self.assertIn('变更请求评审', result['next_action'])
        self.assertIn('tw team deliver', result['next_action'])
        self.assertNotIn('approval-draft', result['next_action'])

    def test_t1_replacement_without_approval_retires_previous_combined_approval(self):
        source, submitted = self.approved_local()
        plan = [ref for ref in self.current()['approvals'] if ref != submitted['approval']]
        self.draft_path().write_text(self.field(source, '## 评审信息', '批准方案与代码', '否'))
        code, result = self.command('review', '--task', self.url, '--submit')
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['approvals'], plan)

    def test_t3_older_platform_draft_uses_binding_recovery(self):
        source = self.prepare()
        self.run_checks()
        self.post(source)
        code, result = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['stopped_at'], 'review')
        self.assertEqual(result['steps'][0]['result']['error_code'], 'review-binding-stale')
        self.assertIn('tw team review', result['next_action'])
        self.assertIn('变更请求评审', result['next_action'])
        self.assertIn(self.draft_path().relative_to(self.root).as_posix(), result['next_action'])

    def test_t4_absent_platform_review_points_to_actual_draft_and_publication(self):
        self.prepare()
        code, result = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['stopped_at'], 'review')
        self.assertEqual(result['steps'][0]['result']['error_code'], 'review-not-submitted')
        self.assertIn(self.draft_path().relative_to(self.root).as_posix(), result['next_action'])
        self.assertIn('变更请求评审', result['next_action'])
        self.assertIn('tw team deliver', result['next_action'])

    def test_t6_platform_command_reports_its_failed_operation(self):
        self.prepare()
        self.platform['items'] = []
        self.response()
        code, result = self.command('platform', '--check', '--id', self.url)
        self.assertEqual(code, 1, result)
        for check in result['checks']:
            if not check['ok']:
                self.assertIn(check['problem'], result['problem'])

    def test_t8_stale_platform_review_problem_contains_only_the_problem(self):
        source = self.prepare()
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        self.post(source)
        code, result = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, result)
        self.assertNotIn('tw team', result['problem'])
        self.assertNotIn('<身份>', result['problem'])
        self.assertIn('tw team review', result['next_action'])

    def test_t8_material_gap_keeps_commands_in_next_action(self):
        self.prepare()
        current = self.current()
        current['runs'] = '错误类型'
        write(self.current_path(), current)
        code, result = self.command('status', '--task', self.url)
        self.assertEqual(code, 1, result)
        self.assertNotIn('tw team', result['problem'])
        self.assertIn('tw team start', result['next_action'])

    def test_t8_missing_acceptance_keeps_accept_command_in_next_action(self):
        source = self.prepare()
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        code, report = self.command('delivery-template', '--task', self.url)
        self.assertEqual(code, 0, report)
        code, result = self.command('verify', '--task', self.url, '--report', report['artifact']['path'])
        self.assertEqual(code, 1, result)
        self.assertNotIn('tw team', result['problem'])
        self.assertIn('tw team accept', result['next_action'])


class OutputTrial(Case):
    def test_t5_project_initialization_has_its_own_recovery(self):
        for command in ('status', 'project'):
            with self.subTest(command=command):
                code, result = self.tw_json('team', command, *(['--task', 'nope'] if command == 'status' else []))
                self.assertEqual(code, 1)
                self.assertEqual(result.get('error_code'), 'project-not-initialized')
                self.assertIn('tw init', result['next_action'])
                self.assertIn('--apply', result['next_action'])
                self.assertNotIn('tw team start', result['next_action'])

    def test_t6_project_text_reports_its_configuration_and_knowledge_errors(self):
        self.initialize()
        config = read(self.root / '.tw/config.json')
        config['checks'] = {'unit': {}}
        write(self.root / '.tw/config.json', config)
        (self.root / '.tw/overview.md').write_text('# 订单服务\n')
        code, result = self.tw_json('team', 'project')
        self.assertEqual(code, 1)
        code, output, _ = self.tw('team', 'project', '--format', 'text')
        self.assertEqual(code, 1)
        expected = result['config']['errors'] + [row['message'] for row in result['knowledge']['check']['errors']]
        self.assertTrue(expected)
        for problem in expected:
            with self.subTest(problem=problem):
                self.assertIn(problem, output)
        self.assertNotIn('The operation is incomplete.', output)

    def test_t7_internal_recovery_data_stays_out_of_error_json(self):
        with patch.object(commands, 'dispatch', side_effect=Invalid('材料缺少来源', next_action='补齐明确来源')):
            code, result = self.tw_json('team', 'status', '--task', 'nope')
        self.assertEqual(code, 1)
        self.assertEqual(set(result), {'ok', 'status', 'problem', 'error_code', 'next_action', 'scope'})
        self.assertEqual(result['next_action'], '补齐明确来源')
        retained = {'ok': False, 'error_code': 'tool-defect', 'problem': '工具缺陷',
                    'source_next_action': '保留材料', 'next_action': '保留材料',
                    'steps': [{'result': {'ok': False, 'source_next_action': '补齐来源', 'problem': '缺少来源'}}]}
        with patch.object(commands, 'dispatch', return_value=retained):
            code, result = self.tw_json('team', 'status', '--task', 'nope')
        self.assertEqual(code, 1)
        self.assertNotIn('source_next_action', result)
        self.assertNotIn('source_next_action', result['steps'][0]['result'])
        self.assertEqual(retained['source_next_action'], '保留材料')

    def test_t8_project_problem_keeps_initialization_commands_in_next_action(self):
        code, result = self.tw_json('team', 'project')
        self.assertEqual(code, 1)
        self.assertNotIn('tw init', result['problem'])
        self.assertIn('tw init', result['next_action'])

    def test_t7_existing_project_configuration_errors_keep_their_public_fields(self):
        self.initialize()
        config = read(self.root / '.tw/config.json')
        config['checks'] = {'unit': {}}
        write(self.root / '.tw/config.json', config)
        code, result = self.tw_json('team', 'project')
        self.assertEqual(code, 1)
        self.assertNotIn('error_code', result)
        self.assertNotIn('source_next_action', result)
        self.assertTrue(result['config']['errors'])



if __name__ == '__main__':
    unittest.main()
