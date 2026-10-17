"""经命令入口核对场景格式、正反向规则与内容指纹。"""
import copy
import contextlib
import io
import json
import unittest
import test_workflow as fixtures
from test_workflow import write_config
from test_scenario_entries import ENTRY
import workflow


def scenario_file():
    base = {'id': 'S-P', 'polarity': 'positive', 'title': '得到结果', 'actor': '成员',
            'priority': 'P0', 'verify': 'cli', 'initial_state': ['空目录'], 'steps': ['运行命令'],
            'expected': ['结果为三'], 'forbidden_effects': []}
    return {'metadata': {'requirement': '合成需求', 'batch': '合成批次', 'version': 1, 'owner': '甲',
                         'sources': [{'ref': '合成依据', 'version': '1', 'confirmed_by': '乙'}]},
            'sops': [{'id': 'S', 'title': '节点', 'actor': '成员', 'entry': '命令',
                      'scenarios': [base, {**copy.deepcopy(base), 'id': 'S-N', 'polarity': 'negative',
                                          'negative_type': 'invalid-input', 'title': '拒绝错误参数'}]}]}


class ScenarioCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def setUp(self):
        fixtures.WorkflowCases.setUp(self)
        self.profile['acceptance_entries'] = {'cli': ENTRY}
        write_config(self.root, self.profile)

    def call(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['--root', str(self.root), *map(str, args)])
        return code, json.loads(output.getvalue())

    def save(self, value, name='scenarios.json'):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        return path

    def test_check_fingerprints_track_only_declared_content(self):
        value = scenario_file()
        path = self.save(value)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        code, first = self.call('scenarios', 'check', path)
        self.assertEqual(code, 0, first)
        self.assertEqual(set(first['fingerprints']), {'S-P', 'S-N'})
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        value['sops'][0]['scenarios'][0]['title'] = '新标题'
        _, same = self.call('scenarios', 'check', self.save(value))
        self.assertEqual(first['fingerprints'], same['fingerprints'])
        value['sops'][0]['scenarios'][0]['expected'] = ['结果为四']
        _, changed = self.call('scenarios', 'check', self.save(value))
        self.assertNotEqual(first['fingerprints']['S-P'], changed['fingerprints']['S-P'])
        self.assertEqual(first['fingerprints']['S-N'], changed['fingerprints']['S-N'])

    def test_missing_negative_and_exemption(self):
        value = scenario_file()
        value['sops'][0]['scenarios'].pop()
        path = self.save(value)
        before = path.read_bytes()
        code, result = self.call('scenarios', 'check', path)
        self.assertEqual((code, result['error_code']), (1, 'scenario-file-invalid'))
        self.assertIn('S', result['problem'])
        self.assertTrue(all(row['line'] > 0 for row in result['errors']))
        self.assertEqual(path.read_bytes(), before)
        value['sops'][0]['negative_exempt'] = '本节点由另一组反向场景覆盖'
        self.assertEqual(self.call('scenarios', 'check', self.save(value))[0], 0)

    def test_undeclared_entry_names_scenario_value_and_source_line(self):
        value = scenario_file()
        value['sops'][0]['scenarios'][0]['verify'] = 'web'
        path = self.save(value)
        code, result = self.call('scenarios', 'check', path)
        self.assertEqual((code, result['error_code']), (1, 'scenario-file-invalid'))
        error = next(row for row in result['errors'] if 'verify' in row['problem'])
        self.assertEqual(error['problem'], '场景 S-P 的 verify 填写 acceptance_entries 中声明的入口名，当前为 web')
        self.assertEqual(error['line'], next(i for i, line in enumerate(path.read_text().splitlines(), 1) if '"verify": "web"' in line))

    def test_all_errors_include_lines_and_strict_fields(self):
        value = scenario_file()
        del value['metadata']['sources']
        negative = value['sops'][0]['scenarios'][1]
        del negative['negative_type']
        negative.update(verify='missing', layer='local', id='S-P')
        code, result = self.call('scenarios', 'check', self.save(value))
        self.assertEqual((code, result['error_code']), (1, 'scenario-file-invalid'))
        for name in ('sources', 'negative_type', 'verify', 'layer', 'S-P'):
            self.assertIn(name, result['problem'])
        self.assertGreaterEqual(len(result['errors']), 5)
        self.assertTrue(all(row['line'] > 0 for row in result['errors']))

    def test_regression_shapes_and_registered_check(self):
        value = scenario_file()
        target = value['sops'][0]['scenarios'][0]
        for regression in ({'manual': '观察终端', 'owner': '乙', 'trigger': '发布时'}, {'pending': 'ISSUE-1'}):
            target['regression'] = regression
            self.assertEqual(self.call('scenarios', 'check', self.save(value))[0], 0)
        for regression in ({'check': 'missing', 'cases': ['C1']}, {'pending': ''},
                           {'manual': '原因', 'owner': '乙'}, {'check': 'unit', 'cases': []}):
            target['regression'] = regression
            self.assertEqual(self.call('scenarios', 'check', self.save(value))[1]['error_code'], 'scenario-file-invalid')

    def test_regression_command_check_is_rejected_at_its_line(self):
        fixtures.WorkflowCases.check(self, "print('ok')")
        write_config(self.root, self.profile)
        value = scenario_file()
        value['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['C1']}
        path = self.save(value)
        code, result = self.call('scenarios', 'check', path)
        self.assertEqual((code, result.get('error_code')), (1, 'scenario-file-invalid'), result)
        error = next(row for row in result['errors'] if '逐项用例报告' in row['problem'])
        self.assertEqual(error['problem'], 'regression 指向的检查需要逐项用例报告（junit 或 go-json），当前 unit 为 command')
        self.assertEqual(error['line'], next(i for i, line in enumerate(path.read_text().splitlines(), 1)
                                             if '"check": "unit"' in line))

    def test_malformed_values_and_negative_type_enum_are_input_errors(self):
        for field, bad in (('negative_type', []), ('negative_type', 'unknown'), ('verify', []), ('id', {}), ('steps', '一行')):
            value = scenario_file()
            value['sops'][0]['scenarios'][0][field] = bad
            code, result = self.call('scenarios', 'check', self.save(value))
            self.assertEqual((code, result.get('error_code')), (1, 'scenario-file-invalid'), result)

    def test_core_content_arrays_are_nonempty_for_both_polarities(self):
        for ordinal, polarity in enumerate(('positive', 'negative')):
            for field in ('initial_state', 'steps', 'expected'):
                with self.subTest(polarity=polarity, field=field):
                    value = scenario_file()
                    value['sops'][0]['scenarios'][ordinal][field] = []
                    code, result = self.call('scenarios', 'check', self.save(value))
                    self.assertEqual((code, result.get('error_code')), (1, 'scenario-file-invalid'), result)
                    self.assertTrue(any(field in error['problem'] and error['line'] > 0 for error in result['errors']))

    def test_forbidden_effects_allows_an_empty_array(self):
        value = scenario_file()
        for row in value['sops'][0]['scenarios']:
            row['forbidden_effects'] = []
        code, result = self.call('scenarios', 'check', self.save(value))
        self.assertEqual(code, 0, result)


class ScenarioParserCases(unittest.TestCase):
    def test_locations_accumulate_at_all_three_levels(self):
        args = workflow.parser().parse_args(['--repository', 'a=/a', 'scenarios', '--repository', 'b=/b',
            'check', '--repository', 'c=/c', '--root', '/project', 'scenarios.yaml'])
        self.assertEqual(args.repository, ['a=/a', 'b=/b', 'c=/c'])
        self.assertEqual(str(args.root), '/project')
