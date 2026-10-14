"""An installed skill that differs from its release is reported and blocks verification."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from common import ALLOW_MODIFIED, Invalid, integrity, manifest, tool_gate, write
import common
import workflow


class InstalledSkillIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.skill = Path(self.tmp.name) / 'team-workflow'
        shutil.copytree(fixtures.SCRIPTS.parent, self.skill,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'MANIFEST.json'))
        (self.skill / 'MANIFEST.json').write_text(json.dumps(manifest(self.skill)))
        environment = patch.dict(os.environ, {ALLOW_MODIFIED: ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.root_patch = patch.object(common, 'SKILL_ROOT', self.skill)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_release_copy_is_intact_and_caches_are_ignored(self):
        (self.skill / 'scripts/__pycache__').mkdir()
        (self.skill / 'scripts/__pycache__/common.cpython-313.pyc').write_bytes(b'cache')
        (self.skill / '.DS_Store').write_bytes(b'finder')
        state = integrity()
        self.assertEqual(state['status'], 'intact', state)
        self.assertEqual(tool_gate(), {'version': common.VERSION, 'integrity': 'intact', 'override': False})

    def test_patched_missing_or_added_files_are_named(self):
        knowledge = self.skill / 'scripts/knowledge.py'
        knowledge.write_text(knowledge.read_text() + '\n# local patch\n')
        (self.skill / 'references/notes.md').write_text('extra')
        (self.skill / 'templates/task.json').unlink()
        state = integrity()
        self.assertEqual(state['status'], 'modified')
        self.assertEqual(state['changed'], ['scripts/knowledge.py'])
        self.assertEqual(state['unexpected'], ['references/notes.md'])
        self.assertEqual(state['missing'], ['templates/task.json'])
        with self.assertRaisesRegex(Invalid, 'scripts/knowledge.py.*npx skills update'):
            tool_gate()

    def test_missing_manifest_is_unknown_and_also_blocks(self):
        (self.skill / 'MANIFEST.json').unlink()
        self.assertEqual(integrity()['status'], 'unknown')
        with self.assertRaisesRegex(Invalid, 'unknown'):
            tool_gate()

    def test_explicit_override_is_recorded(self):
        (self.skill / 'SKILL.md').write_text('patched')
        with patch.dict(os.environ, {ALLOW_MODIFIED: '1'}):
            self.assertEqual(tool_gate(), {'version': common.VERSION, 'integrity': 'modified', 'override': True})

    def test_project_reports_tool_modified_and_cli_override_sets_the_gate(self):
        case = fixtures.WorkflowCases('setUp')
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        skill = case.fake_cs()
        write(case.root / '.team-workflow.json', case.profile)
        (self.skill / 'SKILL.md').write_text('patched')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = workflow.main(['project', '--root', str(case.root), '--cs-skill', str(skill)])
        result = json.loads(output.getvalue())
        self.assertEqual((status, result['error_code']), (1, 'tool-modified'))
        self.assertIn('SKILL.md', result['problem'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.main(['project', '--root', str(case.root), '--cs-skill', str(skill),
                                            '--allow-modified-tool']), 0)
        self.assertEqual(os.environ[ALLOW_MODIFIED], '1')


if __name__ == '__main__':
    unittest.main()
