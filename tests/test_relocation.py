"""Execution evidence remains current when an unchanged checkout changes location."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import test_four_command_delivery as four
import test_workflow as fixtures
from common import Invalid, read
import validation


class RelocationCases(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check = base.setUp, base.git, base.check
    command, start, run_checks = base.command, base.start, base.run_checks
    current_path, current, draft_path = base.current_path, base.current, base.draft_path
    field, completed, submit = base.field, base.completed, base.submit
    reviewed, accepted = base.reviewed, base.accepted

    def configure(self, complexity='simple', passed=True):
        self.base.configure(self, complexity, passed)
        check = self.profile['checks']['unit']
        check['argv'][2] += (
            "; import sys; from pathlib import Path; "
            "out=Path(sys.argv[1]); assert out.is_absolute(); "
            "(out/'observed.txt').write_text('sum=3')")
        check['argv'].append('{output}')
        check['artifacts'] = ['{output}/observed.txt']
        fixtures.write_config(self.root, self.profile)

    def relocate(self, copy=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name).resolve() / 'relocated project'
        original = self.root
        if copy:
            shutil.copytree(original, target)
        else:
            shutil.move(original, target)
            self.assertFalse(original.exists())
        self.root = target
        self.assertTrue((target / '.git').is_dir())
        self.assertTrue((target / '.tw/local').is_dir())

    def assert_accepted_and_deliverable(self, accepted):
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        states = {row['id']: row['state'] for row in status['steps']}
        self.assertEqual({key: states[key] for key in ('prepare', 'run', 'review', 'acceptance')},
                         dict.fromkeys(('prepare', 'run', 'review', 'acceptance'), 'done'), status)
        runs = self.current()['runs']
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'No reusable knowledge changed.')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['delivery_complete'])
        self.assertTrue(result['steps'][0]['reused'])
        self.assertEqual(self.current()['acceptance'], accepted['artifact'])
        self.assertEqual(self.current()['runs'], runs)
        record = read(self.root / runs[0]['path'])
        self.assertEqual(record['results'][0]['argv'], self.profile['checks']['unit']['argv'])
        self.assertEqual((self.root / record['results'][0]['artifacts'][0]['path']).read_text(), 'sum=3')

    def test_move_after_accept_keeps_steps_and_delivers_without_rerunning(self):
        accepted = self.accepted()
        self.relocate()
        self.assert_accepted_and_deliverable(accepted)

    def test_copy_after_accept_keeps_steps_and_delivers_without_rerunning(self):
        accepted = self.accepted()
        self.relocate(copy=True)
        self.assert_accepted_and_deliverable(accepted)

    def test_changed_argv_after_move_expires_only_the_affected_check(self):
        self.configure()
        self.profile['checks']['other'] = deepcopy(self.profile['checks']['unit'])
        self.profile['required_checks']['code'].append('other')
        fixtures.write_config(self.root, self.profile)
        code, result = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, result)
        self.run_checks()
        code, reviewed = self.submit()
        self.assertEqual(code, 0, reviewed)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.relocate()
        runs = [ref['path'] for ref in self.current()['runs']]
        self.profile['checks']['unit']['argv'].append('changed')
        fixtures.write_config(self.root, self.profile)
        other = deepcopy(self.task)
        other['acceptance'][0]['checks'] = ['other']
        profile = deepcopy(self.profile)
        profile['required_checks']['code'] = []
        self.assertEqual(validation.verify_runs(self.root, profile, other, runs)['checks'], ['other'])
        with self.assertRaisesRegex(Invalid, 'definition changed: unit'):
            validation.verify_runs(self.root, self.profile, self.task, runs)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'run')['state'], 'stale')
        code, refused = self.command('deliver', '--task', self.task['id'], '--reason', 'No knowledge change.')
        self.assertEqual(code, 1, refused)
        self.assertFalse(refused['delivery_complete'])

    def test_review_submission_request_can_be_retried_after_move(self):
        self.start()
        self.run_checks()
        code, submitted = self.submit(request_id='relocatable-review')
        self.assertEqual(code, 0, submitted)
        self.relocate()
        code, retried = self.command('review', '--task', self.task['id'], '--submit', '--request-id', 'relocatable-review')
        self.assertEqual(code, 0, retried)
        self.assertEqual(retried, submitted)

    def test_completed_delivery_and_preparation_continue_after_copy(self):
        accepted = self.accepted()
        # 全部步骤完成的夹具也完成新增的场景展示步骤，保留搬迁后的逐项断言。
        scenarios = read(self.root / 'tests/fixtures/scenarios.json')
        evidence = Path(accepted['artifact']['path']).relative_to('.tw/local').as_posix()
        results = self.root / '.tw/local/relocation-scenarios.jsonl'
        results.write_text(''.join(json.dumps({'scenario': row['id'], 'status': 'pass',
            'actual': '独立夹具已核对场景结果', 'executor': 'carol',
            'executed_at': datetime.now(timezone.utc).isoformat(), 'evidence': [evidence]}) + '\n'
            for node in scenarios['sops'] for row in node['scenarios']))
        code, submitted = self.command('scenarios', 'submit', '--task', self.task['id'], '--results', str(results))
        self.assertEqual(code, 0, submitted)
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No reusable knowledge changed.')
        self.assertEqual(code, 0, delivered)
        before = self.current()
        self.relocate(copy=True)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertTrue(all(row['state'] == 'done' for row in status['steps']), status)
        code, continued = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, continued)
        self.assertTrue(continued['continued'])
        self.assertEqual(continued['context'], before['context'])
        self.assert_accepted_and_deliverable(accepted)
        self.assertEqual(self.current()['delivery_report'], before['delivery_report'])

    def test_request_claims_and_responses_remain_reusable_after_copy(self):
        self.configure()
        commands = [
            ('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md'),
            ('run', '--task', self.task['id']),
            ('review', '--task', self.task['id'], '--submit'),
            ('accept', '--task', self.task['id']),
            ('deliver', '--task', self.task['id'], '--reason', 'No knowledge change.'),
        ]
        for args in commands:
            with self.subTest(command=args[0]):
                request_id = 'relocatable-' + args[0]
                if args[0] == 'review':
                    code, result = self.submit(request_id=request_id)
                else:
                    code, result = self.command(*args, '--request-id', request_id)
                self.assertEqual(code, 0, result)
                directory = result['request_directory']
                claim = (self.root / directory / 'request.json').read_bytes()
                response = (self.root / directory / 'response.json').read_bytes()
                self.relocate(copy=True)
                code, retried = self.command(*args, '--request-id', request_id)
                self.assertEqual(code, 0, retried)
                self.assertEqual(retried, result)
                self.assertEqual((self.root / directory / 'request.json').read_bytes(), claim)
                self.assertEqual((self.root / directory / 'response.json').read_bytes(), response)

    def test_expanded_command_cannot_replace_the_recorded_template(self):
        self.configure()
        _, record = validation.run_batch(self.root, self.profile, [self.task])
        self.assertEqual(validation.inspect_record(self.root, self.profile, record), {'unit'})
        row = record['results'][0]
        output = (self.root / row['artifacts'][0]['path']).parent
        row['argv'] = [arg.replace('{output}', str(output)) for arg in row['argv']]
        with self.assertRaisesRegex(Invalid, 'Recorded command or repository mismatch'):
            validation.inspect_record(self.root, self.profile, record)

    def test_absolute_query_path_request_can_be_retried_after_move(self):
        self.configure()
        for args in [
            ('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md'),
            ('brief', '--task', '.tw/local/task.json'),
        ]:
            with self.subTest(command=args[0]):
                request = ('--request-id', 'query-path-' + args[0])
                code, result = self.command(*args, *request, '--path', str(self.root / 'app.py'))
                self.assertEqual(code, 0, result)
                self.relocate()
                code, retried = self.command(*args, *request, '--path', str(self.root / 'app.py'))
                self.assertEqual(code, 0, retried)
                self.assertEqual(retried, result)


if __name__ == '__main__':
    unittest.main()
