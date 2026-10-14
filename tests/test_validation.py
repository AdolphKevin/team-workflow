"""Execute checks against real temporary Git trees; verify content and environment reuse."""
import copy
import sys
import unittest

import test_workflow as fixtures
from common import Invalid
import validation


class ContentValidation(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def setup_task(self):
        self.check("import app; assert app.add(1,2)==3")

    def run_batch(self, tasks=None):
        return validation.run_batch(self.root, self.profile, tasks or [self.task])

    def test_knowledge_commit_and_index_do_not_expire_execution(self):
        self.setup_task()
        path, record = self.run_batch()
        (self.root / '.tw/overview.md').write_text((self.root / '.tw/overview.md').read_text() + '\n实际核对后的说明。\n')
        self.git('add', '.tw')
        self.git('commit', '-qm', 'knowledge only')
        self.assertEqual(validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])['checks'], ['unit'])
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        path, record = self.run_batch()
        self.git('add', 'app.py')
        validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_five_tasks_execute_seven_checks_once(self):
        self.setup_task()
        base = self.profile['checks'].pop('unit')
        self.profile['required_checks']['code'] = []
        for i in range(7):
            row = copy.deepcopy(base)
            row['argv'] = [sys.executable, '-c', f"from pathlib import Path; p=Path(r'{{output}}/counter'); p.write_text('executed-{i}')"]
            row['artifacts'] = ['{output}/counter']
            self.profile['checks'][f'check-{i}'] = row
        tasks = []
        for i, checks in enumerate([[0, 1, 2], [1, 2, 3], [3, 4, 5], [0, 5, 6], [4, 6]]):
            task = copy.deepcopy(self.task)
            task['id'] = f'TASK-{i}'
            task['acceptance'][0]['checks'] = [f'check-{j}' for j in checks]
            tasks.append(task)
        path, record = self.run_batch(tasks)
        self.assertEqual(len(record['results']), 7)
        self.assertEqual(len(list(path.parent.rglob('counter'))), 7)
        for task in tasks:
            result = validation.verify_runs(self.root, self.profile, task, [str(path.relative_to(self.root))])
            self.assertEqual(set(result['checks']), set(task['acceptance'][0]['checks']))

    def test_source_check_and_environment_changes_expire_only_affected_results(self):
        self.setup_task()
        path, _ = self.run_batch()
        names = [str(path.relative_to(self.root))]
        self.profile['checks']['unrelated'] = copy.deepcopy(self.profile['checks']['unit'])
        validation.verify_runs(self.root, self.profile, self.task, names)
        # Evaluation settings do not change what was executed.
        self.profile['checks']['unit']['timeout'] += 1
        self.profile['checks']['unit']['purpose'] = 'Reworded purpose'
        validation.verify_runs(self.root, self.profile, self.task, names)
        argv = self.profile['checks']['unit']['argv']
        self.profile['checks']['unit']['argv'] = argv + ['extra']
        with self.assertRaisesRegex(Invalid, 'definition'):
            validation.verify_runs(self.root, self.profile, self.task, names)
        self.profile['checks']['unit']['argv'] = argv
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, names)

    def junit(self, key, cases, required):
        script = ('from pathlib import Path\n'
                  "rows = ''.join(f'<testcase classname=\"pkg\" name=\"{n}\"/>' for n in %r)\n"
                  "Path(r'{output}/report.xml').write_text(f'<testsuite tests=\"%d\">{rows}</testsuite>')" % (cases, len(cases)))
        row = copy.deepcopy(self.profile['checks']['unit'])
        row.update(argv=[sys.executable, '-c', script], format='junit', report='{output}/report.xml', required_cases=required)
        self.profile['checks'][key] = row
        return row

    def test_fixing_a_required_case_name_needs_no_rerun(self):
        self.setup_task()
        self.junit('unit', ['TestAdd', 'TestSub'], ['TestAdd'])  # registration typo: missing classname prefix
        path, record = self.run_batch()
        self.assertEqual(record['results'][0]['status'], 'incomplete')
        names = [str(path.relative_to(self.root))]
        with self.assertRaisesRegex(Invalid, 'Required case missing or not passed: TestAdd; the report has 2 cases, e.g. pkg::TestAdd. Check the registered name'):
            validation.verify_runs(self.root, self.profile, self.task, names)
        self.profile['checks']['unit']['required_cases'] = ['pkg::TestAdd']
        result = validation.verify_runs(self.root, self.profile, self.task, names)
        row = result['results']['unit']
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['evaluation']['original_status'], 'incomplete')
        self.assertEqual(set(row['cases']), {'pkg::TestAdd', 'pkg::TestSub'})
        # A required case that never ran still cannot pass.
        self.profile['checks']['unit']['required_cases'] = ['pkg::TestMul']
        with self.assertRaisesRegex(Invalid, 'TestMul'):
            validation.verify_runs(self.root, self.profile, self.task, names)

    def test_shared_schema6_record_reuses_current_case_evaluation(self):
        self.setup_task()
        check = self.junit('unit', ['TestAdd', 'TestSub'], ['TestAdd'])
        path, record = self.run_batch()
        self.assertEqual(record['results'][0]['status'], 'incomplete')
        original = copy.deepcopy(record)
        check['required_cases'] = ['pkg::TestAdd']
        self.assertEqual(validation.inspect_record(self.root, self.profile, record), {'unit'})
        from common import artifact
        acceptance = {'data_version': 1, 'kind': 'acceptance', 'business_accepted': True,
            'materials': [artifact(self.root, path)], 'report': {'runs': [path.relative_to(self.root).as_posix()]}}
        self.assertEqual(validation.inspect_record(self.root, self.profile, acceptance), {'unit'})
        self.assertEqual(record, original)
        check['required_cases'] = ['pkg::TestMul']
        with self.assertRaisesRegex(Invalid, 'TestMul'):
            validation.inspect_record(self.root, self.profile, record)
        check['required_cases'] = ['pkg::TestAdd']
        check['argv'].append('changed')
        with self.assertRaisesRegex(Invalid, 'Shared check definition changed'):
            validation.inspect_record(self.root, self.profile, record)

    def test_stale_check_needs_only_a_focused_rerun(self):
        self.setup_task()
        self.profile['checks']['safety'] = copy.deepcopy(self.profile['checks']['unit'])
        self.task['acceptance'][0]['checks'] = ['unit', 'safety']
        batch, _ = self.run_batch()
        names = [str(batch.relative_to(self.root))]
        self.profile['checks']['safety']['argv'] = self.profile['checks']['safety']['argv'] + ['changed']
        with self.assertRaisesRegex(Invalid, r'stale: safety \(.*definition changed: safety'):
            validation.verify_runs(self.root, self.profile, self.task, names)
        focused, record = validation.run_batch(self.root, self.profile, [self.task], selected=['safety'])
        self.assertEqual([r['id'] for r in record['results']], ['safety'])
        result = validation.verify_runs(self.root, self.profile, self.task, names + [str(focused.relative_to(self.root))])
        self.assertEqual(sorted(result['results']), ['safety', 'unit'])
        self.assertEqual([(s['check'], s['path']) for s in result['superseded']], [('safety', names[0])])

    def test_invalid_reevaluation_does_not_hide_valid_focused_rerun(self):
        self.setup_task()
        marker = self.root / '.tw/local/junit-cases.json'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('["TestAdd"]')
        check = self.junit('unit', [], ['pkg::TestAdd'])
        check['argv'] = [sys.executable, '-c',
            "import json; from pathlib import Path; "
            "rows = ''.join(f'<testcase classname=\"pkg\" name=\"{n}\"/>' "
            "for n in json.loads(Path('.tw/local/junit-cases.json').read_text())); "
            "Path(r'{output}/report.xml').write_text(f'<testsuite>{rows}</testsuite>')"]
        old, record = self.run_batch()
        self.assertEqual(record['results'][0]['status'], 'passed')
        self.assertEqual(record['results'][0]['exit_code'], 0)
        check['required_cases'] = ['pkg::TestSub']
        marker.write_text('["TestSub"]')
        focused, _ = validation.run_batch(self.root, self.profile, [self.task], selected=['unit'])
        old_name, focused_name = [p.relative_to(self.root).as_posix() for p in (old, focused)]
        for names in ([old_name, focused_name], [focused_name, old_name]):
            with self.subTest(names=names):
                result = validation.verify_runs(self.root, self.profile, self.task, names)
                self.assertEqual(result['results']['unit']['cases'], {'pkg::TestSub': 'passed'})
                self.assertEqual(result['selected_runs']['unit'], focused_name)
                self.assertEqual(result['superseded'][0]['path'], old_name)
                self.assertIn('Required case missing or not passed: pkg::TestSub', result['superseded'][0]['reason'])

    def test_newest_of_several_current_results_is_selected(self):
        self.setup_task()
        first, _ = self.run_batch()
        second, _ = self.run_batch()
        names = [str(p.relative_to(self.root)) for p in (second, first)]
        result = validation.verify_runs(self.root, self.profile, self.task, names)
        self.assertIn(str(second.parent.name), result['results']['unit']['artifacts'][0]['path'])
        self.assertEqual(result['superseded'][0]['reason'], 'A newer current result was selected')

    def test_recorded_environment_is_trusted_offline_after_the_fixture_is_removed(self):
        self.setup_task()
        marker = self.root / '.tw/local/environment.txt'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('fixture-1')
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture', 'identity': [sys.executable, '-c', "from pathlib import Path; print(Path('.tw/local/environment.txt').read_text())"]}
        path, _ = self.run_batch()
        names = [str(path.relative_to(self.root))]
        marker.unlink()
        with self.assertRaisesRegex(Invalid, 'Cannot confirm environment identity'):
            validation.verify_runs(self.root, self.profile, self.task, names)
        validation.verify_runs(self.root, self.profile, self.task, names, live=False)
        (self.root / 'app.py').write_text('def add(a,b): return a+b  # edited\n')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, names, live=False)

    def test_unsupported_data_version_cannot_be_reused(self):
        self.setup_task()
        path, record = self.run_batch()
        record['data_version'] = 2
        from common import write
        write(path, record)
        with self.assertRaisesRegex(Invalid, 'Expected schema 1 execution record'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_mutable_environment_identity_and_source_changes_during_execution(self):
        self.setup_task()
        marker = self.root / '.tw/local/environment.txt'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('fixture-1')
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture', 'identity': [sys.executable, '-c', "from pathlib import Path; print(Path('.tw/local/environment.txt').read_text())"]}
        path, _ = self.run_batch()
        marker.write_text('fixture-2')
        with self.assertRaisesRegex(Invalid, 'environment'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])
        self.profile['checks']['unit']['argv'] = [sys.executable, '-c', "from pathlib import Path; Path('app.py').write_text('changed')"]
        _, record = self.run_batch()
        self.assertFalse(record['source_unchanged'])

    def test_revision_sensitive_check_rejects_knowledge_commit(self):
        self.setup_task()
        self.profile['checks']['unit']['revision_sensitive'] = True
        path, _ = self.run_batch()
        self.git('commit', '--allow-empty', '-qm', 'revision changes')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_staging_a_deletion_keeps_the_same_executed_content(self):
        self.setup_task()
        (self.root / 'obsolete.txt').write_text('unused input')
        self.git('add', 'obsolete.txt')
        self.git('commit', '-qm', 'add obsolete input')
        (self.root / 'obsolete.txt').unlink()
        path, _ = self.run_batch()
        self.git('add', '-u')
        validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_repository_identity_is_not_just_a_reusable_project_label(self):
        self.setup_task()
        self.git('remote', 'add', 'origin', 'https://github.com/example/first.git')
        path, _ = self.run_batch()
        self.git('remote', 'set-url', 'origin', 'https://github.com/example/other.git')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])


if __name__ == '__main__':
    unittest.main()
