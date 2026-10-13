"""Installed tool versus project configuration: stop when the project needs a newer tool."""
import contextlib
import io
import json
import unittest

import test_workflow as fixtures
from common import VERSION, write
import versioning
import workflow


class VersionPolicy(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main([*args, '--root', str(self.root)])
        return code, json.loads(output.getvalue())

    def save(self):
        write(self.root / '.team-workflow.json', self.profile)

    def test_semantic_version_precedence_includes_prereleases(self):
        ordered = ['0.5.0', '0.6.0-rc.1', '0.6.0-rc.2', '0.6.0-rc.10', '0.6.0', '0.6.1', '1.0.0']
        for older, newer in zip(ordered, ordered[1:]):
            self.assertEqual(versioning.compare(older, newer), -1, (older, newer))
            self.assertEqual(versioning.compare(newer, older), 1, (older, newer))
        self.assertEqual(versioning.compare(VERSION, VERSION), 0)

    def test_newer_project_stops_every_command_and_asks_to_update_the_tool(self):
        self.check("import app; assert app.add(1,2)==3")
        self.profile['workflow_version'] = '99.0.0'
        self.save()
        for args in (['project'], ['snapshot']):
            code, result = self.cli(*args)
            self.assertEqual(code, 1, args)
            self.assertEqual(result['error_code'], 'tool-outdated', args)
            self.assertIn('npx skills update -g', result['next_action'])
        self.profile.pop('workflow_version')
        self.profile['schema_version'] = 6
        self.save()
        code, result = self.cli('project')
        self.assertEqual((code, result['error_code']), (1, 'tool-outdated'))
        code, result = self.cli('version')
        self.assertEqual(code, 0)

    def test_older_or_unstamped_project_is_current(self):
        self.profile.pop('workflow_version', None)
        self.assertEqual(versioning.status(self.profile)['status'], 'current')
        self.profile['workflow_version'] = '0.1.0'
        self.assertEqual(versioning.status(self.profile)['status'], 'current')

    def test_older_contract_is_rejected_not_migrated(self):
        self.check("import app; assert app.add(1,2)==3")
        self.profile['schema_version'] = 4
        self.save()
        write(self.root / '.team-workflow/task.json', self.task)
        code, result = self.cli('snapshot', '--task', '.team-workflow/task.json')
        self.assertEqual(code, 1)
        self.assertIn('expected schema_version 5', result['problem'])


if __name__ == '__main__':
    unittest.main()
