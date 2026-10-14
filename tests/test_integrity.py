"""Both skills use the shared installation checker and reject modified release files."""
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
from common import ALLOW_MODIFIED, Invalid, tool_gate
from tw_runtime import install
import common
import workflow


class InstalledSkillIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parent = Path(self.tmp.name)
        self.knowledge = parent / 'team-knowledge'
        self.skill = parent / 'team-workflow'
        for source, target in ((install.SKILL, self.knowledge), (common.SKILL_ROOT, self.skill)):
            shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'MANIFEST.json'))
            (target / 'MANIFEST.json').write_text(json.dumps(install.manifest(target)))
        for mocked in (patch.dict(os.environ, {ALLOW_MODIFIED: ''}),
                       patch.object(install, 'SKILL', self.knowledge),
                       patch.object(common, 'SKILL_ROOT', self.skill),
                       patch.object(common, 'INSTALL_HOME', common.ContextVar('test_home', default=parent / 'home'))):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_release_copy_is_intact_and_caches_are_ignored(self):
        (self.knowledge / 'scripts/__pycache__').mkdir(exist_ok=True)
        (self.knowledge / 'scripts/__pycache__/common.cpython-313.pyc').write_bytes(b'cache')
        (self.skill / '.DS_Store').write_bytes(b'finder')
        self.assertEqual(install.integrity(self.knowledge)['status'], 'intact')
        self.assertEqual(tool_gate(), {'version': common.VERSION, 'integrity': 'intact', 'override': False})

    def test_patched_missing_or_added_files_are_named(self):
        path = self.knowledge / 'scripts/tw_runtime/team/knowledge.py'
        path.write_text(path.read_text() + '\n# local patch\n')
        (self.skill / 'references/notes.md').write_text('extra')
        (self.skill / 'templates/task.json').unlink()
        self.assertEqual(install.integrity(self.knowledge)['changed'], ['scripts/tw_runtime/team/knowledge.py'])
        state = install.integrity(self.skill)
        self.assertEqual(state['unexpected'], ['references/notes.md'])
        self.assertEqual(state['missing'], ['templates/task.json'])
        with self.assertRaisesRegex(Invalid, 'scripts/tw_runtime/team/knowledge.py'):
            tool_gate()

    def test_missing_manifest_is_unknown_and_also_blocks(self):
        (self.knowledge / 'MANIFEST.json').unlink()
        self.assertEqual(install.integrity(self.knowledge)['status'], 'unknown')
        with self.assertRaisesRegex(Invalid, 'unknown'):
            tool_gate()

    def test_explicit_override_is_recorded(self):
        (self.skill / 'SKILL.md').write_text('patched')
        with patch.dict(os.environ, {ALLOW_MODIFIED: '1'}):
            self.assertEqual(tool_gate(), {'version': common.VERSION, 'integrity': 'modified', 'override': True})

    def test_project_reports_tool_modified_and_cli_override_sets_the_gate(self):
        case = fixtures.WorkflowCases('setUp')
        case.setUp()
        self.addCleanup(case.doCleanups)
        (self.skill / 'SKILL.md').write_text('patched')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = workflow.main(['project', '--root', str(case.root), '--home', str(self.skill.parent / 'home')])
        self.assertEqual((status, json.loads(out.getvalue())['error_code']), (1, 'tool-modified'))
        self.assertIn('SKILL.md', json.loads(out.getvalue())['problem'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.main(['project', '--root', str(case.root), '--home', str(self.skill.parent / 'home'),
                                            '--allow-modified-tool']), 0)
        self.assertEqual(os.environ[ALLOW_MODIFIED], '1')

    def check_install_cli(self, home):
        from tw_runtime import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['version', '--check-install', '--home', str(home)])
        return code, json.loads(out.getvalue())

    def test_installed_copies_are_reported_but_only_the_running_tool_gates_verification(self):
        home = self.skill.parent / 'home'
        copy = home / '.agents/skills/team-workflow'
        shutil.copytree(self.skill, copy)
        code, state = self.check_install_cli(home)
        self.assertEqual(code, 0, state)
        self.assertTrue(state['ok'] and state['installed_ok'], state)
        (copy / 'SKILL.md').write_text('patched')
        other = home / '.codex/skills/team-knowledge'
        shutil.copytree(self.knowledge, other)
        shipped = json.loads((other / 'MANIFEST.json').read_text())
        (other / 'MANIFEST.json').write_text(json.dumps({**shipped, 'version': '0.8.0'}))
        code, state = self.check_install_cli(home)
        self.assertEqual(code, 1, state)
        self.assertTrue(state['ok'])
        self.assertFalse(state['installed_ok'])
        modified, older = state['installation_problems']
        self.assertIn(str(copy), modified)
        self.assertIn('SKILL.md', modified)
        self.assertIn('0.8.0', older)
        self.assertEqual(tool_gate()['integrity'], 'intact')

    def test_a_symlink_in_another_copy_is_reported_but_blocks_only_in_the_running_tool(self):
        home = self.skill.parent / 'home'
        copy = home / '.claude/skills/team-workflow'
        shutil.copytree(self.skill, copy)
        (copy / 'references/local-link.md').symlink_to(copy / 'references/contracts.md')
        code, state = self.check_install_cli(home)
        self.assertEqual(code, 1, state)
        self.assertTrue(state['ok'])
        self.assertIn('符号链接', state['installation_problems'][0])
        self.assertEqual(tool_gate()['integrity'], 'intact')
        (self.skill / 'references/local-link.md').symlink_to(self.skill / 'references/contracts.md')
        with self.assertRaisesRegex(Invalid, '符号链接'):
            tool_gate()

    def test_legacy_cs_skills_are_reported_for_removal(self):
        home = self.skill.parent / 'home'
        legacy = home / '.claude/skills/cs'
        legacy.mkdir(parents=True)
        (legacy / 'SKILL.md').write_text('legacy knowledge skill')
        code, state = self.check_install_cli(home)
        self.assertEqual(code, 1, state)
        self.assertTrue(state['ok'])
        self.assertEqual(state['legacy_skills'], [str(legacy)])
        self.assertIn('npx skills remove -g cs cs-analysis', state['installation_problems'][0])

    def test_team_skill_missing_is_optional_for_knowledge_but_required_for_team(self):
        shutil.rmtree(self.skill)
        self.assertTrue(install.check_install(self.skill.parent / 'home')['ok'])
        self.assertFalse(install.check_install(self.skill.parent / 'home', require_team=True)['ok'])
