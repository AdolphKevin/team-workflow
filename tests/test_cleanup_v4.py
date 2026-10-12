import os
from pathlib import Path
import unittest

import test_workflow as fixtures
from common import Invalid, artifact, create
import cleanup


class CleanupCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def request(self, name, finished=True):
        directory = self.root / '.team-workflow/tasks/task/requests' / name
        create(directory / 'request.json', {'task_id': 'T', 'pid': os.getpid()})
        if finished:
            create(directory / 'response.json', {'ok': False, 'problem': 'old failure'})
        return directory

    def test_only_unreferenced_completed_requests_can_be_removed(self):
        abandoned = self.request('old')
        retained = self.request('referenced')
        self.assertEqual(cleanup.preview(self.root)['candidates'], [])
        create(self.root / '.team-workflow/final.json', {'schema_version': 4, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, p) for p in self.root.glob('.team-workflow/tasks/*/requests/*/request.json')],
            'materials': [{'path': str((retained / 'response.json').relative_to(self.root))}]})
        plan = cleanup.preview(self.root)
        self.assertEqual(plan['candidates'], [str(abandoned.relative_to(self.root))])
        cleanup.apply(self.root, plan)
        self.assertFalse(abandoned.exists())
        self.assertTrue(retained.exists())
        self.assertTrue((self.root / 'app.py').exists())

    def test_changed_references_and_active_requests_refuse_application(self):
        self.request('old')
        create(self.root / '.team-workflow/final.json', {'schema_version': 4, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, p) for p in self.root.glob('.team-workflow/tasks/*/requests/*/request.json')]})
        plan = cleanup.preview(self.root)
        active = self.request('active', finished=False)
        with self.assertRaisesRegex(Invalid, 'active'):
            cleanup.apply(self.root, plan)
        create(active / 'response.json', {'ok': False})
        with self.assertRaisesRegex(Invalid, 'changed'):
            cleanup.apply(self.root, plan)

    def test_symlink_or_corrupt_json_does_not_allow_cleanup(self):
        old = self.request('old')
        (old / 'broken.json').write_text('{')
        self.assertFalse(cleanup.preview(self.root)['ok'])
        (old / 'link').symlink_to(self.root / 'app.py')
        self.assertTrue(any('Symlink' in g for g in cleanup.preview(self.root)['gaps']))

    def test_old_completion_does_not_make_a_reopened_task_deletable(self):
        self.request('first')
        create(self.root / '.team-workflow/final.json', {'schema_version': 4, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, p) for p in self.root.glob('.team-workflow/tasks/*/requests/*/request.json')]})
        self.assertEqual(len(cleanup.preview(self.root)['candidates']), 1)
        self.request('later-failed')
        self.assertEqual(cleanup.preview(self.root)['candidates'], [])
