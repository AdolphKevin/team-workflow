"""R1/R2: authoring whitespace and readable labels preserve the approved content."""
import copy
import re
import unittest
from pathlib import Path

from test_designs import example
import designs
import plan_fixtures as plans


class MarkdownReadabilityCases(unittest.TestCase):
    def test_r1_blank_lines_and_trailing_spaces_keep_approval(self):
        design = example()
        raw = designs.render(design)
        approved = designs.approval_draft(design, 'alice')
        variants = [raw.replace('\n## ', '\n\n\n## ')
                       .replace('\nRequired behavior.\n', '\n\nRequired behavior. \t\n\n'),
                    raw.replace('\n\n## ', '\n## ').replace('\n\n- ', '\n- ')]
        for variant in variants:
            with self.subTest(variant=variant):
                parsed = designs.load(variant, scenario_reader=plans.scenario_reader)
                self.assertEqual(designs.fingerprints(parsed), designs.fingerprints(design))
                status = designs.approval_status(parsed, [approved], changed_paths=[])
                self.assertTrue(status['fully_approved'], status)
                self.assertEqual(status['stale'], [])

    def test_r1_one_character_changes_only_its_leaf_section(self):
        before = designs.load(designs.render(example()), scenario_reader=plans.scenario_reader)
        raw = designs.render(before)
        start = raw.index('<!-- tw-section id=T1 ')
        edited = raw[:start] + raw[start:].replace('Required behavior.', 'Required behaviour.', 1)
        after = designs.load(edited, scenario_reader=plans.scenario_reader)
        left, right = designs.fingerprints(before)['sections'], designs.fingerprints(after)['sections']
        self.assertEqual([key for key in left if left[key] != right[key]], ['T1'])

    def test_r1_normalizes_only_outer_blank_lines_and_line_tails(self):
        value = example()
        original = '\n \t\n首段  保留行内空格  \t\n\n\n```python  \n    call(1,  2) \t\n\n```\t\n尾段\t\n \n'
        expected = '首段  保留行内空格\n\n\n```python\n    call(1,  2)\n\n```\n尾段'
        value['sections'][1]['body'] = original
        saved = copy.deepcopy(value)
        raw = designs.render(value)
        self.assertEqual(value, saved, 'render must not mutate its input')
        self.assertIn(expected, raw)
        self.assertEqual(designs.load(raw, scenario_reader=plans.scenario_reader)['sections'][1]['body'], expected)

    def test_r1_render_separates_headings_body_labels_and_tables(self):
        raw = designs.render(example())
        for title in ('scope-global', 'api-1', 'api-2', 'A1', 'A2', 'T1', 'T2'):
            self.assertIn('\n\n## ' + title + '\n<!-- tw-section ', raw)
        for label in ('需求级验收', '场景', '验收'):
            self.assertIn('Required behavior.\n\n- ' + label + '：', raw)
        self.assertIn('- 需求级验收：A1、A2\n\n| 仓库', raw)
        self.assertEqual(designs.render(designs.load(raw, scenario_reader=plans.scenario_reader)), raw)

    def test_r1_template_matches_rendered_layout(self):
        path = Path(__file__).resolve().parents[1] / 'skills/team-workflow/templates/design.md'
        filled = path.read_text().replace('__REPLACE__', '实际填写内容')
        import tempfile
        import shutil
        import design_files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'docs/sop/scenarios.yaml'
            target.parent.mkdir(parents=True)
            shutil.copyfile(path.with_name('scenarios.yaml'), target)
            (root / '.tw').mkdir()
            (root / '.tw/config.json').write_text(path.with_name('config.json').read_text())
            reader = design_files.scenario_reader(root)
            self.assertEqual(designs.render(designs.load(filled, scenario_reader=reader)), filled)

    def test_r2_single_labels_keep_semicolons_and_literal_quotes(self):
        value = example()
        # 原内联标量的文字核对迁到场景文件的读取边界。
        import json
        import scenario_yaml
        scenario = {'actor': '"中文角色"', 'initial_state': ['状态甲；状态乙、参数 [a] = {b}'],
                    'expected': ['返回 "正确"；数据保持原样']}
        raw = json.dumps(scenario, ensure_ascii=False)
        self.assertEqual(scenario_yaml.loads(raw).value, scenario)
        self.assertEqual(scenario_yaml.loads(raw, '.json').value, scenario)

    def test_r2_multi_value_quotes_only_its_actual_delimiter(self):
        value = example()
        data = value['sections'][3]['data']
        data['verification']['cases'] = ['普通步骤、仍是一项', '执行甲；再执行乙', 'text [a] {b}', '"字面引号"']
        data['checks'] = ['unit', 'suite；备注', 'one、two']
        raw = designs.render(value)
        self.assertIn('用例 "普通步骤、仍是一项"、"执行甲；再执行乙"、text [a] {b}、"字面引号"', raw)
        self.assertIn('- 检查：unit、suite；备注、"one、two"\n', raw)
        self.assertEqual(designs.load(raw, scenario_reader=plans.scenario_reader), value)

    def test_r2_quotes_in_separate_items_cannot_capture_delimiters(self):
        for values in (['a"b', 'c"d'], ['foo "bar', 'second "baz'], ['"unclosed', 'next'], ['"quoted"tail', 'last']):
            with self.subTest(values=values):
                value = example()
                data = value['sections'][3]['data']
                data['verification']['cases'] = values
                data['verification']['cases'] = values
                data['verification']['substitutes'] = ['；替身 "值"']
                self.assertEqual(designs.load(designs.render(value), scenario_reader=plans.scenario_reader), value)

    def test_r2_multiple_sources_keep_quoted_record_separators(self):
        value = example()
        value['sections'][3]['data']['sources'] = [
            {'ref': '需求 / 片段；补充', 'version': 'v2', 'confirmed_by': '甲 / 乙'},
            {'ref': '第二份原文', 'version': '"v3"', 'confirmed_by': '人；四'}]
        self.assertEqual(designs.load(designs.render(value), scenario_reader=plans.scenario_reader), value)

    def test_r2_compound_labels_quote_only_real_separators(self):
        value = example()
        data = value['sections'][3]['data']
        data['sources'] = [{'ref': 'docs/"quoted".md', 'version': 'v[2]', 'confirmed_by': '用户 "甲"'}]
        data['verification']['substitutes'] = ['fixture [x] "value"']
        raw = designs.render(value)
        self.assertIn('- 依据：位置 docs/"quoted".md；版本 v[2]；确认人 用户 "甲"\n', raw)
        self.assertIn('；替身 fixture [x] "value"\n', raw)
        self.assertEqual(designs.load(raw, scenario_reader=plans.scenario_reader), value)
        data['sources'][0].update(ref='"字面引号"', version='&amp;', confirmed_by='甲；乙 / 丙')
        data['verification']['substitutes'] = ['"字面引号"']
        self.assertEqual(designs.load(designs.render(value), scenario_reader=plans.scenario_reader), value)

    def test_r2_prose_commas_cannot_start_list_quotes(self):
        for kind in ('sources', 'substitutes', 'lists'):
            with self.subTest(kind=kind):
                value = example()
                data = value['sections'][3]['data']
                if kind == 'sources':
                    data['sources'] = [{'ref': 'a、"unclosed', 'version': '；start', 'confirmed_by': 'user'}]
                elif kind == 'lists':
                    rows = ['"unclosed', '；start', '["x"]', 'first；second']
                    data['verification']['cases'] = rows
                    data['verification']['substitutes'] = rows[1:]
                else:
                    data['verification']['cases'] = ['a、"unclosed']
                    data['verification']['substitutes'] = ['；start']
                self.assertEqual(designs.load(designs.render(value), scenario_reader=plans.scenario_reader), value)

    def test_r2_special_values_and_nested_lists_roundtrip(self):
        value = example()
        data = value['sections'][3]['data']
        value['sections'][3]['body'] = '第一行\n第二行 &amp; "引号"；原样'
        data['verification']['cases'] = ['无', '["literal"]', '"literal"', ' ]first ', '&amp;', 'line\nbreak', 'a"b', ']first']
        data['verification']['substitutes'] = ['call；then', 'api、v2', 'call [x]']
        self.assertEqual(designs.load(designs.render(value), scenario_reader=plans.scenario_reader), value)


if __name__ == '__main__':
    unittest.main()
