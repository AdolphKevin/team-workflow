"""M8: platform prose is Markdown; only safe tw-record comments carry tool data."""
import copy
import re
import unittest

from test_designs import example
from common import Invalid, digest
import coordination
import issue_draft
import designs
import reviews


class HiddenRecordCases(unittest.TestCase):
    def test_m8_every_draft_roundtrips_unsafe_comment_characters(self):
        value = '中文 --flag --> <!--\n第二行\r\n\\u002d'
        rows = [('design', {'kind': 'design-record', 'task': 'task', 'creator': value,
                            'design': {'id': 'D1', 'revision': 1, 'path': 'docs/a.md', 'commit': 'a'*40}}),
                ('approval', {'kind': 'approval-record', 'approval': {'reviewer': value,
                    'design_revision': 1, 'confirmation': value, 'sections': {'A1': {}}}}),
                ('handoff', {'kind': 'handoff', 'owner': value, 'remaining': [value], 'done': []}),
                ('handoff', {'kind': 'handoff', 'handoff_kind': 'close', 'owner': value,
                             'remaining': [], 'done': [value], 'close': {'summary': value}}),
                ('progress', {'kind': 'progress', 'author': value, 'done': [value], 'remaining': [value]})]
        for name, row in rows:
            with self.subTest(name=name, close=row.get('handoff_kind')):
                draft = coordination._draft_result(name, 'task', row)
                raw = draft['markdown']
                self.assertNotIn('```json', raw)
                self.assertNotIn('```team-workflow-', raw)
                self.assertEqual(coordination.block(raw, name), row)
                payload = re.search(r'<!-- tw-record (.*?) -->', raw, re.S)[1]
                self.assertNotIn('--', payload)
                self.assertNotIn('<!--', payload)

    def test_task_has_goal_non_goals_acceptance_and_ignores_visible_prose(self):
        task = {'id': 'https://github.com/example/project/issues/1', 'data_version': 1,
                'goal': '目标 --flag -->\n中文', 'non_goals': ['不改支付'],
                'acceptance': [{'id': 'A1', 'expectation': '结果为三'}], 'parent': None}
        raw = issue_draft.body({'body': '# 原文'}, task, None)
        self.assertNotIn('```team-workflow-task', raw)
        for part in (task['goal'], '不改支付', '结果为三'):
            self.assertIn(__import__('html').escape(part, quote=False), raw)
        source = coordination.task_source({'html_url': task['id'], 'body': raw})
        edited = coordination.task_source({'html_url': task['id'], 'body': raw.replace('# 原文', '# 可见说明改变')})
        self.assertEqual(source, edited)
        self.assertEqual(source['task'], task)
        self.assertEqual(issue_draft.body({'body': raw}, task, None), raw)

    def test_visible_values_escape_html_comment_syntax(self):
        import html
        value = '中文 --flag --> <!-- value'
        row = {'kind': 'progress', 'author': value, 'done': [], 'remaining': [value]}
        raw = coordination._draft_result('progress', 'task', row)['markdown']
        visible = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
        self.assertIn(value, html.unescape(visible))
        self.assertEqual(coordination.block(raw, 'progress'), row)
        self.assertNotIn('<!-- value', raw)

    def test_comment_examples_in_fences_are_not_platform_records(self):
        import records
        sample = records.comment({'kind': 'progress', 'author': 'an example'})
        self.assertIsNone(coordination.block('```markdown\n' + sample + '\n```', 'progress', required=False))

    def test_old_fenced_records_are_rejected_with_regeneration_hint(self):
        for name in ('task', 'design', 'approval', 'handoff', 'progress'):
            with self.subTest(name=name), self.assertRaisesRegex(Invalid, '重新生成'):
                coordination.block('```team-workflow-' + name + '\n{}\n```\n', name, required=False)

    def test_approval_prose_names_revision_titles_and_confirmation(self):
        design = example()
        row = {'kind': 'approval-record', 'approval': designs.approval_draft(design, 'carol', '会议确认', section_ids=['A1'])}
        raw = coordination._draft_result('approval', 'task', row, design=design)['markdown']
        visible = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
        self.assertIn('carol 批准方案第 1 版：A1。依据：会议确认', visible)

    def test_unicode_line_separators_inside_strings_are_not_markdown_lines(self):
        for separator in ('\u0085', '\u2028', '\u2029'):
            with self.subTest(separator=ord(separator)):
                value = '中文' + separator + '```markdown' + separator + '换行结尾 --flag -->'
                row = {'kind': 'progress', 'author': value, 'done': [value], 'remaining': [value]}
                raw = coordination._draft_result('progress', 'task', row)['markdown']
                self.assertEqual(coordination.block(raw, 'progress'), row)

    def test_review_binding_is_hidden_and_protected(self):
        binding = {'format_version': 2, 'draft_id': 'a'*32, 'risks': [], 'task_id': '中文 -- -->\n'}
        value = {'bindings': binding, 'generated': {}, 'template': {'acceptance': [], 'findings': []}, 'automatic': {}, 'manual': {}}
        raw = reviews.render(value)
        self.assertNotIn('```json', raw)
        self.assertIn('<!-- tw-record ', raw)
        self.assertEqual(coordination.block(raw, 'review'), binding)
        # The same protected-region check is used before parsing editable fields.
        reviews._sections(raw, value)
        with self.assertRaises(reviews.ReviewError):
            reviews._sections(raw.replace('"format_version": 2', '"format_version": 3'), value)


if __name__ == '__main__':
    unittest.main()
