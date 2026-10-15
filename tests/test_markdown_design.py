"""M1–M4: the approved Markdown format preserves the existing design contract."""
import copy
import unittest

from test_designs import example, section, question
from common import Invalid
import designs


class MarkdownDesignCases(unittest.TestCase):
    def test_m1_roundtrip_all_fields_and_section_types(self):
        values = [example(level) for level in ('simple', 'medium', 'complex')]
        full = example()
        full['sections'].insert(1, section('scope-local', 'scope', data={'notes': ['中文', '--flag', '-->', '\n'], 'enabled': True}))
        full['sections'].insert(2, section('storage', 'data', data={'schema': {'version': 2}}))
        full['sections'][-1]['data']['assessment'] = copy.deepcopy(full['assessment'])
        full['sections'][3]['body'] = '## 未标记标题\n正文 | 中文 --flag -->'
        full['issues'] = [question('resolved'), dict(question(), id='Q2')]
        full['assessment']['uncertainties'] = ['Q2']
        full['issues'][0]['resolution'].update(confirmed_by='用户', confirmation='', follow_up='后续', scope_change='范围')
        full['sections'][4]['data']['extra'] = {'a': ['x、y', 'a|b', '\n']}
        values.append(full)
        for value in values:
            with self.subTest(complexity=value['assessment']['complexity'], sections=len(value['sections'])):
                raw = designs.render(value)
                self.assertNotIn('```json', raw)
                self.assertEqual(designs.load(raw), value)
                self.assertEqual(designs.fingerprints(designs.load(raw)), designs.fingerprints(value))

    def test_m2_intro_does_not_participate_in_fingerprints(self):
        value = example()
        raw = designs.render(value)
        index = raw.index('## ')
        edited = raw[:index] + '# 标题\n\n批准记录已更新。\n\n' + raw[index:]
        self.assertEqual(designs.load(edited), value)
        self.assertEqual(designs.fingerprints(designs.load(edited)), designs.fingerprints(value))

    def test_m3_only_changed_section_and_dependents_need_review(self):
        before = designs.load(designs.render(example()))
        approved = designs.approval_draft(before, 'alice')
        after = copy.deepcopy(before)
        after['revision'] = 2
        after['sections'][1]['body'] = '新的接口行为。'
        after = designs.load(designs.render(after))
        self.assertEqual(designs.impact(before, after, [], history=[before])['affected'], ['A1', 'T1', 'api-1'])
        status = designs.approval_status(after, [approved], history=[before], changed_paths=[])
        self.assertEqual(status['stale'], ['A1', 'T1', 'api-1'])
        self.assertEqual(status['approved'], ['A2', 'T2', 'api-2', 'scope-global'])

    def test_m4_format_errors_have_line_numbers(self):
        raw = designs.render(example())
        cases = [raw.replace('revision: 1\n', ''),
                 raw.replace('revision: 1', 'revision: "one"'),
                 raw.replace('type=interface', 'type=unknown', 1),
                 raw.replace('id=api-2', 'id=api-1'),
                 raw.replace('depends=api-1', 'depends=missing'),
                 raw.replace('id=api-1 type=interface', 'id=second-global type=global-scope'),
                 raw.replace('- 角色：caller\n', ''),
                 raw.replace('层级 journey', '层级 bad'),
                 '{}']
        for text in cases:
            with self.subTest(text=text[:100]), self.assertRaisesRegex(Invalid, r'第 \d+ 行'):
                designs.load(text)

    def test_body_ends_at_same_or_higher_marked_heading(self):
        raw = designs.render(example())
        raw = raw.replace('## api-1\n', '## api-1\n').replace('## api-2\n', '### api-2\n')
        loaded = designs.load(raw)
        self.assertIn('### api-2\n<!-- tw-section id=api-2', loaded['sections'][1]['body'])
        self.assertEqual(loaded['sections'][2]['body'], 'Required behavior.')

    def test_m1_unusual_text_and_extension_keys_roundtrip(self):
        value = example()
        value['sections'][1]['body'] = '\\- 角色：这是原本的反斜杠\n- 普通正文\n\\<!-- tw-issues -->'
        value['sections'][1]['data'] = {'中文：字段\n换行': {'value': 'a|b、c；d\n-->'}}
        issue = question('resolved')
        issue['resolution']['confirmation'] = '—'
        value['issues'] = [issue]
        self.assertEqual(designs.load(designs.render(value)), value)

    def test_m4_invalid_structured_values_report_the_actual_line(self):
        raw = designs.render(example())
        changed = raw.replace('- 范围：src/orders', '- 范围：../outside')
        line = next(i for i, text in enumerate(changed.splitlines(), 1) if text == '- 范围：../outside')
        with self.assertRaisesRegex(Invalid, f'第 {line} 行'):
            designs.load(changed)

    def test_m4_unknown_text_after_labels_is_not_silently_lost(self):
        raw = designs.render(example()).replace('- 前置任务：无', '- 前置任务：无\n必须保留这条业务要求。', 1)
        with self.assertRaisesRegex(Invalid, r'第 \d+ 行'):
            designs.load(raw)

    def test_m1_lists_preserve_unbalanced_punctuation(self):
        for values in ([']first', 'second'], ['a"b', 'c'], ['x{y', 'z']):
            with self.subTest(values=values):
                value = example()
                value['sections'][3]['data']['scenario']['steps'] = values
                self.assertEqual(designs.load(designs.render(value)), value)

    def test_m1_long_fence_keeps_short_fences_and_labels_as_prose(self):
        value = example()
        value['sections'][3]['body'] = '例子：\n````markdown\n```\n- 角色：this is code\n````'
        self.assertEqual(designs.load(designs.render(value)), value)

    def test_m1_unclosed_body_fences_cannot_swallow_later_sections(self):
        for body in ('```', '```python\nx', '```python\n```example\n- 角色：仅示例', '\\```python\n- 角色：原有反斜杠'):
            with self.subTest(body=body):
                value = example()
                value['sections'][1]['body'] = body
                self.assertEqual(designs.load(designs.render(value)), value)

    def test_m4_table_separator_has_the_same_column_count(self):
        raw = designs.render(example()).replace('| --- | --- | --- | --- | --- | --- | --- |', '| --- |', 1)
        with self.assertRaisesRegex(Invalid, r'第 \d+ 行'):
            designs.load(raw)

    def test_fenced_marker_examples_are_body_text(self):
        value = example()
        value['sections'][1]['body'] = '例子：\n```markdown\n## Example\n<!-- tw-section id=fake type=scope -->\n示例\n```'
        self.assertEqual(designs.load(designs.render(value)), value)


if __name__ == '__main__':
    unittest.main()
