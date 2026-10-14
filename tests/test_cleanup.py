import os
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
        create(self.root / '.team-workflow/final.json', {'schema_version': 6, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, p) for p in self.root.glob('.team-workflow/tasks/*/requests/*/request.json')],
            'materials': [{'path': str((retained / 'response.json').relative_to(self.root))}]})
        plan = cleanup.preview(self.root)
        self.assertEqual(plan['candidates'], [str(abandoned.relative_to(self.root))])
        cleanup.apply(self.root, plan)
        self.assertFalse(abandoned.exists())
        self.assertTrue(retained.exists())
        self.assertTrue((self.root / 'app.py').exists())

    def material(self, kind, name, days_old, size=1024):
        directory = self.root / '.team-workflow' / kind / name
        directory.mkdir(parents=True)
        (directory / 'run.json').write_bytes(b'{}' + b' ' * size)
        stamp = __import__('time').time() - days_old * 86400
        for path in [directory / 'run.json', directory]:
            os.utime(path, (stamp, stamp))
        return directory

    def test_all_scope_reclaims_old_unreferenced_batches_and_lists_manual_outputs(self):
        orphan = self.material('batches', 'orphan', 30, size=4096)
        recent = self.material('batches', 'recent', 1)
        cited = self.material('imports', 'cited', 30)
        create(self.root / '.team-workflow/acceptance-149.json', {'materials': [
            {'path': str((cited / 'run.json').relative_to(self.root)), 'sha256': 'x'}]})
        manual = self.root / '.team-workflow/delivery-followup/evidence'
        manual.mkdir(parents=True)
        (manual / 'core.test').write_bytes(b'\x7fELF' + b'0' * 8192)
        stale = self.root / '.team-workflow/validation-active/dead.json'
        create(stale, {'pid': 2 ** 22 + 12345, 'tasks': ['T']})
        self.assertEqual(cleanup.preview(self.root)['candidates'], [])  # default scope is unchanged
        plan = cleanup.preview(self.root, 'all', 14)
        relative = lambda p: str(p.relative_to(self.root))
        self.assertEqual(plan['candidates'], sorted([relative(orphan), relative(stale)]))
        self.assertIn(relative(recent), plan['protected'])
        self.assertIn(relative(cited), plan['protected'])
        self.assertEqual({r['path'] for r in plan['unmanaged']},
                         {'.team-workflow/acceptance-149.json', '.team-workflow/delivery-followup'})
        self.assertGreater(next(r['bytes'] for r in plan['unmanaged'] if r['path'].endswith('followup')), 8192)
        self.assertGreaterEqual(plan['totals']['reclaimable_bytes'], 4096)
        self.assertEqual(plan['totals']['largest'][0]['path'], '.team-workflow/delivery-followup/evidence/core.test')
        cleanup.apply(self.root, plan)
        self.assertFalse(orphan.exists() or stale.exists())
        self.assertTrue(recent.exists() and cited.exists() and manual.exists())

    def test_changed_references_and_active_requests_refuse_application(self):
        self.request('old')
        create(self.root / '.team-workflow/final.json', {'schema_version': 6, 'kind': 'delivery-verification',
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
        create(self.root / '.team-workflow/final.json', {'schema_version': 6, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, p) for p in self.root.glob('.team-workflow/tasks/*/requests/*/request.json')]})
        self.assertEqual(len(cleanup.preview(self.root)['candidates']), 1)
        self.request('later-failed')
        self.assertEqual(cleanup.preview(self.root)['candidates'], [])

    def test_completed_task_keeps_submitted_issue_history(self):
        old = self.request('review-failure')
        create(old / 'review-input.json', {'schema_version': 6, 'task_id': 'T', 'at': '2026-10-13T00:00:00Z',
            'issues': [{'id': 'Q1', 'summary': 'A business decision was unresolved'}]})
        create(self.root / '.team-workflow/final.json', {'schema_version': 6, 'kind': 'delivery-verification',
            'task_id': 'T', 'ok': True, 'delivery_complete': True,
            'covered_requests': [artifact(self.root, old / 'request.json')]})
        plan = cleanup.preview(self.root)
        self.assertEqual(plan['candidates'], [])
        self.assertIn(str(old.relative_to(self.root)), plan['protected'])
