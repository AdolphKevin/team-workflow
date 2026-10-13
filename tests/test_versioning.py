"""Installed tool versus project configuration: upgrade older projects, stop on newer ones."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from common import VERSION, read, write
import github_read
import versioning
import workflow
import workflow_v4


class VersionPolicy(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs

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

    def test_older_project_is_reported_with_the_upgrade_command(self):
        self.check("import app; assert app.add(1,2)==3")
        self.save()
        code, result = self.cli('project', '--cs-skill', str(self.fake_cs()))
        self.assertEqual(code, 1)
        self.assertEqual(result['error_code'], 'project-outdated')
        self.assertEqual(result['version']['status'], 'project-outdated')
        self.assertIn('upgrade', result['next_action'])
        self.assertEqual(result['cs']['status'], 'ready')

    def test_upgrade_previews_then_applies_and_stamps_the_installed_version(self):
        self.check("import app; assert app.add(1,2)==3")
        self.profile['external_inputs'] = {'shared': {'kind': 'repository', 'repository': 'acme/shared'}}
        self.save()
        before = (self.root / '.team-workflow.json').read_bytes()
        code, preview = self.cli('upgrade')
        self.assertEqual(code, 0)
        self.assertEqual(before, (self.root / '.team-workflow.json').read_bytes())
        self.assertEqual(preview['profile']['schema_version'], 5)
        self.assertEqual(preview['profile']['workflow_version'], VERSION)
        self.assertEqual(preview['profile']['external_inputs']['shared']['role'], 'build')
        self.assertEqual(preview['assumed_stateless'], ['unit'])
        code, applied = self.cli('upgrade', '--apply')
        self.assertEqual(code, 0)
        self.assertTrue(applied['applied'])
        self.assertEqual(read(self.root / '.team-workflow.json'), preview['profile'])
        code, result = self.cli('project', '--cs-skill', str(self.fake_cs()))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['version']['status'], 'current')
        code, again = self.cli('upgrade', '--apply')
        self.assertEqual((code, again['status']), (0, 'current'))

    def test_onboarding_matches_current_profile_and_task_adoption(self):
        guide = (Path(__file__).resolve().parents[1] /
                 'skills/team-workflow/references/onboarding.md').read_text()
        self.assertIn(f'格式为 {versioning.PROFILE_SCHEMA}', guide)
        self.assertIn(f'`upgrade --apply` 写入格式 {versioning.PROFILE_SCHEMA}', guide)
        self.assertIn('第二、三、四版任务只保留为历史输入', guide)
        self.assertIn('通过 `adopt` 生成第五版草稿', guide)
        for stale in ('格式为 4', '`upgrade --apply` 写入格式 4',
                      '第三版任务按自身格式继续走原兼容接口'):
            self.assertNotIn(stale, guide)

    def test_fixture_identity_is_never_invented(self):
        self.check("import app; assert app.add(1,2)==3", required_env=['TEST_DSN'])
        self.save()
        code, result = self.cli('upgrade', '--apply')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'needs-input')
        self.assertEqual(result['gaps'][0]['check'], 'unit')
        self.assertEqual(read(self.root / '.team-workflow.json')['schema_version'], 3)
        identity = {'environment': {'unit': {'kind': 'fixture', 'identity': [sys.executable, '-c', "print('fixture-1')"]}}}
        write(self.root / '.team-workflow/upgrade-input.json', identity)
        code, result = self.cli('upgrade', '--apply', '--record', '.team-workflow/upgrade-input.json')
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / '.team-workflow.json')['checks']['unit']['environment'], identity['environment']['unit'])

    def test_newer_project_stops_every_command_and_asks_to_update_the_tool(self):
        self.check("import app; assert app.add(1,2)==3", environment={'kind': 'stateless'})
        self.profile.update(schema_version=4, workflow_version='99.0.0')
        self.save()
        for args in (['project'], ['upgrade', '--apply'], ['snapshot']):
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

    def test_historical_tasks_require_adoption_and_status_is_read_only(self):
        self.profile.update(schema_version=5, workflow_version=VERSION)
        self.save()
        url = 'https://github.com/acme/project/issues/7'
        block = {'schema_version': 3, 'parent': None, 'task': {**self.task, 'id': url}}
        issue = {'html_url': url, 'body': '```team-workflow-task\n' + json.dumps(block) + '\n```\n'}
        with patch.object(github_read, 'issue', return_value=issue):
            code, state = self.cli('status', '--issue', url)
            self.assertEqual(code, 0)
            self.assertFalse(state['implementation_ready'])
            self.assertEqual(state['status'], 'needs-adoption')
            code, blocked = self.cli('task-export', '--issue', url)
            self.assertEqual(code, 1)
            self.assertIn('adopt', blocked['problem'])
            code, draft = self.cli('adopt', '--issue', url)
            self.assertEqual(code, 0, draft)
            self.assertEqual(read(self.root / draft['task']['path'])['schema_version'], 5)
            self.assertEqual(read(self.root / draft['original']['path'])['schema_version'], 2)
            self.assertFalse(draft['implementation_ready'])


if __name__ == '__main__':
    unittest.main()
