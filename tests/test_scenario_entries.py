"""项目声明验收入口，错误按代码给出下一步。"""
import copy
import unittest
import test_workflow as fixtures
from test_workflow import write_config, Invalid
from common import load_profile
import repairs
import workflow

ENTRY = {'surface': 'cli', 'operate': '运行命令', 'observe': ['输出', '文件'],
         'evidence': ['原始输出'], 'isolation': '临时目录'}


class AcceptanceEntryCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    def test_optional_entries_and_account_references(self):
        import json
        target = self.root / '.tw/config.json'
        config = json.loads(target.read_text())
        config.pop('acceptance_entries', None)
        target.write_text(json.dumps(config))
        self.assertEqual(load_profile(self.root).get('acceptance_entries'), {})
        self.profile['acceptance_entries'] = {'cli': copy.deepcopy(ENTRY)}
        write_config(self.root, self.profile)
        self.assertEqual(load_profile(self.root)['acceptance_entries'], {'cli': ENTRY})

    def test_invalid_entries_have_dedicated_code(self):
        bad = [None, [], {'cli': {}}, {'cli': {**ENTRY, 'observe': []}},
               {'cli': {**ENTRY, 'evidence': ['']}}, {'cli': {**ENTRY, 'accounts': ['missing']}},
               {'cli': {**ENTRY, 'address_env': 'http://value'}}, {'cli': {**ENTRY, 'surface': ''}}]
        for value in bad:
            with self.subTest(value=value):
                import json
                target = self.root / '.tw/config.json'
                config = json.loads(target.read_text())
                config['acceptance_entries'] = value
                target.write_text(json.dumps(config))
                with self.assertRaises(Invalid) as caught:
                    load_profile(self.root)
                self.assertEqual(caught.exception.error_code, 'acceptance-entry-invalid')

    def test_repair_selection_uses_only_error_code(self):
        from error_codes import Code
        args = workflow.parser().parse_args(['schema'])
        for name, expected in [('SCENARIO_FILE', 'scenarios check'), ('CASE_LIST', 'import-cases'),
                               ('SCENARIO_COVERAGE', 'coverage'), ('ACCEPTANCE_ENTRY', '.tw/config.json')]:
            code = getattr(Code, name)
            self.assertIn(expected, repairs.action(args, '任意文字', code))
            self.assertEqual(repairs.action(args, '甲', code), repairs.action(args, '乙', code))

    def test_invalid_accounts_keep_the_existing_account_error(self):
        import json
        target = self.root / '.tw/config.json'
        config = json.loads(target.read_text())
        for accounts in (None, [{'id': []}]):
            config['accounts'] = accounts
            target.write_text(json.dumps(config))
            with self.assertRaises(Invalid) as caught:
                load_profile(self.root)
            self.assertEqual(caught.exception.error_code, 'invalid-or-incomplete-input')

    def test_invalid_config_root_keeps_the_existing_input_error(self):
        import json
        target = self.root / '.tw/config.json'
        for value in ([], None, 1):
            target.write_text(json.dumps(value))
            with self.assertRaises(Invalid) as caught:
                load_profile(self.root)
            self.assertEqual(caught.exception.error_code, 'invalid-or-incomplete-input')
