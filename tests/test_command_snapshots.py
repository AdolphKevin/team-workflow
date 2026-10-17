"""命令内复用源码事实，显式的前后稳定性比较继续重新读取。"""
import contextlib
from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import patch

import test_four_command_delivery as fixtures
import validation
import workflow


class CommandSnapshots(unittest.TestCase):
    base = fixtures.FourCommandDelivery
    setUp, git, check, configure, start, current_path, current, draft_path, field, completed, submit = (
        base.setUp, base.git, base.check, base.configure, base.start, base.current_path,
        base.current, base.draft_path, base.field, base.completed, base.submit)
    run_checks, reviewed = base.run_checks, base.reviewed

    def command(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = workflow.main([*args, '--root', str(self.root)])
        return code, json.loads(out.getvalue())

    def test_command_snapshot_budgets(self):
        self.start('medium')
        counts, material_counts = {}, {}

        def measured(name, *args):
            with patch.object(validation, 'snapshot', wraps=validation.snapshot) as capture, patch.object(
                    validation, '_acceptance_materials', wraps=validation._acceptance_materials) as listing:
                code, value = self.command(*args)
            self.assertEqual(code, 0, value)
            counts[name] = capture.call_count
            material_counts[name] = listing.call_count
            return value

        measured('status', 'status', '--task', self.task['id'])
        pending = measured('scenarios pending', 'scenarios', 'pending', '--task', self.task['id'])
        directory = self.root / '.tw/local/performance'
        directory.mkdir()
        (directory / 'evidence.txt').write_text('算术入口输出 sum=3，无额外数据写入。\n')
        rows = [{'scenario': row['id'], 'status': 'pass', 'actual': '算术入口输出 sum=3，无额外数据写入',
                 'executor': 'carol', 'executed_at': datetime.now(timezone.utc).isoformat(),
                 'evidence': ['evidence.txt']} for row in pending['pending']]
        results = directory / 'results.jsonl'
        results.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        submitted = measured('scenarios submit', 'scenarios', 'submit', '--task', self.task['id'],
                             '--results', str(results))
        self.assertEqual(submitted['summary_counts'], {'passed': 2, 'failed': 0, 'blocked': 0, 'pending': 0})
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        measured('review', 'review', '--task', self.task['id'])
        code, reviewed = self.submit()
        self.assertEqual(code, 0, reviewed)
        accepted = measured('accept', 'accept', '--task', self.task['id'])
        self.assertTrue(accepted['business_accepted'])
        delivered = measured('deliver', 'deliver', '--task', self.task['id'],
                             '--reason', '本次仅调整实现，现行知识约定继续适用')
        self.assertTrue(delivered['delivery_complete'])
        # review 生成时有一次源码一致核对；deliver 复验已有验收并做最终核查，各比较一次。
        budgets = {'status': 1, 'scenarios pending': 1, 'scenarios submit': 2,
                   'review': 2, 'accept': 2, 'deliver': 3}
        self.snapshot_counts, self.material_counts = counts, material_counts
        for name, maximum in budgets.items():
            with self.subTest(command=name, counts=counts):
                self.assertLessEqual(counts[name], maximum)
                self.assertLessEqual(material_counts[name], maximum)

    def test_next_command_reads_current_source(self):
        self.start('medium')
        code, before = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, before)
        (self.root / 'app.py').write_text('def add(a, b):\n    return sum((a, b))\n')
        code, after = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, after)
        self.assertNotEqual(before['source_digest'], after['source_digest'])

    def test_snapshot_preserves_newlines_in_repository_and_file_names(self):
        import common
        import hashlib
        import shutil
        renamed = self.root.with_name(self.root.name + '\nroot')
        self.root.rename(renamed)
        self.root = renamed
        self.addCleanup(shutil.rmtree, renamed)
        name = '100644 ' + 'a' * 40 + ' 0\tfile\nname.py'
        (self.root / name).write_text('new input\n')
        state = common.snapshot(self.root, self.profile)
        self.assertEqual(state['head'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(state['files'][name], {
            'sha256': hashlib.sha256(b'new input\n').hexdigest(), 'executable': False})

    def test_review_keeps_its_source_stability_check(self):
        self.start('medium')
        self.run_checks()
        original = validation.verify_runs

        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            (self.root / 'app.py').write_text('def add(a, b):\n    return sum((a, b))\n')
            return value

        with patch.object(validation, 'verify_runs', side_effect=changed):
            code, result = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 1, result)
        self.assertIn('生成评审期间源码已改变', result['problem'])

    def test_accept_keeps_its_source_stability_check(self):
        self.reviewed('medium')
        import delivery
        original = delivery.evidence

        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            (self.root / 'app.py').write_text('def add(a, b):\n    return sum((a, b))\n')
            return value

        with patch.object(delivery, 'evidence', side_effect=changed):
            code, result = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, result)
        self.assertIn('Source changed during verification', result['problem'])
        self.assertIsNone(self.current()['acceptance'])

    def test_submit_keeps_its_source_stability_check(self):
        self.start('medium')
        code, pending = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, pending)
        directory = self.root / '.tw/local/changed-submit'
        directory.mkdir()
        (directory / 'evidence.txt').write_text('算术入口输出 sum=3\n')
        path = directory / 'results.jsonl'
        path.write_text(''.join(json.dumps({'scenario': row['id'], 'status': 'pass', 'actual': '算术入口输出 sum=3',
            'executor': 'carol', 'executed_at': datetime.now(timezone.utc).isoformat(),
            'evidence': ['evidence.txt']}) + '\n' for row in pending['pending']))
        import scenario_results
        original = scenario_results.load

        def changed(*args, **kwargs):
            rows = original(*args, **kwargs)
            (self.root / 'app.py').write_text('def add(a, b):\n    return sum((a, b))\n')
            return rows

        with patch.object(scenario_results, 'load', side_effect=changed):
            code, result = self.command('scenarios', 'submit', '--task', self.task['id'], '--results', str(path))
        self.assertEqual(code, 1, result)
        self.assertIn('提交期间源码或场景内容已变化', result['problem'])
        self.assertEqual(self.current().get('scenario_rounds', []), [])


if __name__ == '__main__':
    unittest.main()
