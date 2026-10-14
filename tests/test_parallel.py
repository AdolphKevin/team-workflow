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
    run_check = fixtures.WorkflowCases.run_check

    def prepare(self, code='print("checked")'):
        self.task['design_id'] = 'arithmetic'
        self.check(code)
        fixtures.write_config(self.root, self.profile)
        write(self.root / '.tw/local/input/task.json', self.task)
        return [sys.executable, str(fixtures.SCRIPTS / 'workflow.py'), 'run', '--root', str(self.root),
                '--task', '.tw/local/input/task.json']

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
        self.assertEqual(len(list((self.root / '.tw/local/tasks').glob('*/requests/shared-request/execution/run.json'))), 1)

    def test_retry_after_lost_response_preserves_files_and_rejects_changed_inputs(self):
        args = self.prepare()
        first = self.result(self.start(args + ['--request-id', 'response-lost']))
        before = {p: p.read_bytes() for p in (self.root / '.tw/local/tasks').rglob('*') if p.is_file()}
        retry = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertEqual(first, retry)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / '.tw/local/tasks').rglob('*') if p.is_file()})
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        changed = self.result(self.start(args + ['--request-id', 'response-lost']))
        self.assertFalse(changed['ok'])
        self.assertIn('different inputs', changed['problem'])

    def test_interrupted_check_never_publishes_success_and_new_request_can_retry(self):
        args = self.prepare('import time; from pathlib import Path; Path(".tw/local/started").touch(); time.sleep(1.5)')
        process = self.start(args + ['--request-id', 'interrupted'])
        deadline = time.monotonic() + 5
        while not (self.root / '.tw/local/started').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.root / '.tw/local/started').exists())
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        result = self.result(self.start(args + ['--request-id', 'interrupted']))
        self.assertEqual(result['status'], 'interrupted')
        self.assertFalse(list((self.root / '.tw/local/tasks').glob('*/requests/interrupted/**/run.json')))
        self.assertTrue(self.result(self.start(args + ['--request-id', 'new-attempt']))['ok'])

    def test_terminated_run_stops_its_check_and_is_reported_as_interrupted(self):
        marker = self.root / '.tw/local/child.pid'
        args = self.prepare('import os, time; from pathlib import Path; '
                            f'Path(r"{marker}").write_text(str(os.getpid())); time.sleep(30)')
        process = self.start(args + ['--request-id', 'terminated'])
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child = int(marker.read_text())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM)
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)  # the check's process group was stopped with the tool
        self.assertEqual(list((self.root / '.tw/local/validation-active').glob('*.json')), [])
        import checklist
        steps = checklist.steps(self.root, self.task, snapshot(self.root, self.profile)['digest'], task_arg='t.json')
        self.assertEqual(next(r for r in steps['steps'] if r['id'] == 'run')['state'], 'running-or-interrupted')
        self.assertEqual(steps['next_step']['id'], 'run')

    def test_output_competition_is_atomic_and_failed_empty_output_is_retryable(self):
        args = self.prepare()
        # task exports compete for one explicitly requested filename, without replacing it.
        args[2] = 'task-export'
        processes = [self.start(args + ['--out', '.tw/local/occupied.json']) for _ in range(2)]
        results = [self.result(p) for p in processes]
        self.assertEqual(sum(r['ok'] for r in results), 1)
        self.assertEqual(read(self.root / '.tw/local/occupied.json'), self.task)
        args = self.prepare('pass')
        a = self.result(self.start(args + ['--request-id', 'empty-log']))
        b = self.result(self.start(args + ['--request-id', 'empty-log']))
        self.assertEqual(a, b)
        self.assertIn('request_artifacts', a)

    def test_machine_locations_do_not_change_identity_or_override_requirements(self):
        args = self.prepare()
        external = self.root / '.tw/local/external'
        external.mkdir()
        left, right = external / 'left', external / 'right'
        left.write_text('same input')
        right.write_text('same input')
        self.profile['external_inputs'] = {'fixture': {'kind': 'file'}}
        write(self.root / '.tw/local/repositories.json', {'inputs': {'fixture': str(left)}})
        a = snapshot(self.root, self.profile)
        token = LOCATIONS.set({'inputs': {'fixture': str(right)}, 'repositories': {}})
        try:
            self.assertEqual(a, snapshot(self.root, self.profile))
            right.write_text('different content')
            self.assertNotEqual(a, snapshot(self.root, self.profile))
        finally:
            LOCATIONS.reset(token)
        write(self.root / '.tw/local/repositories.json', {'inputs': {'fixture': str(left)}, 'checks': {}})
        with self.assertRaises(Invalid):
            profile_valid(self.profile, self.root)
        self.profile['data_version'] = 2
        with self.assertRaisesRegex(Invalid, 'data_version 1'):
            profile_valid(self.profile, self.root)
