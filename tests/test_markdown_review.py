"""B1: editable Markdown reviews through the CLI, with immutable submission evidence."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

import test_current_materials
import test_workflow as fixtures
import plan_fixtures as plans
from common import artifact, artifact_valid, read
import artifacts
import cleanup
import designs
import records

TW = fixtures.SCRIPTS.parents[1] / 'tw.py'


class MarkdownReview(unittest.TestCase):
    base = test_current_materials.CurrentMaterials
    setUp, git, check, setup_task, write, name, command, rule, current_path, current = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.command,
        base.rule, base.current_path, base.current)

    def prepared(self, manual=False, issues=None):
        self.setup_task(complexity='medium')
        if manual:
            self.task['kind'] = 'docs'
            self.task['acceptance'][0]['checks'] = []
            self.design['sections'][1]['data']['checks'] = []
            self.design['sections'][1]['data']['verification'] = {
                'method': 'manual', 'coverage': plans.coverage('manual'), 'cases': []}
        else:
            code = "import app; from pathlib import Path; assert app.add(1,2)==3; print('sum=3'); Path('{output}/results.xml').write_text('<testsuite tests=\"1\"><testcase classname=\"Arithmetic\" name=\"adds\"/></testsuite>')"
            self.check(code, format='junit', report='{output}/results.xml', required_cases=['Arithmetic::adds'])
            self.design['sections'][1]['data']['verification']['cases'] = ['Arithmetic::adds']
        if issues is not None:
            self.design['issues'] = copy.deepcopy(issues)
        fixtures.write_config(self.root, self.profile)
        self.write('task', self.task)
        self.write('design', self.design)
        self.write('approval-plan', designs.approval_draft(self.design, 'carol', 'Confirmed business scope', mode='design'))
        code, started = self.command('start', '--task', self.name('task'), '--design', self.name('design'),
                                     '--approval', self.name('approval-plan'))
        self.assertEqual(code, 0, started)
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        self.ran = ran
        return started, ran

    def draft(self, **options):
        self.prepared(**options)
        before = self.current_path().read_bytes()
        code, result = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current_path().read_bytes(), before)
        return self.root / result['review_file'], result

    def field(self, text, section, key, value):
        start = text.index(section)
        end = re.search(r'(?m)^#{1,3} ', text[start + len(section):])
        limit = start + len(section) + end.start() if end else len(text)
        block = text[start:limit]
        pattern = r'(?m)^- ' + re.escape(key) + r'：[ \t]*[^\n]*$'
        block, count = re.subn(pattern, lambda _: '- ' + key + '：' + value, block)
        self.assertEqual(count, 1, (section, key, text))
        return text[:start] + block + text[limit:]

    def completed(self, text, manual=False):
        text = self.field(text, '## 评审信息', '评审人', 'carol')
        text = self.field(text, '## 评审信息', '知识冲突已处理', '是')
        for section in ('## 规范 standards', '## 需求 spec', '## 验收 A1'):
            text = self.field(text, section, '结论', '通过')
            text = self.field(text, section, '理由', '已核对业务要求、实际入口和原始结果。')
        if manual:
            evidence = self.root / '.tw/local/manual-result.txt'
            evidence.write_text('result=3; count=1\n')
            for key, value in {'观察人': 'carol', '时间': '2026-01-01T00:00:00+00:00',
                               '操作': '从实际入口读取算术结果', '结果': '观察到结果为 3',
                               '数据': 'result=3; count=1', '证据文件': '.tw/local/manual-result.txt'}.items():
                text = self.field(text, '### 人工观察 A1', key, value)
        return text

    def submit(self, path, text, *options):
        path.write_text(text)
        return self.command('review', '--task', self.task['id'], '--submit', *options)

    def assert_position(self, result, section=None):
        self.assertRegex(result['problem'], r'第\s*\d+\s*行|小节')
        if section:
            self.assertIn(section, result['problem'])

    def test_help_exposes_review_and_removes_review_template(self):
        result = subprocess.run([sys.executable, str(TW), 'team', '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(?m)^\s+review\s+')
        self.assertNotIn('review-template', result.stdout)
        result = subprocess.run([sys.executable, str(TW), 'team', 'review-template'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_markdown_contains_bound_actual_results_and_no_handwritten_fingerprint_placeholders(self):
        path, result = self.draft()
        self.assertEqual(path, self.current_path().parent / 'review.md')
        text = path.read_text()
        for value in ('## 规范 standards', '## 需求 spec', '## 验收 A1', '## 风险', 'unit', 'Arithmetic::adds', 'sum=3'):
            self.assertIn(value, text)
        self.assertIn('<!-- tw-review:binding:start -->', text)
        self.assertIn('task_digest', text)
        self.assertNotIn('__REPLACE__', text)
        self.assertNotRegex(text, r'<(?:run|review|approval)\.json>')
        self.assertIsNone(self.current()['review'])

    def test_submission_generates_original_json_and_accept_uses_it_automatically(self):
        path, _ = self.draft()
        source = self.completed(path.read_text())
        code, result = self.submit(path, source)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['review_submitted'])
        review = read(self.root / result['artifact']['path'])
        self.assertEqual((review['kind'], review['reviewer']), ('review', 'carol'))
        self.assertTrue(review['knowledge_conflicts_resolved'])
        observation = review['acceptance'][0]['observations'][0]
        self.assertEqual(observation, {'kind': 'execution', 'run': self.ran['artifact'],
                                      'check': 'unit', 'cases': ['Arithmetic::adds']})
        self.assertTrue(review['standards']['evidence'])
        self.assertEqual(self.current()['review'], result['artifact'])
        saved = self.current()['review_markdown']
        self.assertEqual((self.root / saved['path']).read_text(), source)
        self.assertNotEqual(self.root / saved['path'], path)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertTrue(accepted['business_accepted'])

    def many_cases(self, declared, skipped=False):
        self.setup_task(complexity='medium')
        rows = ['<testcase classname="Arithmetic" name="adds"/>']
        rows += [f'<testcase classname="Suite" name="case{i:02}"/>' for i in range(40)]
        if skipped:
            rows.append('<testcase classname="Other" name="skipped"><skipped/></testcase>')
        (self.root / 'cases.xml').write_text(f'<testsuite tests="{len(rows)}">' + ''.join(rows) + '</testsuite>')
        code = ("import app, shutil; assert app.add(1,2)==3; print('sum=3'); "
                "shutil.copy('cases.xml', '{output}/results.xml')")
        self.check(code, format='junit', report='{output}/results.xml',
                   required_cases=['Arithmetic::adds'] if declared else [])
        self.design['sections'][1]['data']['verification']['cases'] = ['Arithmetic::adds'] if declared else []
        fixtures.write_config(self.root, self.profile)
        self.write('task', self.task)
        self.write('design', self.design)
        self.write('approval-plan', designs.approval_draft(self.design, 'carol', 'Confirmed business scope', mode='design'))
        code, started = self.command('start', '--task', self.name('task'), '--design', self.name('design'),
                                     '--approval', self.name('approval-plan'))
        self.assertEqual(code, 0, started)
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        code, result = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        text = (self.root / result['review_file']).read_text()
        begin = text.index('## 验收 A1')
        return text[begin:text.index('- 结论：', begin)]

    def test_undeclared_cases_are_summarised_not_listed_one_by_one(self):
        # Real case (Issue #5): every executed case was listed under every acceptance item; the
        # review grew to 424 KB, unreadable and past a pull request comment's size limit.
        section = self.many_cases(declared=False)
        self.assertNotIn('Suite::case07', section)
        self.assertRegex(section, r'共 41 项.*通过 41')
        self.assertLess(len(section), 2000)

    def test_declared_cases_and_every_unpassed_case_are_listed(self):
        section = self.many_cases(declared=True, skipped=True)
        self.assertIn('用例 Arithmetic::adds：通过', section)
        self.assertIn('用例 Other::skipped：跳过', section)
        self.assertNotIn('Suite::case07', section)
        self.assertRegex(section, r'共 42 项')

    def test_binding_edits_are_rejected_before_a_review_material_is_created(self):
        path, _ = self.draft()
        source = self.completed(path.read_text())
        binding = records.block(source, 'review')
        text = source.replace(records.comment(binding), records.comment({**binding, 'task_id': 'TASK-other'}))
        before = self.current_path().read_bytes()
        code, refused = self.submit(path, text)
        self.assertEqual(code, 1, refused)
        self.assert_position(refused, '绑定')
        self.assertEqual(self.current_path().read_bytes(), before)
        self.assertFalse(list(self.current_path().parent.glob('requests/*/review.json')))

    def test_missing_or_invalid_conclusion_reports_its_markdown_location(self):
        path, _ = self.draft()
        text = self.completed(path.read_text())
        for value in ('', '大概通过'):
            with self.subTest(value=value):
                broken = self.field(text, '## 规范 standards', '结论', value)
                code, refused = self.submit(path, broken)
                self.assertEqual(code, 1, refused)
                self.assert_position(refused, '规范')
                self.assertIsNone(self.current()['review'])

    def test_manual_observations_are_blank_and_missing_actor_or_result_is_rejected(self):
        path, _ = self.draft(manual=True)
        text = path.read_text()
        for field in ('观察人', '时间', '操作', '结果', '数据', '证据文件'):
            self.assertRegex(text, r'(?m)^- ' + field + r'：\s*$')
        complete = self.completed(text, manual=True)
        for field in ('观察人', '结果'):
            with self.subTest(field=field):
                broken = self.field(complete, '### 人工观察 A1', field, '')
                code, refused = self.submit(path, broken)
                self.assertEqual(code, 1, refused)
                self.assert_position(refused, '人工观察 A1')
                self.assertIsNone(self.current()['review'])
        code, result = self.submit(path, complete)
        self.assertEqual(code, 0, result)
        row = read(self.root / result['artifact']['path'])['acceptance'][0]['observations'][0]
        self.assertEqual(row['observer'], 'carol')
        self.assertIn('result=3; count=1', row['result'])

    def test_known_issue_identity_fields_cannot_be_changed(self):
        issue = {'id': 'Q1', 'owner': 'carol', 'affects': ['A1'], 'blocks': ['acceptance'],
                 'state': 'open', 'summary': 'Need the independently confirmed result', 'resolution': {}}
        path, _ = self.draft(issues=[issue])
        complete = self.completed(path.read_text())
        for key, value in [('编号', 'Q2'), ('负责人', 'bob'), ('影响范围', 'T1'), ('阻塞阶段', 'implementation')]:
            with self.subTest(field=key):
                broken = self.field(complete, '### 问题 Q1', key, value)
                code, refused = self.submit(path, broken)
                self.assertEqual(code, 1, refused)
                self.assert_position(refused, '问题 Q1')
                self.assertIsNone(self.current()['review'])

    def test_implementer_review_is_still_rejected_by_accept(self):
        path, _ = self.draft()
        code, submitted = self.submit(path, self.completed(path.read_text()))
        self.assertEqual(code, 0, submitted)
        review = read(self.root / submitted['artifact']['path'])
        review['reviewer'] = 'bob'
        self.write('self-review', review)
        code, refused = self.command('accept', '--task', self.task['id'], '--review', self.name('self-review'))
        self.assertEqual(code, 1, refused)
        self.assertIn('Reviewer must not be the implementation owner', refused['problem'])

    def test_unsubmitted_markdown_is_not_overwritten_and_progress_is_reported(self):
        path, first = self.draft()
        edited = self.field(path.read_text(), '## 评审信息', '评审人', 'carol')
        path.write_text(edited)
        before = path.read_bytes()
        code, again = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, again)
        self.assertEqual(again['review_file'], first['review_file'])
        self.assertEqual(path.read_bytes(), before)
        self.assertGreater(again['progress']['completed'], 0)

    def test_existing_draft_accepts_absolute_explicit_run_paths(self):
        path, _ = self.draft()
        before = path.read_bytes()
        alias = self.root.parent / (self.root.name + '-alias')
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        for base in (self.root, alias):
            with self.subTest(base=base):
                code, again = self.command('review', '--task', self.task['id'],
                                            '--run', str(base / self.ran['artifact']['path']))
                self.assertEqual(code, 0, again)
                self.assertTrue(again['binding_current'])
                self.assertEqual(path.read_bytes(), before)

    def test_failing_run_review_requires_complete_fields_and_is_saved_but_not_accepted(self):
        self.prepared()
        code = "from pathlib import Path; import sys; print('sum=wrong'); Path('{output}/results.xml').write_text('<testsuite tests=\"1\" failures=\"1\"><testcase classname=\"Arithmetic\" name=\"adds\"><failure>wrong sum</failure></testcase></testsuite>'); sys.exit(1)"
        self.check(code, format='junit', report='{output}/results.xml', required_cases=['Arithmetic::adds'])
        fixtures.write_config(self.root, self.profile)
        status, failed = self.command('run', '--task', self.task['id'])
        self.assertEqual(status, 1, failed)
        status, drafted = self.command('review', '--task', self.task['id'])
        self.assertEqual(status, 0, drafted)
        path = self.root / drafted['review_file']
        self.assertIn('Arithmetic::adds：失败', path.read_text())
        self.assertIn('sum=wrong', path.read_text())
        complete = self.completed(path.read_text())
        incomplete = self.field(complete, '## 验收 A1', '理由', '')
        status, refused = self.submit(path, incomplete)
        self.assertEqual(status, 1, refused)
        self.assert_position(refused)
        self.assertIsNone(self.current()['review'])
        status, submitted = self.submit(path, complete)
        self.assertEqual(status, 0, submitted)
        self.assertEqual(self.current()['review'], submitted['artifact'])
        status, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(status, 1, refused)
        self.assertIsNone(self.current()['acceptance'])

    def test_unsubmitted_draft_is_preserved_even_after_source_changes(self):
        path, _ = self.draft()
        before = path.read_bytes()
        (self.root / 'app.py').write_text('def add(a,b): return a + b + 1\n')
        code, again = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, again)
        self.assertEqual(artifact_valid(self.root, again['archived_draft']).read_bytes(), before)
        self.assertTrue(again['binding_current'])
        code, refused = self.submit(path, self.completed(path.read_text()))
        self.assertEqual(code, 1, refused)
        self.assert_position(refused)

    def test_status_requires_a_successful_submission_and_gives_the_submit_command(self):
        path, _ = self.draft()
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertNotEqual(next(row for row in status['steps'] if row['id'] == 'review')['state'], 'done')
        self.assertEqual(status['next_step']['id'], 'review')
        self.assertIn('review', status['next_step']['next_command'])
        self.assertIn('--submit', status['next_step']['next_command'])
        code, submitted = self.submit(path, self.completed(path.read_text()))
        self.assertEqual(code, 0, submitted)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'review')['state'], 'done')
        self.assertEqual(status['next_step']['id'], 'acceptance')

    def test_submit_accepts_an_external_markdown_copy(self):
        path, _ = self.draft()
        external = self.root.parent / (self.root.name + '-review.md')
        self.addCleanup(lambda: external.unlink(missing_ok=True))
        source = self.completed(path.read_text())
        external.write_text(source)
        code, submitted = self.command('review', '--task', self.task['id'], '--submit', '--file', str(external))
        self.assertEqual(code, 0, submitted)
        self.assertEqual((self.root / submitted['review_markdown']['path']).read_text(), source)

    def test_optional_evidence_paths_are_hashed_by_the_tool(self):
        path, _ = self.draft()
        evidence = self.root / '.tw/local/inspection.txt'
        evidence.write_text('Independently read the public assertion and original output.\n')
        source = self.completed(path.read_text())
        source = self.field(source, '## 规范 standards', '证据文件', '.tw/local/inspection.txt')
        code, submitted = self.submit(path, source)
        self.assertEqual(code, 0, submitted)
        review = read(self.root / submitted['artifact']['path'])
        self.assertIn(artifact(self.root, evidence), review['standards']['evidence'])

    def test_cleanup_keeps_submitted_markdown_review_runs_and_a_pending_draft(self):
        path, _ = self.draft()
        code, submitted = self.submit(path, self.completed(path.read_text()))
        self.assertEqual(code, 0, submitted)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.rule()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        code, delivered = self.command('verify', '--task', self.task['id'])
        self.assertEqual(code, 0, delivered)
        path.write_text(path.read_text() + '\n尚未提交的补充记录。\n')
        before = path.read_bytes()
        group = self.current()
        plan = cleanup.preview(self.root, 'all', 0)
        self.assertTrue(plan['ok'], plan)
        cleanup.apply(self.root, plan)
        self.assertEqual(path.read_bytes(), before)
        for ref in [group['review'], group['review_markdown'], *group['runs']]:
            artifact_valid(self.root, ref)


if __name__ == '__main__':
    unittest.main()
