"""Execute checks against real temporary Git trees; verify content and environment reuse."""
import copy
import json
from pathlib import Path
import sys
import unittest

import test_workflow as fixtures
import v5_fixtures as v5
from common import Invalid, create, read
import validation


class ContentValidation(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def setup_v4(self):
        self.profile['schema_version'] = 5
        self.task.update(schema_version=5, design_id='D-add', section_ids=['T1'], acceptance_scope='requirement', paths=['app.py'])
        self.check("import app; assert app.add(1,2)==3")['environment'] = {'kind': 'stateless'}

    def run_batch(self, tasks=None):
        return validation.run_batch(self.root, self.profile, tasks or [self.task])

    def test_knowledge_commit_and_index_do_not_expire_execution(self):
        self.setup_v4()
        path, record = self.run_batch()
        (self.root / '.codestable').mkdir()
        (self.root / '.codestable/note.md').write_text('actual completed knowledge')
        self.git('add', '.codestable/note.md')
        self.git('commit', '-qm', 'knowledge only')
        self.assertEqual(validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])['checks'], ['unit'])
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        path, record = self.run_batch()
        self.git('add', 'app.py')
        validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_five_tasks_execute_seven_checks_once(self):
        self.setup_v4()
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
        self.setup_v4()
        path, _ = self.run_batch()
        names = [str(path.relative_to(self.root))]
        self.profile['checks']['unrelated'] = copy.deepcopy(self.profile['checks']['unit'])
        validation.verify_runs(self.root, self.profile, self.task, names)
        self.profile['checks']['unit']['timeout'] += 1
        with self.assertRaisesRegex(Invalid, 'definition'):
            validation.verify_runs(self.root, self.profile, self.task, names)
        self.profile['checks']['unit']['timeout'] -= 1
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, names)

    def test_mutable_environment_identity_and_source_changes_during_execution(self):
        self.setup_v4()
        marker = self.root / '.team-workflow/environment.txt'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('fixture-1')
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture', 'identity': [sys.executable, '-c', "from pathlib import Path; print(Path('.team-workflow/environment.txt').read_text())"]}
        path, _ = self.run_batch()
        marker.write_text('fixture-2')
        with self.assertRaisesRegex(Invalid, 'environment'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])
        self.profile['checks']['unit']['argv'] = [sys.executable, '-c', "from pathlib import Path; Path('app.py').write_text('changed')"]
        _, record = self.run_batch()
        self.assertFalse(record['source_unchanged'])

    def test_revision_sensitive_check_rejects_knowledge_commit(self):
        self.setup_v4()
        self.profile['checks']['unit']['revision_sensitive'] = True
        path, _ = self.run_batch()
        self.git('commit', '--allow-empty', '-qm', 'revision changes')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_staging_a_deletion_keeps_the_same_executed_content(self):
        self.setup_v4()
        (self.root / 'obsolete.txt').write_text('unused input')
        self.git('add', 'obsolete.txt')
        self.git('commit', '-qm', 'add obsolete input')
        (self.root / 'obsolete.txt').unlink()
        path, _ = self.run_batch()
        self.git('add', '-u')
        validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_repository_identity_is_not_just_a_reusable_project_label(self):
        self.setup_v4()
        self.git('remote', 'add', 'origin', 'https://github.com/example/first.git')
        path, _ = self.run_batch()
        self.git('remote', 'set-url', 'origin', 'https://github.com/example/other.git')
        with self.assertRaisesRegex(Invalid, 'source'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])


if __name__ == '__main__':
    unittest.main()
