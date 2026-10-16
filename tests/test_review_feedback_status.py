"""C2: record human decisions, retain acceptance gates, report verified current facts."""
import plan_fixtures as plans
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_four_command_delivery as four
import test_current_materials as recorded
import test_workflow as fixtures
import test_close_note as close_note
from common import artifact_valid, read, write
import coordination
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import issue_history
import workflow


class ReviewFeedbackStatus(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, rule, field, completed, command, configure, start, run_checks = (
        base.setUp, base.git, base.check, base.rule, base.field, base.completed, base.command,
        base.configure, base.start, base.run_checks)
    current_path, current, draft_path, submit, reviewed, accepted = (
        base.current_path, base.current, base.draft_path, base.submit, base.reviewed, base.accepted)

    def opinion(self, negative=True, issue=True):
        self.start()
        self.run_checks()
        source = self.completed(self.draft_path().read_text())
        source = self.field(source, '## 评审信息', '批准方案与代码', '是')
        if negative:
            for section, reason in [('## 规范 standards', '错误输入没有明确提示'),
                                    ('## 需求 spec', '重复输入的业务要求没有满足'),
                                    ('## 验收 A1', '观察到重复输入数量错误')]:
                source = self.field(source, section, '结论', '不通过')
                source = self.field(source, section, '理由', reason)
        if issue:
            source = source.replace('## 风险', '### 问题 I-count\n- 编号：I-count\n- 负责人：bob\n'
                '- 影响范围：A1\n- 阻塞阶段：acceptance\n- 状态：open\n- 摘要：重复输入数量丢失\n\n## 风险')
        self.draft_path().write_text(source)
        return self.command('review', '--task', self.task['id'], '--submit')

    def test_negative_review_is_submitted_and_its_issues_become_current_history(self):
        code, result = self.opinion()
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['review'], result['artifact'])
        review = read(artifact_valid(self.root, result['artifact']))
        self.assertEqual(review['acceptance'][0]['status'], 'failed')
        self.assertEqual(review['standards']['summary'], '错误输入没有明确提示')
        self.assertEqual([row['id'] for row in issue_history.known(self.root, self.task['id'])], ['I-count'])

    def test_open_acceptance_issue_does_not_prevent_a_complete_review_submission(self):
        code, result = self.opinion(negative=False)
        self.assertEqual(code, 0, result)
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('I-count', refused['problem'])
        self.assertIn('重复输入数量丢失', refused['problem'])

    def test_accept_and_deliver_list_every_failed_axis_acceptance_and_blocker(self):
        code, submitted = self.opinion()
        self.assertEqual(code, 0, submitted)
        for command in ('accept', 'deliver'):
            with self.subTest(command=command):
                code, refused = self.command(command, '--task', self.task['id'])
                self.assertEqual(code, 1, refused)
                for text in ('standards', 'spec', 'A1', 'I-count', '错误输入没有明确提示',
                             '重复输入的业务要求没有满足', '观察到重复输入数量错误', '重复输入数量丢失'):
                    self.assertIn(text, refused['problem'])
                self.assertIn('tw team run', refused['next_action'])
                self.assertIn('tw team review', refused['next_action'])
                if command == 'deliver':
                    self.assertEqual(refused['stopped_at'], 'acceptance')
        self.assertIsNone(self.current()['acceptance'])
        self.assertIsNone(self.current()['delivery'])

    def test_implementer_can_record_opinion_but_cannot_pass_acceptance(self):
        self.start('medium')
        self.run_checks()
        code, submitted = self.submit(reviewer='bob')
        self.assertEqual(code, 0, submitted)
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('implementation owner', refused['problem'])

    def test_implementer_opinion_does_not_create_an_independent_combined_approval(self):
        self.start()
        self.run_checks()
        for reviewer in ('bob', '  BOB  '):
            with self.subTest(reviewer=reviewer):
                code, submitted = self.submit(reviewer=reviewer)
                self.assertEqual(code, 0, submitted)
                self.assertNotIn('approval', submitted)
                self.assertEqual(self.current()['approvals'], [])
                code, refused = self.command('accept', '--task', self.task['id'])
                self.assertEqual(code, 1, refused)
                self.assertIn('implementation owner', refused['problem'])

    def test_failed_execution_can_be_described_and_submitted_but_cannot_be_accepted(self):
        self.start('medium', passed=False)
        plans.submit_scenarios(self.root, self.task)
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1, ran)
        code, draft = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, draft)
        source = self.completed(self.draft_path().read_text())
        source = self.field(source, '## 验收 A1', '结论', '不通过')
        self.draft_path().write_text(source)
        code, submitted = self.command('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, submitted)
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('A1', refused['problem'])

    def test_submission_points_to_deliver_and_names_the_knowledge_branch(self):
        result = self.reviewed()
        self.assertIn('tw team deliver --task ' + self.task['id'], result['next_action'])
        self.assertIn('--reason', result['next_action'])
        self.assertIn('tw team accept --task ' + self.task['id'], result['knowledge_next_action'])

    def test_deliver_without_a_submitted_review_names_draft_and_submit_command(self):
        self.start()
        self.run_checks()
        code, refused = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['stopped_at'], 'acceptance')
        self.assertIn('尚未提交评审', refused['problem'])
        self.assertNotIn('accept needs --review', refused['problem'])
        self.assertEqual(refused['review_file'], str(self.draft_path().relative_to(self.root)))
        self.assertIn('tw team review --task ' + self.task['id'] + ' --submit', refused['next_action'])

    def test_status_after_failed_acceptance_points_to_the_repair_not_the_failed_step(self):
        code, submitted = self.opinion()
        self.assertEqual(code, 0, submitted)
        code, refused = self.command('deliver', '--task', self.task['id'], '--reason', '没有可复用的知识')
        self.assertEqual(code, 1, refused)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        step = status['next_step']
        self.assertEqual((step['id'], step['state']), ('acceptance', 'failed'))
        self.assertIn('tw team run', step['next_command'])
        self.assertIn('tw team review', step['next_command'])
        self.assertNotIn('tw team deliver', step['next_command'])

    def test_local_status_states_that_publication_does_not_apply(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', '没有可复用的知识')
        self.assertEqual(code, 0, delivered)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(status['publication']['kind'], 'local')
        self.assertIn('发布状态：本地任务没有平台收尾说明或交接', status['publication']['summary'])

    def test_status_only_lists_verified_current_records_and_deliver_commands(self):
        self.reviewed()
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        for key in ('business_accepted', 'delivery_complete', 'closable', 'regression_pending', 'delivery'):
            self.assertNotIn(key, status)
        self.assertEqual(status['verified_records'], {})
        by_id = {row['id']: row for row in status['steps']}
        # 保留原来的三个交付步骤断言；场景展示插入后按步骤身份核对。
        for key in ('acceptance', 'knowledge', 'delivery'):
            self.assertIn('tw team deliver', by_id[key]['next_command'])
        self.assertEqual(by_id['scenarios']['state'], 'done')
        self.assertNotIn('next_command', by_id['scenarios'])
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(status['verified_records'], {'acceptance': accepted['artifact']})

    def test_delivered_status_reports_paths_and_authorization_boundary(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, delivered)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['summary'], '任务已交付')
        self.assertEqual(status['task_phase'], 'delivered')
        self.assertIn('关闭授权', status['next_action'])
        self.assertEqual(status['verified_records'], {key: self.current()[key] for key in ('acceptance', 'delivery')})
        self.assertIsNone(status['next_step'])

    def test_start_after_delivery_continues_using_current_verified_materials(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, delivered)
        before = self.current_path().read_bytes()
        context = self.current()['context']
        code, continued = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, continued)
        self.assertTrue(continued['continued'])
        self.assertEqual(continued['context'], context)
        self.assertIsNone(continued['next_step'])
        self.assertEqual(continued['verified_records'], {key: self.current()[key] for key in ('acceptance', 'delivery')})
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_text_status_includes_the_verified_record_paths(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, delivered)
        result = subprocess.run([sys.executable, str(four.TW), '--root', str(self.root), 'team',
                                 'status', '--task', self.task['id'], '--format', 'text'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        for role in ('acceptance', 'delivery'):
            self.assertIn(self.current()[role]['path'], result.stdout)

    def test_source_change_expires_accepted_and_delivered_records(self):
        self.reviewed()
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, result)
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'delivered')
        self.assertTrue(status['verified_records']['delivery'])
        code, reopened = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, reopened)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'in-progress')
        self.assertEqual(status['verified_records'], {})
        states = {row['id']: row['state'] for row in status['steps']}
        for name in ('run', 'review', 'acceptance', 'knowledge', 'delivery'):
            self.assertEqual(states[name], 'stale', (name, status))

    def test_check_configuration_change_expires_all_dependent_steps(self):
        self.reviewed()
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, result)
        self.profile['checks']['unit']['argv'][-1] += "; print('new validation policy')"
        fixtures.write_config(self.root, self.profile)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'delivered')
        self.assertTrue(status['verified_records']['delivery'])
        code, reopened = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, reopened)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'in-progress')
        self.assertEqual(status['verified_records'], {})
        by_id = {row['id']: row for row in status['steps']}
        for key in ('run', 'review', 'acceptance', 'knowledge', 'delivery'):
            self.assertEqual(by_id[key]['state'], 'stale', by_id[key])
        # 检查策略变化不改变已独立核对的产品与场景内容。
        self.assertEqual(by_id['scenarios']['summary_counts']['pending'], 0)
        self.assertEqual(by_id['scenarios']['summary_counts']['passed'], 2)

    def test_explicit_new_design_expires_material_dependent_steps(self):
        self.reviewed()
        revised = copy.deepcopy(self.design)
        revised['sections'][-1]['body'] = 'Changed implementation requirement'
        plans.write_design(self.root / '.tw/local/revised.md', revised)
        before = self.current_path().read_bytes()
        code, status = self.command('status', '--task', self.task['id'], '--design', '.tw/local/revised.md')
        self.assertEqual(code, 0, status)
        self.assertEqual(status['verified_records'], {})
        for name in ('prepare', 'review'):
            self.assertEqual(next(row for row in status['steps'] if row['id'] == name)['state'], 'stale')
        self.assertEqual(self.current_path().read_bytes(), before, 'Status must not silently adopt an unprepared plan')

    def test_rejection_messages_for_all_workflow_commands_include_a_repair_command(self):
        for command in ('start', 'run', 'review', 'accept', 'deliver', 'verify', 'status'):
            with self.subTest(command=command):
                code, refused = self.command(command)
                self.assertEqual(code, 1, refused)
                self.assertIn('tw team ', refused['next_action'])

    def test_material_gap_repair_uses_the_recorded_task_and_plan_paths(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 0, delivered)
        group = self.current()
        artifact_valid(self.root, group['delivery']).unlink()
        code, refused = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('tw team start', refused['next_action'])
        self.assertIn(group['task']['path'], refused['next_action'])
        self.assertIn(group['design']['path'], refused['next_action'])

    def test_failed_run_gives_a_copyable_check_command(self):
        self.start(passed=False)
        code, refused = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('tw team run --task ' + self.task['id'], refused['next_action'])
        self.assertIn('--check unit', refused['next_action'])

    def test_stale_review_gives_generation_command_before_submission(self):
        self.reviewed('medium')
        old = self.draft_path().read_text()
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        self.draft_path().write_text(old)
        code, refused = self.command('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 1, refused)
        self.assertIn('tw team review --task ' + self.task['id'], refused['next_action'])
        self.assertNotIn('--submit', refused['next_action'])

    def test_deliver_after_source_change_gives_run_and_recheck_commands(self):
        self.accepted()
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        code, refused = self.command('deliver', '--task', self.task['id'], '--reason', 'No new knowledge.')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['stopped_at'], 'acceptance')
        self.assertIn('tw team run --task ' + self.task['id'], refused['next_action'])
        self.assertIn('tw team review --task ' + self.task['id'], refused['next_action'])


class PlatformStatus(unittest.TestCase):
    base = recorded.PlatformCurrentMaterials
    setUp, git, check, prepare, body, github, publish_fixture, establish_design, handoff, prepared_platform = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github, base.publish_fixture,
        base.establish_design, base.handoff, base.prepared_platform)
    command, identity_command = base.command, base.identity_command

    def test_platform_newer_plan_is_displayed_as_stale_without_adopting_it(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][-1]['body'] = 'New shared requirement'
            self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
            code, status = self.identity_command('status')
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'prepare')['state'], 'stale')
        self.assertIn('start', status['next_action'])
        self.assertEqual(status['verified_records'], {})

    def test_platform_newer_approval_is_displayed_as_stale(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            self.publish_fixture(coordination.draft_approval(self.url,
                {'reviewer': 'carol', 'confirmation': 'New explicit approval', 'section_ids': 'all'}), 'carol')
            code, status = self.identity_command('status')
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'prepare')['state'], 'stale')
        self.assertIn('批准', json.dumps(status, ensure_ascii=False))
        import materials
        group = materials.load(self.root, self.url)
        artifact_valid(self.root, group['brief']).unlink()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, refused = self.identity_command('status')
        self.assertEqual(code, 1, refused)
        self.assertIn('--task ' + self.url, refused['next_action'])
        self.assertNotIn('--task ' + group['task']['path'], refused['next_action'])

    def test_status_reads_publication_from_platform_records(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url,
                self.handoff(creator='bob'), kind='implementation'), 'bob')
            code, status = self.identity_command('status')
        self.assertEqual(code, 0, status)
        self.assertTrue(status['publication']['published'])
        self.assertEqual(status['publication']['kind'], 'implementation')
        self.assertIn('#issuecomment-', status['publication']['url'])
        self.assertTrue(all('/issues/' in p or '/commits/' in p for p in self.gets))


class WorkflowDocumentation(unittest.TestCase):
    def test_user_documentation_has_only_current_command_names(self):
        root = Path(__file__).resolve().parents[1]
        files = [root / 'README.md']
        files += [path for path in (root / 'docs').rglob('*.md')
                  if path.name != 'validation.md' and not {'proposals', 'sop'} & set(path.relative_to(root).parts)]
        files += list((root / 'skills').rglob('*.md'))
        forbidden = re.compile(r'\b(?:prepare|resume|review-template)\b|verify\s+--phase')
        hits = [(str(path.relative_to(root)), n, line) for path in files
                for n, line in enumerate(path.read_text().splitlines(), 1) if forbidden.search(line)]
        self.assertEqual(hits, [])
        self.assertLessEqual(len((root / 'skills/team-workflow/SKILL.md').read_text()), 2500)

    def test_closing_instructions_require_completion_publication_and_named_authorization(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / 'skills/team-workflow/references/team-delivery.md').read_text()
        for required in ('close_authorization', 'confirmed_by', 'reference', '已发布', '(contracts.md#工具做什么)'):
            self.assertIn(required, text)
        contracts = (root / 'skills/team-workflow/references/contracts.md').read_text()
        self.assertIn('关闭任务', contracts)
        self.assertIn('由成员按自己的授权执行；平台只读', contracts)


class ClosingRules(unittest.TestCase):
    helper = close_note.CloseNote
    base = helper.base
    setUp, git, check, setup_task, write, name, github, publish, accept_and_record_knowledge = (
        helper.setUp, helper.git, helper.check, helper.setup_task, helper.write, helper.name, helper.github,
        helper.publish, helper.accept_and_record_knowledge)

    def test_authorized_close_note_must_be_published_before_closable(self):
        import delivery
        self.accept_and_record_knowledge()
        self.report['close_authorization'] = {'confirmed_by': 'carol', 'reference': 'Explicit authorization in this session'}
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])
        count = len(self.issue['comments_data'])
        self.publish(result['close_note'], 'bob')
        verified = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(verified['closable'])
        self.assertEqual(len(self.issue['comments_data']), count + 1)
        self.assertEqual(self.issue['state'], 'open')

    def test_authorized_unpublished_close_note_summary_names_publication_gap(self):
        import delivery
        self.accept_and_record_knowledge()
        self.report['close_authorization'] = {'confirmed_by': 'carol', 'reference': 'Explicit authorization in this session'}
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertFalse(result['closable'])
        self.assertIn('尚未发布', result['summary_markdown'])
        self.assertNotIn('还需要明确的关闭授权', result['summary_markdown'])

    def test_incomplete_close_authorization_names_the_report_repair_command(self):
        import delivery
        from common import Invalid
        self.accept_and_record_knowledge()
        self.report['close_authorization'] = {'confirmed_by': 'carol'}
        with self.assertRaisesRegex(Invalid, 'close_authorization') as caught:
            delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertIn('tw team verify', caught.exception.next_action)
        self.assertIn('--report', caught.exception.next_action)
        self.write('report-missing-authorization', self.report)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['verify', '--root', str(self.root), '--task', self.name('task'),
                                  '--report', self.name('report-missing-authorization')])
        refused = json.loads(output.getvalue())
        self.assertEqual(code, 1, refused)
        self.assertIn(self.name('report-missing-authorization'), refused['next_action'])
        self.assertIn('cp -n ', refused['next_action'])
        self.assertNotIn('<修正后的报告路径>', refused['next_action'])


if __name__ == '__main__':
    unittest.main()
