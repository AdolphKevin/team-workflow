"""D9：完成的任务读取交付事实，重新开工后核对当前材料。"""
import copy
import json
import unittest
import test_four_command_delivery as fixtures
from common import read, write, artifact


class DeliveredTask(unittest.TestCase):
    base = fixtures.FourCommandDelivery
    setUp, git, check, command, configure, start, run_checks = (
        base.setUp, base.git, base.check, base.command, base.configure, base.start, base.run_checks)
    current_path, current, draft_path, field, completed, submit, reviewed = (
        base.current_path, base.current, base.draft_path, base.field, base.completed, base.submit, base.reviewed)

    def delivered(self):
        self.reviewed()
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, result)
        self.assertTrue(result['delivery_complete'])
        return self.current()['delivery']

    def unrelated_files(self):
        (self.root / 'other').mkdir()
        (self.root / 'other/plan.md').write_text('任务 B 的方案')
        (self.root / 'other/scenarios.yaml').write_text('任务 B 的场景')
        self.git('add', 'other')
        self.git('commit', '-qm', '另一个任务的材料')

    def test_unrelated_commit_keeps_delivered_records_and_reuses_delivery(self):
        original = self.delivered()
        before = self.current_path().read_bytes()
        self.unrelated_files()
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'delivered')
        self.assertEqual(status['summary'], '任务已交付')
        self.assertEqual(status['verified_records']['delivery'], original)
        self.assertEqual(status['verified_records']['acceptance'], self.current()['acceptance'])
        self.assertEqual([r['state'] for r in status['steps']], ['done'] * 7)
        self.assertIn('关闭授权', status['next_action'])
        self.assertIn('--task ' + self.task['id'], status['next_action'])
        code, checked = self.command('verify', '--task', self.task['id'],
            '--report', self.current()['delivery_report']['path'])
        self.assertEqual(code, 1, checked)
        self.assertFalse(checked.get('delivery_complete', False))
        code, reused = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, reused)
        self.assertTrue(reused['reused'])
        self.assertEqual(reused['artifact'], original)
        self.assertEqual(reused['summary_markdown'], read(self.root / original['path'])['summary_markdown'])
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_run_reopens_delivered_task_and_uses_current_inputs(self):
        self.delivered()
        (self.root / 'app.py').write_text('def add(a,b): return a+b+1\n')
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1, ran)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'in-progress')
        self.assertEqual(next(r['state'] for r in status['steps'] if r['id'] == 'run'), 'failed')
        self.assertEqual(status['next_step']['id'], 'run')
        self.assertIn('tw team run', status['next_step']['next_command'])

    def test_start_review_generation_and_submission_reopen_task(self):
        for command, extra in (('start', []), ('review', []), ('review', ['--submit'])):
            with self.subTest(command=command, extra=extra):
                self.delivered()
                code, result = self.command(command, '--task', self.task['id'], *extra)
                self.assertEqual(code, 0, result)
                code, status = self.command('status', '--task', self.task['id'])
                self.assertEqual(code, 0, status)
                self.assertEqual(status['task_phase'], 'in-progress')

    def test_scenario_submission_reopens_delivered_task(self):
        from common import now
        original = self.delivered()
        fixture = read(self.root / 'tests/fixtures/scenarios.json')
        directory = self.root / '.tw/local/phase-results'
        directory.mkdir()
        (directory / 'observed.txt').write_text('实际结果为三')
        rows = [{'scenario': row['id'], 'status': 'pass', 'actual': '已独立核对结果为三',
                 'evidence': ['observed.txt'], 'executed_at': now(), 'executor': 'carol'}
                for node in fixture['sops'] for row in node['scenarios']]
        path = directory / 'results.jsonl'
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        code, result = self.command('scenarios', 'submit', '--task', self.task['id'], '--results', str(path))
        self.assertEqual(code, 0, result)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['task_phase'], 'in-progress')
        self.assertIsNotNone(status['next_step'])
        self.assertEqual(self.current()['delivery'], original)

    def test_delivered_status_reads_legacy_snapshot_without_parsing_it(self):
        self.delivered()
        group = self.current()
        snapshot = self.root / group['design']['path']
        old = read(snapshot)
        old['sections'][1]['data']['scenario'] = {'roles': ['用户'], 'steps': ['旧字段']}
        old['sections'][1]['data'].pop('scenarios')
        write(snapshot, old)
        group['design'] = artifact(self.root, snapshot)
        write(self.current_path(), group)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['summary'], '任务已交付')
        self.assertEqual([r['state'] for r in status['steps']], ['done'] * 7)

    def test_in_progress_legacy_snapshot_directs_to_start(self):
        self.start()
        group = self.current()
        snapshot = self.root / group['design']['path']
        old = read(snapshot)
        old['sections'][1]['data']['scenario'] = {'roles': ['用户']}
        old['sections'][1]['data'].pop('scenarios')
        write(snapshot, old)
        group['design'] = artifact(self.root, snapshot)
        write(self.current_path(), group)
        code, refused = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('tw team start', refused['next_action'])
        self.assertNotIn('修正方案文件', refused['next_action'])
        self.assertNotIn('design.json', refused['next_action'])
        old_bytes = snapshot.read_bytes()
        code, restarted = self.command('start', '--task', self.task['id'], '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, restarted)
        self.assertFalse(restarted['continued'])
        self.assertNotEqual(self.current()['design']['path'], group['design']['path'])
        self.assertEqual(snapshot.read_bytes(), old_bytes)
        self.assertEqual(self.command('status', '--task', self.task['id'])[0], 0)
