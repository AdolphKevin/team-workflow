"""真实命令导入用例，核对累积集合与配对材料。"""
import copy
import json
import unittest
import test_current_materials as fixtures
from common import read


class CaseImportCases(unittest.TestCase):
    base = fixtures.CurrentMaterials
    setUp, git, check, setup_task, write, name, command, prepared, current, current_path = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.command,
        base.prepared, base.current, base.current_path)

    def cases(self, rows, name='cases.json'):
        path = self.root / name
        path.write_text(json.dumps({'test_cases': rows}, ensure_ascii=False, indent=2))
        return path

    def import_cases(self, rows):
        return self.command('scenarios', 'import-cases', '--task', self.task['id'], str(self.cases(rows)))

    def pair_cases(self, covered):
        path = self.root / '.tw/local/pairs.json'
        path.write_text(json.dumps({'covered': covered, 'conflict': [], 'disposed': []}, ensure_ascii=False, indent=2))
        return self.command('scenarios', 'coverage', '--task', self.task['id'], '--pairs', str(path))

    def test_coverage_accepts_checks_and_counts_mixed_cases_without_running(self):
        self.prepared()
        from test_workflow import write_config
        for report_format in ('junit', 'go-json'):
            with self.subTest(format=report_format):
                self.check("raise RuntimeError('coverage must not run checks')", format=report_format)
                if report_format == 'junit':
                    self.profile['checks']['unit']['report'] = '{output}/results.xml'
                    self.profile['checks']['unit']['argv'].append('{output}/results.xml')
                write_config(self.root, self.profile)
                self.assertEqual(self.import_cases([{'id': 'C1', 'title': '格式用例'}])[0], 0)
                check_pair = {'case': 'C1', 'checks': [{'check': 'unit', 'cases': ['chat.Message::test_trim']}], 'note': ''}
                code, result = self.pair_cases([check_pair])
                self.assertEqual(code, 0, result)
                self.assertEqual((result['covered_by_scenarios'], result['covered_by_checks']), (0, 1))
        self.assertEqual(self.import_cases([{'id': 'C' + str(i), 'title': '用例'} for i in range(1, 13)])[0], 0)
        covered = [{'case': 'C' + str(i), 'scenarios': ['SYNTH-01-P01'], 'note': ''} for i in range(1, 9)]
        covered += [{**check_pair, 'case': 'C' + str(i)} for i in range(9, 13)]
        code, result = self.pair_cases(covered)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['total'], result['covered'], result['disposed']), (12, 12, 0))
        self.assertEqual((result['covered_by_scenarios'], result['covered_by_checks']), (8, 4))
        covered[0]['checks'] = check_pair['checks']
        code, result = self.pair_cases(covered)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['covered'], result['covered_by_scenarios'], result['covered_by_checks']), (12, 8, 5))
        self.assertEqual(self.current()['runs'], [])

    def test_import_preserves_fields_and_later_import_wins(self):
        self.prepared()
        first = [{'id': 'C1', 'title': '中文用例', 'extra': {'steps': [1, '甲'], 'flag': True}},
                 {'id': 'C2', 'title': '第二条', 'priority': 'P0'}, {'id': 'C3', 'title': '第三条'}]
        code, result = self.import_cases(first)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['imported'], result['total'], result['added'], result['updated']), (3, 3, ['C1', 'C2', 'C3'], []))
        self.assertEqual(json.loads((self.root / 'cases.json').read_text())['test_cases'], first)
        ref = self.current()['case_imports'][0]
        self.assertEqual(read(self.root / ref['path'])['test_cases'], first)
        changed = [{'id': 'C1', 'title': '修订', 'extra': ['原样']}, {'id': 'C4', 'title': '新增'}]
        code, result = self.import_cases(changed)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['total'], result['added'], result['updated']), (4, ['C4'], ['C1']))
        self.assertEqual(json.loads((self.root / 'cases.json').read_text())['test_cases'], changed)
        import scenarios
        self.assertEqual(list(scenarios.imported_cases(self.root, self.current()).values()), [changed[0], first[1], first[2], changed[1]])

    def test_coverage_rejects_invalid_checks_with_locations(self):
        self.prepared()
        from test_workflow import write_config
        self.check("print('unused')", format='go-json')
        self.profile['checks']['command'] = {**self.profile['checks']['unit'], 'format': 'command'}
        write_config(self.root, self.profile)
        self.assertEqual(self.import_cases([{'id': 'C1', 'title': '格式用例'}])[0], 0)
        good = {'check': 'unit', 'cases': ['chat.Message::test_trim']}
        variants = [
            ({'checks': [{**good, 'check': 'missing'}]}, 'regression.check 引用 checks 已登记的检查', '"check": "missing"'),
            ({'checks': [{**good, 'check': 'command'}]}, 'regression 指向的检查需要逐项用例报告（junit 或 go-json），当前 command 为 command', '"check": "command"'),
            ({'checks': [{**good, 'cases': []}]}, 'cases 应为非空数组', '"cases": []'),
            ({'checks': []}, 'checks 应为非空数组', '"checks": []'),
            ({'checks': [{**good, 'cases': [' ']}]}, '应为非空字符串', '" "'),
            ({'checks': [None]}, '应为对象', 'null'),
            ({'checks': [{'check': 'unit'}]}, '缺少字段：cases', '"checks"'),
            ({'checks': [{**good, 'extra': True}]}, '格式外字段：extra', '"extra"'),
            ({'scenarios': []}, 'scenarios 应为非空数组', '"scenarios": []'),
            ({}, 'scenarios 或 checks', '"case": "C1"'),
        ]
        before = self.current_path().read_bytes()
        for fields, message, token in variants:
            with self.subTest(fields=fields):
                code, result = self.pair_cases([{'case': 'C1', 'note': '', **fields}])
                self.assertEqual((code, result.get('error_code')), (1, 'scenario-coverage-incomplete'), result)
                error = next((row for row in result['errors'] if message in row['problem']), None)
                self.assertIsNotNone(error, result)
                self.assertGreater(error['line'], 0)
                if token not in ('"case": "C1"', '"checks"'):
                    lines = (self.root / '.tw/local/pairs.json').read_text().splitlines()
                    self.assertEqual(error['line'], next(i for i, line in enumerate(lines, 1) if token in line))
                self.assertEqual(self.current_path().read_bytes(), before)

    def test_invalid_cases_report_lines_and_keep_current_materials(self):
        self.prepared()
        before = self.current_path().read_bytes()
        snapshots = sorted((self.root / '.tw/local/tasks').rglob('*'))
        for rows in ([{'id': 'C1', 'title': ''}], [{'id': 'C1', 'title': '甲'}, {'id': 'C1', 'title': '乙'}], [{}]):
            code, result = self.import_cases(rows)
            self.assertEqual((code, result['error_code']), (1, 'case-list-invalid'))
            self.assertTrue(all(row['line'] > 0 for row in result['errors']))
            self.assertEqual(before, self.current_path().read_bytes())
            self.assertEqual(snapshots, sorted((self.root / '.tw/local/tasks').rglob('*')))

    def test_coverage_reports_missing_conflict_and_new_cases(self):
        self.prepared()
        self.assertEqual(self.import_cases([{'id': 'C1', 'title': '甲'}, {'id': 'C2', 'title': '乙'}, {'id': 'C3', 'title': '丙'}])[0], 0)
        path = self.root / 'pairs.json'
        def check(value):
            path.write_text(json.dumps(value, ensure_ascii=False))
            return self.command('scenarios', 'coverage', '--task', self.task['id'], '--pairs', str(path))
        pairs = {'covered': [], 'conflict': [{'case': 'C1', 'scenarios': ['SYNTH-01-P01'], 'note': '预期有分歧'}], 'disposed': []}
        code, result = check(pairs)
        self.assertEqual((code, result['error_code']), (1, 'scenario-coverage-incomplete'))
        self.assertNotIn('第 1 行', result['problem'])
        self.assertTrue(all('line' not in row for row in result['errors']))
        self.assertEqual(result['cases'], [{'case': 'C1', 'category': 'conflict'}, {'case': 'C2', 'category': 'unclassified'}, {'case': 'C3', 'category': 'unclassified'}])
        self.assertNotIn('case_coverage', self.current())
        pairs['covered'] = [{**pairs['conflict'][0], 'note': ''}]
        pairs['conflict'] = []
        pairs['disposed'] = [{'case': key, 'state': 'deferred', 'reason': '延期', 'confirmed_by': '测试同事'} for key in ('C2', 'C3')]
        self.assertEqual(check(pairs)[0], 0)
        ref = self.current()['case_coverage']
        self.assertEqual(read(self.root / ref['path']), pairs)
        self.assertEqual(self.import_cases([{'id': 'C4', 'title': '丁'}, {'id': 'C5', 'title': '戊'}])[0], 0)
        code, result = check(pairs)
        self.assertEqual(result['cases'], [{'case': 'C4', 'category': 'unclassified'}, {'case': 'C5', 'category': 'unclassified'}])
        bad = copy.deepcopy(pairs)
        bad['covered'][0]['scenarios'] = ['missing']
        malformed = check(bad)[1]
        self.assertEqual(malformed['error_code'], 'scenario-coverage-incomplete')
        self.assertTrue(any(row.get('line', 0) > 0 for row in malformed['errors']))
        bad = copy.deepcopy(pairs)
        bad['disposed'][0]['confirmed_by'] = ''
        self.assertEqual(check(bad)[0], 1)
        bad = copy.deepcopy(pairs)
        bad['disposed'].append(copy.deepcopy(bad['disposed'][0]))
        duplicate = check(bad)[1]
        self.assertTrue(all('line' not in row for row in duplicate['errors']))
        self.assertIn('duplicate', duplicate['problem'])
        bad = copy.deepcopy(pairs)
        bad['covered'].append({'case': 'unknown', 'scenarios': ['SYNTH-01-P01'], 'note': ''})
        self.assertEqual(check(bad)[0], 1)

    def test_prepared_local_design_reloads_scenario_content(self):
        self.prepared()
        import design_files
        import designs
        snapshot = self.root / self.current()['design']['path']
        before = design_files.read(snapshot)
        path = self.root / before['sections'][1]['data']['scenarios'][0]['path']
        value = read(path)
        value['sops'][0]['scenarios'][0]['expected'] = ['修订后的业务结果']
        path.write_text(json.dumps(value, ensure_ascii=False))
        after = design_files.read(snapshot)
        self.assertNotEqual(designs.fingerprints(before)['sections']['A1'], designs.fingerprints(after)['sections']['A1'])

    def test_coverage_preserves_auxiliary_fields(self):
        self.prepared()
        self.assertEqual(self.import_cases([{'id': 'C1', 'title': '合成'}])[0], 0)
        pairs = {'metadata': {'reviewer': '测试同事'}, 'covered': [], 'conflict': [],
                 'disposed': [{'case': 'C1', 'state': 'deferred', 'reason': '延期', 'confirmed_by': '乙', 'link': 'ISSUE-2'}]}
        path = self.root / 'pairs-extra.json'
        path.write_text(json.dumps(pairs, ensure_ascii=False))
        code, result = self.command('scenarios', 'coverage', '--task', self.task['id'], '--pairs', str(path))
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / self.current()['case_coverage']['path']), pairs)
