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

    def test_import_preserves_fields_and_later_import_wins(self):
        self.prepared()
        first = [{'id': 'C1', 'title': '中文用例', 'extra': {'steps': [1, '甲'], 'flag': True}},
                 {'id': 'C2', 'title': '第二条', 'priority': 'P0'}]
        code, result = self.import_cases(first)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['imported'], result['total'], result['added'], result['updated']), (2, 2, ['C1', 'C2'], []))
        ref = self.current()['case_imports'][0]
        self.assertEqual(read(self.root / ref['path'])['test_cases'], first)
        changed = [{'id': 'C1', 'title': '修订', 'extra': ['原样']}, {'id': 'C3', 'title': '新增'}]
        code, result = self.import_cases(changed)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['total'], result['added'], result['updated']), (3, ['C3'], ['C1']))
        import scenarios
        self.assertEqual(list(scenarios.imported_cases(self.root, self.current()).values()), [changed[0], first[1], changed[1]])

    def test_invalid_cases_report_lines_and_keep_current_materials(self):
        self.prepared()
        before = self.current_path().read_bytes()
        for rows in ([{'id': 'C1', 'title': ''}], [{'id': 'C1', 'title': '甲'}, {'id': 'C1', 'title': '乙'}], [{}]):
            code, result = self.import_cases(rows)
            self.assertEqual((code, result['error_code']), (1, 'case-list-invalid'))
            self.assertTrue(all(row['line'] > 0 for row in result['errors']))
            self.assertEqual(before, self.current_path().read_bytes())

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
        self.assertEqual(check(bad)[1]['error_code'], 'scenario-coverage-incomplete')
        bad = copy.deepcopy(pairs)
        bad['disposed'][0]['confirmed_by'] = ''
        self.assertEqual(check(bad)[0], 1)
        bad = copy.deepcopy(pairs)
        bad['disposed'].append(copy.deepcopy(bad['disposed'][0]))
        self.assertEqual(check(bad)[0], 1)
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
