"""Guidance blocks: preview by default, write only marked blocks, keep user content."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import test_workflow  # noqa: F401  (adds the scripts directory to sys.path)
import guidance
import workflow


class GuidanceBlocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.root, self.home = base / 'project', base / 'home'
        self.root.mkdir()
        (self.home / '.claude').mkdir(parents=True)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main([*args, '--root', str(self.root), '--home', str(self.home)])
        return code, json.loads(output.getvalue())

    def actions(self, result):
        return {Path(t['path']).name + ':' + t.get('client', 'project'): t['action'] for t in result['targets']}

    def test_preview_writes_nothing_and_reports_each_target(self):
        (self.root / 'AGENTS.md').write_text('# Project\n\nKeep me.\n', encoding='utf-8')
        code, result = self.cli('guidance')
        self.assertEqual(code, 0)
        self.assertTrue(result['read_only'])
        self.assertEqual(self.actions(result), {'AGENTS.md:project': 'append', 'CLAUDE.md:project': 'create',
                                                'CLAUDE.md:claude-code': 'create', 'AGENTS.md:codex': 'skipped'})
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        self.assertEqual((self.root / 'AGENTS.md').read_text(encoding='utf-8'), '# Project\n\nKeep me.\n')
        self.assertFalse((self.home / '.claude/CLAUDE.md').exists())
        blocks = {t['kind']: t.get('block') or t.get('text') for t in result['targets'] if t['action'] != 'skipped'}
        self.assertEqual(blocks['claude'], guidance.render('claude'))
        self.assertIn('\n@AGENTS.md\n', blocks['claude'])
        self.assertIn('需求完成门槛', blocks['project'])
        self.assertNotIn('__REFERENCE__', blocks['global'])
        self.assertIn(str(guidance.REFERENCE), blocks['global'])

    def test_apply_keeps_user_content_and_is_idempotent(self):
        (self.root / 'AGENTS.md').write_text('# Project\n\nKeep me.\n', encoding='utf-8')
        (self.home / '.codex').mkdir()
        (self.home / '.codex/AGENTS.md').write_text('## Style\n\nPlain words.\n', encoding='utf-8')
        code, result = self.cli('guidance', '--apply')
        self.assertEqual(code, 0)
        self.assertFalse(result['read_only'])
        project = (self.root / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertTrue(project.startswith('# Project\n\nKeep me.\n\n<!-- team-workflow:guidance:project start -->'))
        self.assertTrue(project.endswith('<!-- team-workflow:guidance:project end -->\n'))
        self.assertNotIn(str(self.home), project)
        codex = (self.home / '.codex/AGENTS.md').read_text(encoding='utf-8')
        self.assertTrue(codex.startswith('## Style\n\nPlain words.\n\n<!-- team-workflow:guidance:global start -->'))
        self.assertEqual((self.home / '.claude/CLAUDE.md').read_text(encoding='utf-8'), guidance.render('global'))
        self.assertEqual((self.root / 'CLAUDE.md').read_text(encoding='utf-8'), guidance.render('claude'))
        code, again = self.cli('guidance')
        self.assertEqual(set(self.actions(again).values()), {'unchanged'})
        self.assertEqual(again['summary'], '指引已是最新')

    def test_changed_block_is_replaced_in_place_without_touching_neighbors(self):
        start, end = guidance.markers('project')
        stale = f'# Project\n\n{start}\nold rules\n{end}\n\n## After\n\nStill here.\n'
        (self.root / 'AGENTS.md').write_text(stale, encoding='utf-8')
        code, result = self.cli('guidance', '--scope', 'project', '--apply')
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(result), {'AGENTS.md:project': 'update', 'CLAUDE.md:project': 'create'})
        text = (self.root / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertEqual(text, f'# Project\n\n{guidance.render("project")}\n## After\n\nStill here.\n')

    def test_existing_claude_md_gets_reference_unless_it_already_imports_agents(self):
        (self.root / 'CLAUDE.md').write_text('# C\n\nOwn rules.\n', encoding='utf-8')
        code, result = self.cli('guidance', '--scope', 'project', '--apply')
        self.assertEqual(self.actions(result), {'AGENTS.md:project': 'create', 'CLAUDE.md:project': 'append'})
        claude = (self.root / 'CLAUDE.md').read_text(encoding='utf-8')
        self.assertTrue(claude.startswith('# C\n\nOwn rules.\n\n<!-- team-workflow:guidance:claude start -->'))
        self.assertIn('\n@AGENTS.md\n', claude)
        for line in ('@AGENTS.md', '@./AGENTS.md'):
            (self.root / 'CLAUDE.md').write_text(f'# C\n\n{line}\n', encoding='utf-8')
            code, result = self.cli('guidance', '--scope', 'project', '--apply')
            self.assertEqual(self.actions(result)['CLAUDE.md:project'], 'unchanged')
            self.assertEqual((self.root / 'CLAUDE.md').read_text(encoding='utf-8'), f'# C\n\n{line}\n')

    def test_explicit_file_is_referenced_by_claude_md(self):
        code, result = self.cli('guidance', '--scope', 'project', '--file', 'docs/AGENTS.md')
        self.assertEqual([t['action'] for t in result['targets']], ['create', 'create'])
        self.assertEqual(Path(result['targets'][0]['path']), self.root / 'docs/AGENTS.md')
        self.assertIn('\n@docs/AGENTS.md\n', result['targets'][1]['text'])

    def test_symlink_mode_and_crlf_are_preserved(self):
        dotfiles = self.root.parent / 'dotfiles'
        dotfiles.mkdir()
        real = dotfiles / 'CLAUDE.md'
        real.write_bytes(b'# Mine\r\n\r\nline two\r\n')
        real.chmod(0o644)
        (self.home / '.claude/CLAUDE.md').symlink_to(real)
        code, result = self.cli('guidance', '--scope', 'global', '--apply')
        self.assertEqual(code, 0)
        self.assertTrue((self.home / '.claude/CLAUDE.md').is_symlink())
        data = real.read_bytes()
        self.assertTrue(data.startswith(b'# Mine\r\n\r\nline two\r\n\r\n<!-- team-workflow:guidance:global start -->\r\n'))
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertEqual(real.stat().st_mode & 0o777, 0o644)
        code, again = self.cli('guidance', '--scope', 'global')
        self.assertEqual(self.actions(again)['CLAUDE.md:claude-code'], 'unchanged')

    def test_damaged_markers_block_apply(self):
        start, _ = guidance.markers('project')
        (self.root / 'AGENTS.md').write_text(f'{start}\nno end marker\n', encoding='utf-8')
        code, result = self.cli('guidance', '--scope', 'project', '--apply')
        self.assertEqual(code, 1)
        self.assertIn('Damaged guidance markers', result['problem'])
        self.assertEqual((self.root / 'AGENTS.md').read_text(encoding='utf-8'), f'{start}\nno end marker\n')


if __name__ == '__main__':
    unittest.main()
