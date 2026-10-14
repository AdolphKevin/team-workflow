"""Moving a project onto the current tool keeps old evidence as history and names what to re-run."""
import contextlib
import io
import json
import unittest

import test_workflow as fixtures
from common import VERSION, create, read, write
import validation
import workflow


class EvidenceCLI(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = workflow.main([args[0], '--root', str(self.root), *args[1:]])
        return status, json.loads(output.getvalue())




class EvidenceGuard(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def test_compiled_executables_are_never_evidence(self):
        fixtures.write_config(self.root, self.profile)
        write(self.root / '.tw/local/task.json', self.task)
        binary = self.root / '.tw/local/core.test'
        binary.write_bytes(b'\xcf\xfa\xed\xfe' + b'\0' * 64)
        log = self.root / '.tw/local/stdout.txt'
        log.write_text('ok\n')
        for path, allow, expected in [(binary, [], 'compiled executable'), (binary, ['--allow-large-evidence'], 'compiled executable')]:
            with self.subTest(allow=allow):
                status, result = EvidenceCLI.cli(self, 'evidence',
                                                '--path', str(path.relative_to(self.root)), *allow)
                self.assertEqual(status, 1)
                self.assertIn(expected, result['problem'])
        status, result = EvidenceCLI.cli(self, 'evidence', '--path', '.tw/local/stdout.txt')
        self.assertEqual(status, 0)
        self.assertEqual(result['artifacts'][0]['path'], '.tw/local/stdout.txt')


if __name__ == '__main__':
    unittest.main()
