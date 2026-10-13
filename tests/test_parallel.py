"""Real concurrent processes share request materials without losing or overwriting evidence."""
import json
import os
import signal
import subprocess
import sys
import time
import unittest

import test_workflow as fixtures
from common import Invalid, LOCATIONS, profile_valid, read, snapshot, write


class ParallelMaterials(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs
    run_check = fixtures.WorkflowCases.run_check

    def prepare(self, code='print("checked")'):
        self.task['design_id'] = 'arithmetic'
        self.check(code)
        write(self.root / '.team-workflow.json', self.profile)
        write(self.root / '.team-workflow/input/task.json', self.task)
        return [sys.executable, str(fixtures.SCRIPTS / 'workflow.py'), 'run', '--root', str(self.root),
                '--task', '.team-workflow/input/task.json']

    def start(self, args):
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: process.poll() is None and os.killpg(process.pid, signal.SIGKILL))
        return process

    def result(self, process):
        out, error = process.communicate(timeout=15)
        self.assertFalse(error, error)
        return json.loads(out)

    def test_default_paths_and_same_request_competition(self):
        args = self.prepare('import time; time.sleep(0.4); print("checked")')
        processes = [self.start(args) for _ in range(4)]
        results = [self.result(p) for p in processes]
        self.assertTrue(all(r['ok'] for r in results), results)
        self.assertEqual(len({r['artifact']['path'] for r in results}), 4)
        for result in results:
            self.assertTrue(read(self.root / result['artifact']['path'])['source_unchanged'])
        processes = [self.start(args + ['--request-id', 'shared-request']) for _ in range(3)]
        results = [self.result(p) for p in processes]
        self.assertTrue(any(r['ok'] for r in results), results)
        self.assertTrue(all(r['ok'] or r['status'] == 'running' for r in results), results)
        self.assertEqual(len(list((self.root / '.team-workflow/tasks').glob('*/requests/shared-request/execution/run.json'))), 1)

    def test_retry_after_lost_response_preserves_files_and_rejects_changed_inputs(self):
        args = self.prepare()
        first = self.result(self.start(args + ['--request-id', 'response-lost']))
        before = {p: p.read_bytes() for p in (self.root / '.team-workflow/tasks').rglob('*') if p.is_file()}
        retry = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertEqual(first, retry)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / '.team-workflow/tasks').rglob('*') if p.is_file()})
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        changed = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertFalse(changed['ok'])
        self.assertIn('different inputs', changed['problem'])

    def test_interrupted_check_never_publishes_success_and_new_request_can_retry(self):
        args = self.prepare('import time; from pathlib import Path; Path(".team-workflow/started").touch(); time.sleep(1.5)')
        process = self.start(args + ['--request-id', 'interrupted'])
        deadline = time.monotonic() + 5
        while not (self.root / '.team-workflow/started').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.root / '.team-workflow/started').exists())
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        result = self.result(self.start(args + ['--request-id', 'interrupted']))
        self.assertEqual(result['status'], 'interrupted')
        self.assertFalse(list((self.root / '.team-workflow/tasks').glob('*/requests/interrupted/**/run.json')))
        self.assertTrue(self.result(self.start(args + ['--request-id', 'new-attempt']))['ok'])

    def test_output_competition_is_atomic_and_failed_empty_output_is_retryable(self):
        args = self.prepare()
        # task exports compete for one explicitly requested filename, without replacing it.
        args[2] = 'task-export'
        processes = [self.start(args + ['--out', '.team-workflow/occupied.json']) for _ in range(2)]
        results = [self.result(p) for p in processes]
        self.assertEqual(sum(r['ok'] for r in results), 1)
        self.assertEqual(read(self.root / '.team-workflow/occupied.json'), self.task)
        args = self.prepare('pass')
        a = self.result(self.start(args + ['--request-id', 'empty-log']))
        b = self.result(self.start(args + ['--request-id', 'empty-log']))
        self.assertEqual(a, b)
        self.assertIn('request_artifacts', a)

    def test_machine_locations_do_not_change_identity_or_override_requirements(self):
        args = self.prepare()
        external = self.root / '.team-workflow/external'
        external.mkdir()
        left, right = external / 'left', external / 'right'
        left.write_text('same input')
        right.write_text('same input')
        self.profile['external_inputs'] = {'fixture': {'kind': 'file'}}
        write(self.root / '.team-workflow/local.json', {'inputs': {'fixture': str(left)}})
        a = snapshot(self.root, self.profile)
        token = LOCATIONS.set({'inputs': {'fixture': str(right)}, 'repositories': {}})
        try:
            self.assertEqual(a, snapshot(self.root, self.profile))
            right.write_text('different content')
            self.assertNotEqual(a, snapshot(self.root, self.profile))
        finally:
            LOCATIONS.reset(token)
        write(self.root / '.team-workflow/local.json', {'inputs': {'fixture': str(left)}, 'checks': {}})
        with self.assertRaises(Invalid):
            profile_valid(self.profile, self.root)
        self.profile['schema_version'] = 4
        with self.assertRaisesRegex(Invalid, 'configuration'):
            profile_valid(self.profile, self.root)
