"""T7 A1: the existing team commands own their options; only locations are global."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_workflow  # Adds the runtime directories to sys.path.
from common import ALLOW_MODIFIED, LOCATIONS, write
from tw_runtime import cli
import commands
import workflow


GLOBAL = {'--root', '--repository'}
OUTPUT = {'--format'}
TASK = {'--task', '--issue', '--context'}
REQUEST = {'--request-id', '--out', '--allow-modified-tool'}
INPUT = {'--input'}
QUERY = {'--path', '--symbol'}
REPORT = {'--design', '--brief', '--approval', '--design-history', '--run', '--review', '--dependency'}
EXPECTED = {
    'platform': {'--check', '--id', '--commit', '--reference', '--locator'},
    'project': {'--home', '--allow-modified-tool'},
    'snapshot': TASK | INPUT,
    'run': TASK | INPUT | REQUEST | {'--with-task', '--check', '--portable'},
    'brief': TASK | INPUT | REQUEST | QUERY,
    'review': TASK | INPUT | REQUEST | (REPORT - {'--review'}) | {'--submit', '--file', '--from-platform'},
    'accept': TASK | INPUT | REQUEST | REPORT | {'--report', '--home'},
    'verify': TASK | INPUT | REQUEST | {'--report', '--home'},
    'deliver': TASK | INPUT | REQUEST | {'--reason', '--home'},
    'aggregate': INPUT | {'--joint'},
    'evidence': INPUT | {'--path', '--evidence-repository', '--allow-large-evidence'},
    'version': {'--home'},
    'handoff': TASK | INPUT | REQUEST | {'--progress', '--kind', '--dependency', '--home'},
    'progress': TASK | INPUT | REQUEST | {'--progress'},
    'task-export': TASK | INPUT | REQUEST,
    'delivery-template': TASK | INPUT | REQUEST | REPORT | {'--acceptance'},
    'import-result': INPUT | REQUEST | {'--result'},
    'status': TASK | INPUT | {'--design', '--design-history', '--run', '--report'},
    'agents': {'--ledger', '--plan', '--mark', '--status', '--reason'},
    'start': TASK | INPUT | REQUEST | QUERY | {'--design', '--approval', '--design-history', '--dependency',
                                            '--grant', '--confirmed-by', '--home', '--run', '--report'},
    'design-draft': TASK | INPUT | REQUEST | {'--record', '--design'},
    'approval-draft': TASK | INPUT | REQUEST | {'--record', '--design', '--design-history', '--run', '--reviewer', '--confirmation', '--mode', '--revision'},
    'design-diff': TASK | INPUT | REQUEST | {'--design', '--design-history'},
    'schema': set(),
    'cleanup': {'--apply', '--dry-run', '--plan', '--cleanup-scope', '--older-than'},
    'guidance': {'--scope', '--apply', '--home', '--file'},
    'issue-draft': {'--task', '--design', '--with-task', '--reviewer'},
    'metrics': {'--task', '--issue', '--since'},
}


class TeamParser(unittest.TestCase):
    def test_each_command_declares_only_its_options(self):
        parser = workflow.parser()
        subparsers = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
        self.assertEqual(len(subparsers), 1, 'Every team command needs a subparser')
        self.assertEqual(set(subparsers[0].choices), set(EXPECTED))
        for name, subparser in subparsers[0].choices.items():
            options = {option for action in subparser._actions for option in action.option_strings}
            with self.subTest(command=name):
                self.assertEqual(options, EXPECTED[name] | OUTPUT | GLOBAL | {'-h', '--help'})

    def test_only_root_and_repository_are_global(self):
        options = {option for action in workflow.parser()._actions for option in action.option_strings}
        self.assertEqual(options, GLOBAL | {'-h', '--help'})

    def test_rejects_options_from_other_commands(self):
        for command, option, value in [('run', '--phase', 'acceptance'), ('status', '--approval', 'x'),
                                       ('schema', '--task', 'x'), ('run', '--kind', 'design'),
                                       ('metrics', '--request-id', 'x'), ('delivery-template', '--home', 'x')]:
            with self.subTest(command=command, option=option):
                error = io.StringIO()
                with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                    workflow.parser().parse_args([command, option, value])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(option, error.getvalue())

    def test_globals_are_accepted_before_after_and_on_both_sides(self):
        for command in EXPECTED:
            for arguments, expected in [
                (['--root', '/project', '--repository', 'a=/a', command], ['a=/a']),
                ([command, '--root', '/project', '--repository', 'a=/a'], ['a=/a']),
                (['--root', '/before', '--repository', 'a=/a', command, '--root', '/project',
                  '--repository', 'b=/b', '--repository', 'c=/c'], ['a=/a', 'b=/b', 'c=/c']),
            ]:
                with self.subTest(command=command, arguments=arguments):
                    args = workflow.parser().parse_args(arguments)
                    self.assertEqual(args.root, Path('/project'))
                    self.assertEqual(args.repository, expected)
                    self.assertEqual(args.command, command)

    def help(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            cli.main(['team', *args, '--help'])
        self.assertEqual(raised.exception.code, 0)
        return output.getvalue()

    def test_team_help_lists_every_command_with_a_description(self):
        help_text = self.help()
        for command in EXPECTED:
            with self.subTest(command=command):
                self.assertRegex(help_text, r'(?m)^\s+' + command + r'\s+\S')

    def test_command_help_only_lists_its_options(self):
        for command, options in EXPECTED.items():
            help_text = self.help(command)
            with self.subTest(command=command):
                listed = set(re.findall(r'(?m)^  (--[a-z-]+)(?:[ =]|$)', help_text))
                self.assertEqual(listed, options | OUTPUT | GLOBAL)

    def test_outer_team_injection_preserves_root_and_repository_mappings(self):
        observed = []

        def capture(args, root):
            observed.append((args.root, root, LOCATIONS.get()))
            return {'ok': True}

        for tail, expected in [(['schema'], Path('/outer')),
                               (['schema', '--root', '/explicit'], Path('/explicit')),
                               (['schema', '--root=/explicit'], Path('/explicit'))]:
            with self.subTest(tail=tail), patch.object(commands, 'dispatch', side_effect=capture), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['--root', '/outer', '--repository', 'one=/one', 'team',
                                           *tail, '--repository', 'two=/two']), 0)
                self.assertEqual(observed[-1], (expected, expected,
                                               {'repositories': {'one': '/one', 'two': '/two'}, 'inputs': {}}))

    def test_outer_team_accepts_globals_before_the_nested_command(self):
        observed = []

        def capture(args, root):
            observed.append((root, LOCATIONS.get()))
            return {'ok': True}

        for suffix, expected in [([], Path('/team')), (['--root', '/explicit'], Path('/explicit'))]:
            with self.subTest(suffix=suffix), patch.object(commands, 'dispatch', side_effect=capture), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['--root', '/outer', '--repository', 'one=/one', 'team',
                                           '--root', '/team', '--repository', 'two=/two', 'schema',
                                           *suffix, '--repository', 'three=/three']), 0)
                self.assertEqual(observed[-1], (expected, {'repositories': {
                    'one': '/one', 'two': '/two', 'three': '/three'}, 'inputs': {}}))


class TeamOptionBehavior(unittest.TestCase):
    setUp, git = test_workflow.WorkflowCases.setUp, test_workflow.WorkflowCases.git

    def command(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(['--root', str(self.root), 'team', *args])
        return code, json.loads(output.getvalue())

    def test_undeclared_optional_attributes_do_not_become_tool_defects(self):
        for name in EXPECTED:
            extra = ['--home', str(self.root / '.tw/local/test-home'), '--scope', 'project'] if name == 'guidance' else []
            with self.subTest(command=name):
                code, result = self.command(name, *extra)
                self.assertIn(code, (0, 1))
                self.assertNotEqual(result.get('error_code'), 'tool-defect', result)
                self.assertNotIn('AttributeError', result.get('problem', ''))
                if code == 1:
                    self.assertTrue(result.get('error_code'), result)

    def test_tool_override_and_install_home_keep_their_effects(self):
        home = self.root / '.tw/local/test-home'
        legacy = home / '.agents/skills/cs'
        legacy.mkdir(parents=True)
        with patch.dict(os.environ):
            os.environ.pop(ALLOW_MODIFIED, None)
            code, result = self.command('project', '--home', str(home), '--allow-modified-tool')
            self.assertEqual(code, 0, result)
            self.assertEqual(os.environ[ALLOW_MODIFIED], '1')
            self.assertTrue(result['tool']['override'])
            self.assertEqual(result['installation']['legacy_skills'], [str(legacy)])
            code, version = self.command('version', '--home', str(home))
            self.assertEqual(code, 0, version)
            self.assertEqual(version['installation']['legacy_skills'], [str(legacy)])

    def test_input_mapping_changes_the_source_snapshot(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        paths = [Path(external.name) / name for name in ('first.work', 'second.work')]
        for path, text in zip(paths, ('workspace A', 'workspace B')):
            path.write_text(text)
        self.profile['external_inputs'] = {'workspace': {'kind': 'file'}}
        test_workflow.write_config(self.root, self.profile)
        write(self.root / '.tw/local/task.json', self.task)
        args = ['snapshot', '--task', '.tw/local/task.json']
        code, missing = self.command(*args)
        self.assertEqual(code, 1)
        self.assertEqual(missing['error_code'], 'invalid-or-incomplete-input')
        self.assertIn('workspace', missing['problem'])
        results = []
        for path in (paths[0], paths[1], paths[0]):
            code, result = self.command(*args, '--input', 'workspace=' + str(path))
            self.assertEqual(code, 0, result)
            results.append(result['source_digest'])
        self.assertNotEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])

    def test_repository_mapping_reads_evidence_from_the_selected_checkout(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        checkout = Path(external.name) / 'dependency'
        shutil.copytree(self.root, checkout)
        subprocess.run(['git', '-C', str(checkout), 'remote', 'add', 'origin',
                        'https://github.com/acme/dependency.git'], check=True)
        path = checkout / 'original.txt'
        path.write_text('actual dependency evidence\n')
        self.profile['external_inputs'] = {'dependency': {'kind': 'repository', 'repository': 'github.com/acme/dependency'}}
        test_workflow.write_config(self.root, self.profile)
        args = ['evidence', '--evidence-repository', 'github.com/acme/dependency', '--path', path.name]
        code, missing = self.command(*args)
        self.assertEqual(code, 1)
        self.assertIn('github.com/acme/dependency', missing['problem'])
        code, result = self.command(*args, '--repository', 'github.com/acme/dependency=' + str(checkout))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['artifacts'], [{'repository': 'github.com/acme/dependency', 'path': path.name,
                                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}])


if __name__ == '__main__':
    unittest.main()
