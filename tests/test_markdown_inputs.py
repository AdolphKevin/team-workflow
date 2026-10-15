"""D1: caller-supplied designs are Markdown; captured JSON is internal only."""
import contextlib
import io
import json
import unittest

import test_four_command_delivery as fixtures
from common import read, write
import workflow
import designs


class MarkdownInputCases(unittest.TestCase):
    setUp, git, check, configure, command = fixtures.FourCommandDelivery.setUp, fixtures.FourCommandDelivery.git, fixtures.FourCommandDelivery.check, fixtures.FourCommandDelivery.configure, fixtures.FourCommandDelivery.command

    def test_json_design_inputs_are_rejected_on_every_option(self):
        self.configure()
        write(self.root / '.tw/local/design.json', self.design)
        for command, options in [
            ('start', ['--design', '.tw/local/design.json']),
            ('status', ['--design', '.tw/local/design.json']),
            ('design-draft', ['--record', '.tw/local/design.json']),
            ('approval-draft', ['--design', '.tw/local/design.json', '--reviewer', 'alice']),
            ('design-diff', ['--design-history', '.tw/local/design.json']),
            ('issue-draft', ['--design', '.tw/local/design.json']),
            ('review', ['--design-history', '.tw/local/design.json']),
        ]:
            with self.subTest(command=command):
                code, value = self.command(command, '--task', '.tw/local/task.json', *options)
                self.assertEqual(code, 1, value)
                self.assertIn('Markdown', value['problem'])
                self.assertIn('references/designs.md', value['problem'])

    def test_markdown_start_captures_and_reuses_internal_json(self):
        self.configure()
        (self.root / '.tw/local/source.md').write_text(designs.render(self.design))
        code, value = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/source.md')
        self.assertEqual(code, 0, value)
        self.assertEqual(read(self.root / value['design']['path']), self.design)
        code, resumed = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, resumed)
        self.assertTrue(resumed['continued'])

    def test_design_draft_help_names_markdown_source(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(fixtures.TW), 'team', 'design-draft', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Markdown', result.stdout)
        self.assertNotIn('JSON input for the design', result.stdout)

    def test_schema_keeps_existing_template_names(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['schema', '--root', str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(output.getvalue())['templates']), {'config', 'design', 'task'})

    def test_schema_points_to_markdown_design_template(self):
        raw = io.StringIO()
        with contextlib.redirect_stdout(raw):
            code = workflow.main(['schema', '--root', str(self.root)])
        value = json.loads(raw.getvalue())
        self.assertEqual(code, 0, value)
        self.assertTrue(value['templates']['design'].endswith('/design.md'), value)


if __name__ == '__main__':
    unittest.main()

class MarkdownFixtureCases(unittest.TestCase):
    def test_fixture_writer_roundtrips_the_existing_plan(self):
        import tempfile
        from pathlib import Path
        from test_designs import example
        import plan_fixtures as plans
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'design.md'
            value = example()
            plans.write_design(path, value)
            self.assertEqual(designs.load(path.read_text()), value)
