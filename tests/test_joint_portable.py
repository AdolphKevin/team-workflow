"""Portable aggregation contracts over three actual isolated Git repositories.

Individual delivery verification is covered in test_continuation; here its
result is a unit-test fixture so failures isolate the joint boundary.
"""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from common import Invalid, write
import github_read
import portable
import verification


class JointPortableCases(unittest.TestCase):
    def setUp(self):
        self.fixtures = []
        self.roots = {}
        self.commits = {}
        self.profiles = {}
        self.tasks = {}
        self.url = 'https://github.com/example/core/issues/1'
        for name in ('core', 'gateway', 'common'):
            fixture = fixtures.WorkflowCases()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.git('remote', 'add', 'origin', 'https://github.com/example/' + name + '.git')
            fixture.profile['project'] = name
            fixture.task['id'] = 'https://github.com/example/' + name + '/issues/1'
            fixture.check('print("actual command covered separately")')
            if name == 'core':
                fixture.task['risks'] = ['cross-service']
                fixture.profile['risk_checks']['cross-service'] = ['unit']
            self.fixtures.append(fixture)
            repo = 'example/' + name
            self.roots[repo] = fixture.root
            self.commits[repo] = fixture.task['base']
            self.profiles[repo] = fixture.profile
            self.tasks[repo] = fixture.task
            write(fixture.root / '.team-workflow/profile.json', fixture.profile)
            write(fixture.root / '.team-workflow/task.json', fixture.task)
            write(fixture.root / '.team-workflow/report.json', {'schema_version': 3})
        self.manifest = {'schema_version': 3, 'task_id': self.url, 'joint': 'example/core',
            'participants': [{'repository': repo, 'commit': self.commits[repo], 'profile': '.team-workflow/profile.json',
                              'task': '.team-workflow/task.json', 'report': '.team-workflow/report.json'}
                             for repo in ('example/core', 'example/gateway')],
            'dependencies': [{'repository': 'example/common', 'commit': self.commits['example/common']}]}
        self.source = {'repositories': {}, 'files': {}}
        for repo, root in self.roots.items():
            self.source['repositories'].update(portable.source_state(root, {'inputs': []})['repositories'])

    def api(self, endpoint, **kw):
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        if endpoint.endswith('/comments?per_page=100'):
            return []
        repo = '/'.join(endpoint.split('/')[1:3])
        task = self.tasks[repo]
        import json
        return {'html_url': task['id'], 'body': '```team-workflow-task\n' + json.dumps(
            {'schema_version': 3, 'task': task, 'parent': None if repo == 'example/core' else self.url}) + '\n```',
            'updated_at': '2026-10-01T00:00:00Z', 'assignees': [{'login': 'owner'}]}

    def delivery(self, root, profile, task, report, cs_skill):
        return {'ok': True, 'scope': 'test-fixture-only', 'records': [
            {'result': {'id': 'unit'}, 'portable_source': copy.deepcopy(self.source)}]}

    def aggregate(self, manifest=None):
        with patch.object(github_read, 'api', side_effect=self.api), patch.object(verification, 'verify', side_effect=self.delivery):
            return verification.aggregate(manifest or self.manifest, None, self.roots)

    def test_distinct_task_ids_share_parent_and_all_versions(self):
        result = self.aggregate()
        self.assertTrue(result['ok'])
        self.assertEqual(result['versions'], self.commits)

    def test_missing_common_from_manifest_or_execution_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['dependencies'] = []
        with self.assertRaisesRegex(Invalid, 'omits or mismatches'):
            self.aggregate(manifest)
        del self.source['repositories']['example/common']
        with self.assertRaisesRegex(Invalid, 'omits or mismatches'):
            self.aggregate()

    def test_wrong_participant_version_or_dirty_dependency_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['participants'][1]['commit'] = '0'*40
        with self.assertRaisesRegex(Invalid, 'commit differs'):
            self.aggregate(manifest)
        (self.roots['example/common'] / 'app.py').write_text('changed = True\n')
        with self.assertRaisesRegex(Invalid, 'unshared changes'):
            self.aggregate()

    def test_missing_mapping_joint_owner_or_different_parent_rejected(self):
        removed = self.roots.pop('example/common')
        with self.assertRaisesRegex(Invalid, 'checkout mapping'):
            self.aggregate()
        self.roots['example/common'] = removed
        manifest = copy.deepcopy(self.manifest)
        manifest['joint'] = 'example/common'
        with self.assertRaisesRegex(Invalid, 'Joint owner or execution'):
            self.aggregate(manifest)
        self.manifest['task_id'] = 'https://github.com/example/core/issues/99'
        with self.assertRaisesRegex(Invalid, 'another parent'):
            self.aggregate()

    def test_external_unversioned_file_cannot_certify_joint_delivery(self):
        self.source['files']['workspace'] = '0'*64
        with self.assertRaisesRegex(Invalid, 'versioned repositories'):
            self.aggregate()


if __name__ == '__main__':
    unittest.main()
