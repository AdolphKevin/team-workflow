"""CLI diagnostics and recovery suggested by the documentation-only trial."""
import copy
import hashlib
import json
from pathlib import Path
import shlex
import unittest

import test_four_command_delivery as four
from common import Invalid, read, write
import design_files
import designs
import contracts
import commands
import test_workflow as fixtures
import test_markdown_review as markdown
import test_reconciliation as published
import plan_fixtures as plans


class TrialFeedback(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, command = base.setUp, base.git, base.check, base.configure, base.command

    def legacy_design(self):
        self.configure('medium')
        raw = designs.render(self.design).replace('- 验证：自动', '- 验证：自动；层级 journey', 1)
        path = self.root / 'docs/design.md'
        path.parent.mkdir()
        path.write_text(raw)
        line = next(i for i, value in enumerate(raw.splitlines(), 1) if '层级 journey' in value)
        return path, raw, line

    def test_r1_parse_error_names_file_line_and_acceptance(self):
        path, _, line = self.legacy_design()
        with self.assertRaises(Invalid) as caught:
            design_files.read(path)
        self.assertIn(f'docs/design.md 第 {line} 行：验收 A1 的验证行：请改为', str(caught.exception))

    def test_r1_published_parse_error_names_path_and_revision(self):
        path, raw, line = self.legacy_design()
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.git('add', 'docs/design.md')
        self.git('commit', '-qm', 'Published invalid design fixture')
        reference = {'id': self.design['id'], 'revision': 1, 'repository': 'github.com/example/project',
                     'path': 'docs/design.md', 'commit': self.git('rev-parse', 'HEAD').strip(),
                     'sha256': hashlib.sha256(raw.encode()).hexdigest()}
        with self.assertRaises(Invalid) as caught:
            design_files.source(self.root, reference)
        self.assertIn('docs/design.md 第 1 版', str(caught.exception))
        self.assertIn(f'第 {line} 行：验收 A1 的验证行：请改为', str(caught.exception))

    def test_r2_task_error_names_file_row_fields_and_fix(self):
        self.configure('medium')
        write(self.root / '.tw/local/task.json', self.task)
        code, result = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['problem'], '任务 .tw/local/task.json 的验收项 A1 含 expectation、checks；验收项只写编号，内容以方案为准')
        self.assertIn('修正任务文件 .tw/local/task.json', result['next_action'])
        self.assertNotIn('补齐任务和方案', result['next_action'])

    def test_r2_design_error_points_to_the_named_design_file(self):
        self.legacy_design()
        for command in ('start', 'design-draft'):
            with self.subTest(command=command):
                code, result = self.command(command, '--task', '.tw/local/task.json', '--design', 'docs/design.md')
                self.assertEqual(code, 1, result)
                self.assertIn('修正方案文件 docs/design.md', result['next_action'] or '')
                self.assertNotIn('补齐任务和方案', result['next_action'] or '')

    def test_r3_substitute_hint_is_a_full_line_and_names_only_missing(self):
        self.configure('medium')
        verification = self.design['sections'][1]['data']['verification']
        verification.update(cases=['tests.x::test_a'], substitutes=['邮件记录器'])
        self.profile['checks']['unit']['format'] = 'junit'
        self.profile['checks']['unit']['coverage']['substitutes'] = ['邮件记录器', '固定时钟']
        gap, = contracts.execution_environment(self.profile, self.task, self.design)
        self.assertEqual(gap, '把 A1 的验证行改为：- 验证：自动；用例 tests.x::test_a；替身 邮件记录器、固定时钟'
                             '（检查 unit 还使用了未允许的替身：固定时钟）')
        raw = designs.render(self.design)
        line = next(line for line in raw.splitlines() if line.startswith('- 验证：'))
        replacement = gap.split('改为：', 1)[1].split('（检查 ', 1)[0]
        loaded = designs.load(raw.replace(line, replacement))
        self.assertEqual(loaded['sections'][1]['data']['verification'],
                         {'method': 'automatic', 'cases': ['tests.x::test_a'], 'substitutes': ['邮件记录器', '固定时钟']})

    def test_r4_pending_approval_is_the_same_next_step_in_data_and_text(self):
        self.configure('medium')
        self.profile['checks']['unit']['coverage']['substitutes'] = ['固定时钟']
        fixtures.write_config(self.root, self.profile)
        args = ('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        for continued in (False, True):
            with self.subTest(continued=continued):
                code, result = self.command(*args)
                self.assertEqual(code, 0, result)
                self.assertEqual(result['continued'], continued)
                self.assertTrue(result['next_action'].startswith('tw team approval-draft '), result)
                self.assertEqual(result['next_step'], {'id': 'approval', 'label': '取得待确认章节的批准',
                                                      'next_command': result['next_action']})
                self.assertIn('下一步：取得待确认章节的批准', result['step_lines'])
                self.assertIn(result['next_action'], result['step_lines'])
                self.assertNotIn('下一步：运行检查', result['step_lines'])
                text = commands.readable(result)
                self.assertIn('\n验收无法满足：\n- ' + result['verification_gaps'][0], text)
                self.assertIn('下一步：取得待确认章节的批准\n' + result['next_action'], text)

    def test_r4_without_pending_sections_keeps_verification_fix_first(self):
        self.configure('medium')
        self.profile['checks']['unit']['coverage']['substitutes'] = ['固定时钟']
        fixtures.write_config(self.root, self.profile)
        write(self.root / '.tw/local/approved.json', designs.approval_draft(self.design, 'carol'))
        args = ('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                '--approval', '.tw/local/approved.json')
        for continued in (False, True):
            code, result = self.command(*args)
            self.assertEqual(code, 0, result)
            self.assertEqual(result['continued'], continued)
            self.assertEqual(result['pending_sections'], [])
            self.assertEqual(result['next_step']['id'], 'run')
            self.assertTrue(result['next_action'].startswith(result['verification_gaps'][0]))

    def test_r5_identity_start_reuses_original_design_path_from_preparation(self):
        self.configure('medium')
        original = 'docs/notification design.md'
        plans.write_design(self.root / original, self.design)
        code, first = self.command('start', '--task', '.tw/local/task.json', '--design', original)
        self.assertEqual(code, 0, first)
        code, resumed = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, resumed)
        self.assertTrue(resumed['continued'])
        arguments = shlex.split(resumed['next_action'])
        self.assertEqual(arguments[arguments.index('--design') + 1], original)
        context = read(self.root / first['context']['path'])
        self.assertEqual(context['preparation_inputs']['design_path'], original)

    def test_r6_empty_confirmation_has_no_basis_label(self):
        self.configure('medium')
        args = ('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md', '--reviewer', 'carol')
        code, empty = self.command(*args)
        self.assertEqual(code, 0, empty)
        self.assertNotIn('依据：', empty['summary'])
        code, confirmed = self.command(*args, '--confirmation', '会议确认')
        self.assertEqual(code, 0, confirmed)
        self.assertIn('依据：会议确认', confirmed['summary'])

    def test_r7_unknown_approval_sections_are_named_in_chinese(self):
        self.configure('medium')
        args = ('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        write(self.root / '.tw/local/input.json', {'reviewer': 'carol', 'section_ids': ['A9', 'A8']})
        for extra in [('--reviewer', 'carol', '--sections', 'A9,A8'), ('--record', '.tw/local/input.json')]:
            with self.subTest(arguments=extra):
                code, result = self.command(*args, *extra)
                self.assertEqual(code, 1, result)
                self.assertEqual(result['problem'], '批准范围包含不存在的章节：A9、A8')
        with self.assertRaisesRegex(Invalid, '批准范围包含不存在的章节：A9'):
            designs.approval_draft(self.design, 'carol', section_ids=['A9'])

    def test_r8_own_content_change_reason_includes_labels(self):
        self.configure('medium')
        before = copy.deepcopy(self.design)
        approval = designs.approval_draft(before, 'carol')
        self.design['revision'] = 2
        self.design['sections'][1]['data']['verification']['cases'] = ['tests.x::test_a']
        status = designs.approval_status(self.design, [approval], history=[before], changed_paths=[])
        self.assertEqual(status['sections']['A1']['reason'], '内容已改')
        self.assertEqual(status['sections']['T1']['reason'], '依赖 A1 已改')

    def test_r9_local_design_draft_has_no_platform_publication_steps(self):
        self.configure('medium')
        code, result = self.command('design-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, result)
        self.assertNotIn('next_steps', result)
        self.assertNotIn('承载方案的变更请求', commands.readable(result))


class TrialReviewFeedback(unittest.TestCase):
    base = markdown.MarkdownReview
    setUp, git, check, setup_task, write, name, command, rule, current_path, current = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.command,
        base.rule, base.current_path, base.current)
    prepared, many_cases, field, completed, submit = base.prepared, base.many_cases, base.field, base.completed, base.submit

    def test_r10_generated_wording_names_the_design(self):
        section = self.many_cases(declared=False)
        self.assertIn('方案未登记对应用例', section)
        self.assertNotIn('本验收未登记对应用例', section)

    def test_r10_summary_names_union_of_design_and_review_cases(self):
        self.many_cases(declared=True)
        path = self.current_path().parent / 'review.md'
        source = self.field(self.completed(path.read_text()), '## 验收 A1', '用例', 'Suite::case07')
        code, submitted = self.submit(path, source)
        self.assertEqual(code, 0, submitted)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertIn('；用例 Arithmetic::adds、Suite::case07', accepted['summary_markdown'])
        self.assertNotIn('未指明用例', accepted['summary_markdown'])
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', '无知识变化')
        self.assertEqual(code, 0, delivered)
        self.assertIn('；用例 Arithmetic::adds、Suite::case07', delivered['summary_markdown'])
        self.assertNotIn('未指明用例', delivered['summary_markdown'])

    def test_r11_invalid_review_cases_point_to_the_same_resubmit_command(self):
        self.many_cases(declared=False, skipped=True)
        path = self.current_path().parent / 'review.md'
        original = self.completed(path.read_text())
        editable = '.tw/local/review for resubmit.md'
        source = self.root / editable
        for case in ('Unknown::case', 'Other::skipped'):
            source.write_text(self.field(original, '## 验收 A1', '用例', case))
            code, submitted = self.command('review', '--task', self.task['id'], '--submit', '--file', editable)
            self.assertEqual(code, 0, submitted)
            actions = []
            for operation in ('accept', 'deliver', 'review', 'status'):
                with self.subTest(case=case, operation=operation):
                    code, result = self.command(operation, '--task', self.task['id'])
                    self.assertEqual(code, 1 if operation in ('accept', 'deliver') else 0, result)
                    action = result['next_action']
                    actions.append(action)
                    self.assertIn('“用例”字段', action)
                    self.assertIn('--submit --file ', action)
                    arguments = shlex.split(action[action.index('tw team review '):])
                    self.assertEqual(arguments[arguments.index('--file') + 1], editable)
                    self.assertNotIn('tw team accept ', action)
                    self.assertNotIn('tw team deliver ', action)
            self.assertEqual(len(set(actions)), 1)
        self.assertIn('--file ', actions[-1])
        arguments = shlex.split(actions[-1][actions[-1].index('tw team review '):])
        source.write_text(self.field(original, '## 验收 A1', '用例', 'Arithmetic::adds'))
        code, corrected = self.command(*arguments[2:])
        self.assertEqual(code, 0, corrected)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)


class TrialFeedbackDocs(unittest.TestCase):
    def test_r12_local_approval_guidance_names_the_saved_file_and_reuse(self):
        path = Path(__file__).parents[1] / 'skills/team-workflow/references/team-delivery.md'
        self.assertIn('本地任务保留 `approval-draft` 生成的 `approval.json`，用 `start --approval <approval.json>` 传入，之后的开工会沿用。',
                      path.read_text())


class PublishedFeedback(unittest.TestCase):
    base = published.Reconciliation
    setUp, git, check, prepare, body, github, publish_fixture, setup_record, draft, command, old_history = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github,
        base.publish_fixture, base.setup_record, base.draft, base.command, base.old_history)

    def test_r2_history_parse_error_keeps_the_named_file_repair(self):
        self.old_history()
        code, result = self.command('start')
        self.assertEqual(code, 1, result)
        self.assertIn('docs/design.md', result['next_action'])
