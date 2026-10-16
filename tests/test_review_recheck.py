"""B2: changes require explicit per-section rechecks through the real CLI."""
import copy
import hashlib
import os
import re
import unittest

import test_markdown_review as markdown
import test_workflow as fixtures
from common import artifact, artifact_valid, read, write
import designs
import plan_fixtures as plans


class ReviewRecheck(unittest.TestCase):
    base = markdown.MarkdownReview
    setUp, git, check, setup_task, write, name, command, rule, current_path, current = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.command,
        base.rule, base.current_path, base.current)
    prepared, draft, field, completed, submit, assert_position = (
        base.prepared, base.draft, base.field, base.completed, base.submit, base.assert_position)

    def submitted(self, manual=False, issues=None):
        path, _ = self.draft(manual=manual, issues=issues)
        source = self.completed(path.read_text(), manual=manual)
        if not manual:
            (self.root / '.tw/local/inspection.txt').write_text('Independently inspected the original behavior.\n')
            source = self.field(source, '## 规范 standards', '证据文件', '.tw/local/inspection.txt')
        code, result = self.submit(path, source)
        self.assertEqual(code, 0, result)
        self.initial = result
        self.initial_text = source
        return path, result

    def rerun(self, source=True):
        if source:
            (self.root / 'app.py').write_text('def add(a, b):\n    # Same confirmed behavior; new implementation.\n    return sum((a, b))\n')
        code, result = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        plans.submit_scenarios(self.root, self.task)
        self.ran = result
        return result

    def recheck(self):
        code, result = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        return self.root / result['review_file'], result

    def confirmed(self, source):
        self.assertIn('- 复核：待复核', source)
        return source.replace('- 复核：待复核', '- 复核：已复核')

    def legacy_b1_submission(self):
        """Persist the public B1 record shapes: no source manifest, latest pointer, or result signatures."""
        path, submitted = self.submitted()
        editor_path = self.current_path().parent / 'reviews/editor.json'
        editor = read(editor_path)
        binding_path = artifact_valid(self.root, editor['current'])
        value = read(binding_path)
        for key in ('source_snapshot', 'acceptance_results', 'rechecks'):
            value.pop(key, None)
        value['bindings']['format_version'] = 1
        write(binding_path, value)
        binding = artifact(self.root, binding_path)
        source = path.read_text().replace('"format_version": 2', '"format_version": 1')
        path.write_text(source)
        original_path = artifact_valid(self.root, submitted['review_markdown'])
        original_path.write_text(source)
        original = artifact(self.root, original_path)
        editor['current'] = binding
        editor['generations'][submitted['draft_id']] = binding
        editor.pop('latest', None)
        editor['submitted'][submitted['draft_id']] = {'review': submitted['artifact'], 'markdown': original,
            'default_sha': hashlib.sha256(source.encode('utf-8')).hexdigest()}
        write(editor_path, editor)
        group = self.current()
        group.pop('review_source', None)
        group['review_markdown'] = original
        write(self.current_path(), group)
        return path

    def test_source_and_run_changes_prefill_old_fields_and_current_actual_results(self):
        path, previous = self.submitted()
        old = read(self.root / previous['artifact']['path'])
        self.rerun()
        path, result = self.recheck()
        text = path.read_text()
        self.assertTrue(result['recheck'])
        for value in ('- 评审人：carol', '- 知识冲突已处理：是', old['standards']['summary'],
                      old['spec']['summary'], '.tw/local/inspection.txt', 'Arithmetic::adds', 'sum=3'):
            self.assertIn(value, text)
        self.assertEqual(text.count('- 复核：待复核'), 3)
        self.assertIn(self.ran['artifact']['path'], text)
        self.assertIn('## 变化', text)
        self.assertEqual(result['changes']['files'], ['app.py'])
        self.assertEqual(result['changes']['acceptance'], ['A1'])
        self.assertIn('app.py', text[text.index('## 变化'):])
        self.assertEqual(self.current()['review'], previous['artifact'])

    def test_pending_submission_lists_all_sections_and_line_numbers(self):
        path, previous = self.submitted()
        self.rerun()
        path, _ = self.recheck()
        text = path.read_text()
        before = self.current_path().read_bytes()
        count = len(list(self.current_path().parent.glob('requests/*/review.json')))
        code, refused = self.submit(path, text)
        self.assertEqual(code, 1, refused)
        for name in ('规范 standards', '需求 spec', '验收 A1'):
            block = text.index('## ' + name)
            marker = text.index('- 复核：待复核', block)
            self.assertIn(name, refused['problem'])
            self.assertRegex(refused['problem'], r'第\s*' + str(text[:marker].count('\n') + 1) + r'\s*行')
        self.assertEqual(self.current_path().read_bytes(), before)
        self.assertEqual(len(list(self.current_path().parent.glob('requests/*/review.json'))), count)
        self.assertEqual(self.current()['review'], previous['artifact'])

    def test_every_confirmation_allows_submission_and_accept_with_new_run(self):
        path, _ = self.submitted()
        self.rerun()
        path, _ = self.recheck()
        code, result = self.submit(path, self.confirmed(path.read_text()))
        self.assertEqual(code, 0, result)
        value = read(self.root / result['artifact']['path'])
        self.assertEqual(value['acceptance'][0]['observations'][0]['run'], self.ran['artifact'])
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertTrue(accepted['business_accepted'])

    def test_rewritten_conclusions_require_confirmation_and_replace_old_summaries(self):
        path, _ = self.submitted()
        self.rerun()
        path, _ = self.recheck()
        source = path.read_text()
        for name in ('## 规范 standards', '## 需求 spec', '## 验收 A1'):
            source = self.field(source, name, '理由', '本轮重新核对实际入口，仍返回结果3。')
        code, refused = self.submit(path, source)
        self.assertEqual(code, 1, refused)
        code, result = self.submit(path, self.confirmed(source))
        self.assertEqual(code, 0, result)
        value = read(self.root / result['artifact']['path'])
        for row in (value['standards'], value['spec'], value['acceptance'][0]):
            self.assertEqual(row['summary'], '本轮重新核对实际入口，仍返回结果3。')

    def test_missing_partial_or_invalid_recheck_fields_cannot_bypass_confirmation(self):
        path, _ = self.submitted()
        self.rerun(source=False)
        path, _ = self.recheck()
        source = path.read_text()
        variants = [source.replace('- 复核：待复核\n', ''),
                    source.replace('- 复核：待复核', '- 复核：已复核', 1),
                    source.replace('- 复核：待复核', '- 复核：无需复核')]
        for variant in variants:
            with self.subTest(source=variant[-150:]):
                code, refused = self.submit(path, variant)
                self.assertEqual(code, 1, refused)
                self.assert_position(refused)
                self.assertIn('复核', refused['problem'])

    def test_expired_unsubmitted_draft_is_archived_exactly_and_prefills_partial_work(self):
        path, _ = self.draft()
        source = self.field(path.read_text(), '## 评审信息', '评审人', 'dave')
        source = self.field(source, '## 规范 standards', '结论', '通过')
        source = self.field(source, '## 规范 standards', '理由', '草稿中尚未提交的独立阅读结论。')
        original = source.replace('\n', '\r\n').encode('utf-8')
        path.write_bytes(original)
        self.rerun()
        path, result = self.recheck()
        self.assertNotEqual(path.read_bytes(), original)
        saved = artifact_valid(self.root, result['archived_draft'])
        self.assertNotEqual(saved, path)
        self.assertEqual(saved.read_bytes(), original)
        self.assertIn('- 评审人：dave', path.read_text())
        self.assertIn('草稿中尚未提交的独立阅读结论。', path.read_text())
        self.assertIn('- 复核：待复核', path.read_text())
        self.assertIsNone(self.current()['review'])

    def test_expired_working_copy_takes_priority_over_last_submitted_conclusions(self):
        path, _ = self.submitted()
        source = self.field(path.read_text(), '## 规范 standards', '理由', '未提交的最新判断，不能丢失。')
        path.write_text(source)
        self.rerun()
        path, result = self.recheck()
        self.assertEqual(artifact_valid(self.root, result['archived_draft']).read_text(), source)
        self.assertIn('未提交的最新判断，不能丢失。', path.read_text())
        self.assertTrue(result['recheck'])

    def test_document_scenarios_are_preserved_and_rechecked_with_acceptance(self):
        path, previous = self.submitted(manual=True)
        observed = read(self.root / previous['artifact']['path'])['acceptance'][0]['observations']
        self.rerun()
        path, _ = self.recheck()
        source = path.read_text()
        self.assertNotIn('人工观察', source)
        self.assertEqual(source.count('- 复核：待复核'), 3)
        code, refused = self.submit(path, source)
        self.assertEqual(code, 1, refused)
        code, result = self.submit(path, self.confirmed(source))
        self.assertEqual(code, 0, result)
        current = read(self.root / result['artifact']['path'])['acceptance'][0]['observations']
        self.assertEqual(current[0]['kind'], 'scenarios')
        self.assertTrue(all(ref in current[0]['rounds'] for ref in observed[0]['rounds']))


    def test_file_comparison_uses_saved_fingerprints_including_additions_and_deletions(self):
        (self.root / 'removed.py').write_text('obsolete = True\n')
        path, previous = self.submitted()
        saved = read(artifact_valid(self.root, previous['review_source']))
        self.assertEqual(saved['files']['app.py']['sha256'], hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest())
        before = (self.root / 'app.py').stat()
        self.rerun()
        os.utime(self.root / 'app.py', ns=(before.st_atime_ns, before.st_mtime_ns))
        (self.root / 'removed.py').unlink()
        (self.root / 'added.py').write_text('enabled = True\n')
        self.rerun(source=False)
        path, result = self.recheck()
        self.assertEqual(result['changes']['files'], ['added.py', 'app.py', 'removed.py'])
        self.assertIn('added.py', path.read_text())
        self.assertIn('removed.py', path.read_text())

    def test_mtime_only_change_keeps_the_submitted_review_current(self):
        path, _ = self.submitted()
        before = path.read_bytes()
        stat = (self.root / 'app.py').stat()
        os.utime(self.root / 'app.py', ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
        path, result = self.recheck()
        self.assertTrue(result['review_current'])
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn('待复核', path.read_text())

    def test_run_only_change_requires_recheck_even_when_source_files_match(self):
        self.submitted()
        self.rerun(source=False)
        path, result = self.recheck()
        self.assertTrue(result['recheck'])
        self.assertEqual(result['changes']['files'], [])
        self.assertEqual(result['changes']['acceptance'], ['A1'])
        self.assertIn('- 复核：待复核', path.read_text())

    def test_policy_change_requires_recheck_without_reexecuting_unchanged_definition(self):
        self.submitted()
        self.profile['checks']['unit']['purpose'] = 'Updated confirmation scope, original execution still usable'
        fixtures.write_config(self.root, self.profile)
        path, result = self.recheck()
        self.assertTrue(result['recheck'])
        self.assertEqual(result['changes']['files'], [])
        self.assertIn('校验策略', path.read_text())

    def test_legacy_b1_policy_change_does_not_invent_file_or_running_result_changes(self):
        self.legacy_b1_submission()
        self.profile['checks']['unit']['purpose'] = 'Clarified review policy only'
        fixtures.write_config(self.root, self.profile)
        path, result = self.recheck()
        self.assertTrue(result['recheck'])
        self.assertTrue(result['changes']['baseline_complete'])
        self.assertEqual(result['changes']['files'], [])
        self.assertEqual(result['changes']['acceptance'], [])
        self.assertIn('- 复核：待复核', path.read_text())

    def test_legacy_b1_without_old_file_hashes_reports_unknown_history_after_source_changes(self):
        self.legacy_b1_submission()
        self.rerun()
        path, result = self.recheck()
        self.assertFalse(result['changes']['baseline_complete'])
        self.assertIn('无法还原精确文件差异', path.read_text())
        self.assertIn('- 复核：待复核', path.read_text())

    def test_task_and_section_changes_can_reuse_review_history_across_new_contexts(self):
        self.submitted()
        self.task['goal'] = 'Same operation, clarified task goal'
        self.design['sections'][1]['title'] = 'Confirmed addition acceptance'
        self.write('task', self.task)
        self.write('design', self.design)
        self.write('approval-new', designs.approval_draft(self.design, 'carol', 'Confirmed revised sections', mode='design'))
        code, started = self.command('start', '--task', self.name('task'), '--design', self.name('design'),
                                     '--approval', self.name('approval-new'))
        self.assertEqual(code, 0, started)
        self.assertFalse(started['continued'])
        self.rerun(source=False)
        path, result = self.recheck()
        self.assertTrue(result['recheck'])
        self.assertIn('已核对业务要求、实际入口和原始结果。', path.read_text())
        self.assertIn('任务', path.read_text()[path.read_text().index('## 变化'):])
        self.assertIn('章节', path.read_text()[path.read_text().index('## 变化'):])

    def test_status_marks_review_stale_and_points_to_generation_after_run_change(self):
        self.submitted()
        self.rerun(source=False)
        code, result = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        step = next(row for row in result['steps'] if row['id'] == 'review')
        self.assertEqual(step['state'], 'stale')
        self.assertIn('tw team review', step['next_command'])
        self.assertIn('--submit', step['next_command'])  # run already generated the current recheck form.
        self.assertEqual(result['next_step']['id'], 'review')

    def test_unchanged_review_is_reported_current_without_a_new_generation(self):
        path, previous = self.submitted()
        before = path.read_bytes()
        bindings = sorted(self.current_path().parent.glob('reviews/*/binding.json'))
        path, result = self.recheck()
        self.assertTrue(result['review_current'])
        self.assertFalse(result['recheck'])
        self.assertIn('仍然有效', result['summary'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(self.current_path().parent.glob('reviews/*/binding.json')), bindings)
        self.assertEqual(self.current()['review'], previous['artifact'])

    def test_generation_request_id_is_bound_to_the_previous_submitted_review(self):
        self.submitted()
        self.rerun()
        arguments = ('review', '--task', self.task['id'], '--request-id', 'fixed-review-history')
        code, draft = self.command(*arguments)
        self.assertEqual(code, 0, draft)
        path = self.root / draft['review_file']
        code, submitted = self.submit(path, self.confirmed(path.read_text()))
        self.assertEqual(code, 0, submitted)
        before = self.current_path().read_bytes()
        code, refused = self.command(*arguments)
        self.assertEqual(code, 1, refused)
        self.assertIn('Request ID already belongs to different inputs', refused['problem'])
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_known_issue_identity_is_preserved_and_disposition_can_be_updated(self):
        issue = {'id': 'Q1', 'owner': 'carol', 'affects': ['A1'], 'blocks': ['acceptance'], 'state': 'resolved',
                 'summary': 'Confirm the exact operation result',
                 'resolution': {'reason': 'Independently confirmed before approval', 'evidence': ['Confirmed business SOP']}}
        path, _ = self.submitted(issues=[issue])
        self.rerun()
        path, _ = self.recheck()
        source = self.confirmed(path.read_text())
        broken = self.field(source, '### 问题 Q1', '负责人', 'bob')
        code, refused = self.submit(path, broken)
        self.assertEqual(code, 1, refused)
        self.assertIn('问题 Q1', refused['problem'])
        source = self.field(source, '### 问题 Q1', '处置理由', '本轮再次独立核对，问题已解决。')
        code, result = self.submit(path, source)
        self.assertEqual(code, 0, result)
        actual = read(self.root / result['artifact']['path'])['findings'][0]
        for key in ('id', 'owner', 'affects', 'blocks', 'summary'):
            self.assertEqual(actual[key], issue[key])
        self.assertEqual(actual['resolution']['reason'], '本轮再次独立核对，问题已解决。')


if __name__ == '__main__':
    unittest.main()
