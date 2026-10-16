"""已关闭阶段按记录本身显示最后结果。"""
import unittest

import test_workflow as fixtures
from common import artifact, write
import artifacts
import checklist


class ChecklistRecords(unittest.TestCase):
    setUp, git = fixtures.WorkflowCases.setUp, fixtures.WorkflowCases.git

    def record(self, name, command, second, ok=True, **options):
        directory = artifacts.directory(self.root, self.task['id'], name)
        claim = {'task_id': self.task['id'], 'command': command,
                 'started_at': f'2026-01-01T00:00:{second:02d}Z', **options}
        write(directory / 'request.json', claim)
        if ok is not None:
            write(directory / 'record.json', {'kind': 'prepared-context' if command == 'start' else 'review',
                  'source_digest': '旧源码', 'tool': {'override': name.endswith('override')}})
            response = {'ok': ok, 'artifact': artifact(self.root, directory / 'record.json'),
                        'request_directory': directory.relative_to(self.root).as_posix()}
            write(directory / 'response.json', response)
        return directory

    def test_recorded_steps_keep_last_results_across_new_starts_and_source_bindings(self):
        self.record('run-passed', 'run', 1)
        failed = self.record('run-failed', 'run', 2, ok=False)
        self.record('review-submitted', 'review', 3, submit=True)
        self.record('new-start', 'start', 4)
        self.record('review-draft', 'review', 5, submit=False)
        self.record('delivery-running', 'verify', 6, ok=None, phase='delivery')
        self.record('prepare-override', 'start', 7)
        steps = checklist.recorded_steps(self.root, checklist.records(self.root, self.task['id']))
        self.assertEqual([(row['id'], row['state']) for row in steps], [
            ('prepare', 'done'), ('run', 'failed'), ('review', 'done'),
            ('acceptance', 'pending'), ('knowledge', 'pending'), ('delivery', 'running-or-interrupted')])
        self.assertEqual(steps[1]['evidence'], failed.relative_to(self.root).as_posix())
        self.assertIn('--allow-modified-tool', steps[0]['note'])

    def test_in_progress_adds_trust_source_and_start_checks_to_recorded_results(self):
        trusted = self.record('review-trusted', 'review', 1, submit=True)
        latest = self.record('review-override', 'review', 2, submit=True)
        recorded = checklist.recorded_steps(self.root, checklist.records(self.root, self.task['id']))
        current = checklist.steps(self.root, self.task, '旧源码')['steps']
        self.assertEqual(recorded[2]['evidence'], (latest / 'record.json').relative_to(self.root).as_posix())
        self.assertEqual(current[2]['evidence'], (trusted / 'record.json').relative_to(self.root).as_posix())
        self.assertNotIn('note', current[2])
        stale = checklist.steps(self.root, self.task, '新源码')['steps']
        self.assertEqual((recorded[2]['state'], stale[2]['state']), ('done', 'stale'))
        self.record('new-start', 'start', 3)
        current = checklist.steps(self.root, self.task, '旧源码')['steps']
        self.assertEqual(current[2]['state'], 'pending')
        recorded = checklist.recorded_steps(self.root, checklist.records(self.root, self.task['id']))
        self.assertEqual(recorded[2]['state'], 'done')

    def test_in_progress_supersedes_a_failure_and_recorded_results_keep_it(self):
        self.record('run-failed', 'run', 1, ok=False)
        self.record('acceptance-passed', 'accept', 2)
        recorded = checklist.recorded_steps(self.root, checklist.records(self.root, self.task['id']))
        current = checklist.steps(self.root, self.task, '旧源码')['steps']
        self.assertEqual((recorded[1]['state'], current[1]['state']), ('failed', 'not-recorded'))
