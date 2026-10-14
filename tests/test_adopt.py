"""Moving a project onto the current tool keeps old evidence as history and names what to re-run."""
import contextlib
import io
import json
import unittest

import test_workflow as fixtures
from common import VERSION, create, read, write
import validation
import workflow


class AdoptCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = workflow.main([args[0], '--root', str(self.root), *args[1:]])
        return status, json.loads(output.getvalue())

    def test_preview_names_legacy_evidence_and_apply_only_stamps_the_profile(self):
        self.check('import app; assert app.add(1, 2) == 3')
        write(self.root / '.team-workflow.json', self.profile)
        path, record = validation.run_batch(self.root, self.profile, [self.task])
        legacy = dict(record, schema_version=5)
        create(self.root / '.team-workflow/old/run.json', legacy)
        create(self.root / '.team-workflow/old/acceptance.json',
               {'schema_version': 5, 'kind': 'acceptance', 'task_id': 'TASK-149'})
        before = (self.root / '.team-workflow/old/run.json').read_bytes()
        status, preview = self.cli('adopt')
        self.assertEqual(status, 0)
        self.assertTrue(preview['read_only'])
        self.assertEqual(preview['profile']['changes'][0]['to'], VERSION)
        self.assertEqual(preview['legacy_evidence']['count'], 2)
        self.assertEqual(preview['legacy_evidence']['tasks']['TASK-149'], ['.team-workflow/old/acceptance.json'])
        self.assertIn(self.task['id'], preview['legacy_evidence']['tasks'])
        self.assertNotIn('workflow_version', read(self.root / '.team-workflow.json'))
        status, applied = self.cli('adopt', '--apply')
        self.assertEqual((status, applied['kind']), (0, 'adopt-result'))
        self.assertEqual(read(self.root / '.team-workflow.json')['workflow_version'], VERSION)
        self.assertEqual((self.root / '.team-workflow/old/run.json').read_bytes(), before)
        status, again = self.cli('adopt')
        self.assertEqual(again['profile']['changes'], [])

    def test_newer_project_asks_for_a_tool_update(self):
        write(self.root / '.team-workflow.json', dict(self.profile, workflow_version='99.0.0'))
        status, result = self.cli('adopt')
        self.assertEqual((status, result['error_code']), (1, 'tool-outdated'))


class EvidenceGuard(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def test_compiled_executables_are_never_evidence(self):
        write(self.root / '.team-workflow.json', self.profile)
        write(self.root / '.team-workflow/task.json', self.task)
        binary = self.root / '.team-workflow/core.test'
        binary.write_bytes(b'\xcf\xfa\xed\xfe' + b'\0' * 64)
        log = self.root / '.team-workflow/stdout.txt'
        log.write_text('ok\n')
        for path, allow, expected in [(binary, [], 'compiled executable'), (binary, ['--allow-large-evidence'], 'compiled executable')]:
            with self.subTest(allow=allow):
                status, result = AdoptCases.cli(self, 'evidence', '--task', '.team-workflow/task.json',
                                                '--path', str(path.relative_to(self.root)), *allow)
                self.assertEqual(status, 1)
                self.assertIn(expected, result['problem'])
        status, result = AdoptCases.cli(self, 'evidence', '--task', '.team-workflow/task.json', '--path', '.team-workflow/stdout.txt')
        self.assertEqual(status, 0)
        self.assertEqual(result['artifacts'][0]['path'], '.team-workflow/stdout.txt')


if __name__ == '__main__':
    unittest.main()
