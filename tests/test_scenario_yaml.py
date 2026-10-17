"""场景与用例文件使用的 YAML 子集，全部为合成输入。"""
import json
import unittest
from test_workflow import Invalid


class ScenarioYamlCases(unittest.TestCase):
    def test_supported_values_preserve_text_and_locations(self):
        from scenario_yaml import loads
        raw = '''# 合成样本
metadata:
  version: 2 # 版本
  title: 中文：括号（甲）、乙；丙
cases:
  - id: 'TC_''甲'
    title: "双引号\\\"、斜线\\\\、换行\\n"
    values: [1, 'x,y', "#文字", {k: v, n: -2}] # 注释
    detail:
      nested: [甲, 乙]
      empty: []
'''
        parsed = loads(raw)
        self.assertEqual(parsed.value, {'metadata': {'version': 2, 'title': '中文：括号（甲）、乙；丙'},
            'cases': [{'id': "TC_'甲", 'title': '双引号"、斜线\\、换行\n',
                       'values': [1, 'x,y', '#文字', {'k': 'v', 'n': -2}],
                       'detail': {'nested': ['甲', '乙'], 'empty': []}}]})
        self.assertEqual(parsed.line(('cases', 0, 'values', 3, 'n')), 8)

    def test_unsupported_syntax_and_duplicate_keys_report_source_line(self):
        from scenario_yaml import loads
        for expression in ('x: |', 'x: >', 'x: &a value', 'x: *a', 'x: !tag value', '---',
                           '\tx: value', 'x: a\n  continuation', 'x: 1\nx: 2', 'x: {a: 1, a: 2}'):
            with self.subTest(expression=expression), self.assertRaisesRegex(Invalid, r'第 [2-4] 行'):
                loads('# 合成样本\n' + expression + '\n')

    def test_json_preserves_all_json_values(self):
        from scenario_yaml import loads
        value = {'cases': [{'id': '合成', 'title': 'JSON', 'flag': True, 'nothing': None, 'amount': 1.5}]}
        parsed = loads(json.dumps(value, ensure_ascii=False, indent=2), suffix='.json')
        self.assertEqual(parsed.value, value)
        self.assertEqual(parsed.line(('cases', 0, 'title')), 5)

    def test_plain_punctuation_is_text_inside_a_scalar(self):
        from scenario_yaml import loads
        self.assertEqual(loads('title: Returns & Exchanges\nvalue: 2 * 3 ! 提示\n').value,
                         {'title': 'Returns & Exchanges', 'value': '2 * 3 ! 提示'})

    def test_block_sequences_accept_indentless_values_and_variable_item_spacing(self):
        from scenario_yaml import loads
        self.assertEqual(loads('cases:\n-   id: C1\n    title: 合成\n    values:\n    - 甲\n    - 乙\n').value,
                         {'cases': [{'id': 'C1', 'title': '合成', 'values': ['甲', '乙']}]})

    def test_flow_collections_can_span_lines_with_comments(self):
        from scenario_yaml import loads
        raw = 'cases: [ # 集合\n  {id: C1,\n   title: 合成}, # 注释\n  {id: C2, title: 第二条}\n]\n'
        parsed = loads(raw)
        self.assertEqual(parsed.value, {'cases': [{'id': 'C1', 'title': '合成'}, {'id': 'C2', 'title': '第二条'}]})
        self.assertEqual(parsed.line(('cases', 0, 'title')), 3)

    def test_multiline_plain_scalars_in_flow_are_rejected(self):
        from scenario_yaml import loads
        with self.assertRaisesRegex(Invalid, '第 2 行'):
            loads('values: [one\n  continued]\n')

    def test_document_markers_inside_values_are_plain_text(self):
        from scenario_yaml import loads
        self.assertEqual(loads('value: ---\nother: ...\nvalues: [---, ...]\n').value,
                         {'value': '---', 'other': '...', 'values': ['---', '...']})
