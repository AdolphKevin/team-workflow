"""场景清单、逐行结果契约及跨上下文统计的命令回归。"""
import copy
from datetime import datetime, timezone
import json
import subprocess
import sys
import unittest

import test_current_materials as fixtures
from test_scenarios import scenario_file
from common import read
import designs


class ScenarioRounds(unittest.TestCase):
    base = fixtures.CurrentMaterials
    setUp, git, check, setup_task, write, name, current, current_path = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name,
        base.current, base.current_path)

    def call(self, *args):
        from test_start_accept import TW
        result = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', *map(str, args)],
                                capture_output=True, text=True)
        self.assertTrue(result.stdout.startswith('{'), result.stderr or result.stdout)
        return result.returncode, json.loads(result.stdout)

    def prepare(self):
        self.setup_task(complexity='medium')
        self.scenario_path = self.root / '.tw/local/scenarios.json'
        self.scenarios = scenario_file()
        second = copy.deepcopy(self.scenarios['sops'][0])
        second['id'], second['title'] = 'T', '第二节点'
        for row in second['scenarios']:
            row['id'] = row['id'].replace('S-', 'T-')
        self.scenarios['sops'].append(second)
        self.save_scenarios()
        import common
        self.design['sections'][1]['data']['scenarios'] = [
            {'path': '.tw/local/scenarios.json', 'sha256': common.sha(self.scenario_path), 'nodes': ['S', 'T']}]
        self.write('design', self.design)
        self.approve_start()
        self.evidence = self.root / '.tw/local/results/observed.txt'
        self.evidence.parent.mkdir(parents=True, exist_ok=True)
        self.evidence.write_text('真实命令的原始输出\n')
        return self

    def save_scenarios(self):
        self.scenario_path.write_text(json.dumps(self.scenarios, ensure_ascii=False, indent=2))

    def approve_start(self):
        import design_files
        self.design = design_files.read(self.root / self.name('design'))
        approval = designs.approval_draft(self.design, 'carol', '已核对方案', mode='design')
        self.write('approval-design', approval)
        code, value = self.call('start', '--task', self.name('task'), '--design', self.name('design'),
                                '--approval', self.name('approval-design'))
        self.assertEqual(code, 0, value)
        return value

    def pending(self):
        code, value = self.call('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, value)
        return value

    def result(self, scenario, status='pass', executor='carol', **extra):
        return {'scenario': scenario, 'status': status, 'actual': '已核对预期结果与副作用',
                'executed_at': datetime.now(timezone.utc).isoformat(), 'executor': executor,
                'evidence': ['observed.txt'], **extra}

    def submit(self, rows):
        path = self.evidence.parent / 'results.jsonl'
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        return self.call('scenarios', 'submit', '--task', self.task['id'], '--results', path)

    def test_pending_lists_task_scenarios_with_executable_instructions(self):
        self.prepare()
        value = self.pending()
        self.assertEqual(value['summary_counts'], {'passed': 0, 'failed': 0, 'blocked': 0, 'pending': 4})
        self.assertEqual([(row['id'], row['node'], row['reason']) for row in value['pending']],
                         [('S-P', 'S', 'new'), ('S-N', 'S', 'new'), ('T-P', 'T', 'new'), ('T-N', 'T', 'new')])
        row = value['pending'][0]
        for key in ('title', 'verify', 'acceptance_entry', 'initial_state', 'steps', 'expected', 'forbidden_effects', 'fingerprint'):
            self.assertIn(key, row)
        self.assertEqual(row['acceptance_entry']['surface'], 'cli')
        from test_start_accept import TW
        text = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', 'scenarios',
                               'pending', '--task', self.task['id'], '--format', 'text'], capture_output=True, text=True)
        self.assertEqual(text.returncode, 0, text.stdout)
        for content in ('S-P', '初始状态', '运行命令', '结果为三', '副作用', 'new'):
            self.assertIn(content, text.stdout)

    def test_submit_records_round_copies_evidence_and_counts_first_results(self):
        self.prepare()
        code, value = self.submit([self.result(key, 'fail' if key == 'T-N' else 'pass')
                                   for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual(code, 0, value)
        self.assertEqual(value['round_statistics'], {'executed': 4, 'pass': 3, 'fail': 1, 'blocked': 0, 'skip': 0})
        self.assertEqual(value['statistics']['first_pass'], {'numerator': 3, 'denominator': 4, 'rate': 0.75})
        self.assertEqual(value['statistics']['summary_counts'], {'passed': 3, 'failed': 1, 'blocked': 0, 'pending': 0})
        self.assertEqual(value['pending_count'], 1)
        self.assertIn('scenarios submit', value['next_action'])
        group = self.current()
        self.assertEqual(group['scenario_rounds'], [value['artifact']])
        record = read(self.root / value['artifact']['path'])
        self.assertEqual((record['data_version'], record['kind'], record['task_id'], record['round']),
                         (1, 'scenario-round', self.task['id'], 1))
        self.assertEqual(record['statistics'], value['round_statistics'])
        self.assertEqual(record['results'][0]['fingerprint'], self.pending()['scenarios'][0]['fingerprint'])
        ref = record['results'][0]['evidence'][0]
        from common import sha
        self.assertEqual(ref['sha256'], sha(self.evidence))
        self.assertNotEqual(self.root / ref['path'], self.evidence)
        self.evidence.unlink()
        self.assertEqual((self.root / ref['path']).read_text(), '真实命令的原始输出\n')
        self.assertEqual([(r['id'], r['reason']) for r in self.pending()['pending']], [('T-N', 'failed')])

    def test_scenario_material_changes_only_its_status_and_stales_runs(self):
        self.prepare()
        # 使用产品目录中的场景材料，证明结果有效性与运行绑定使用不同范围。
        original = self.scenario_path
        self.scenario_path = self.root / 'scenarios.json'
        self.scenario_path.write_bytes(original.read_bytes())
        import common
        self.design['sections'][1]['data']['scenarios'][0].update(path='scenarios.json', sha256=common.sha(self.scenario_path))
        self.write('design', self.design)
        self.approve_start()
        code, ran = self.call('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        code, submitted = self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual(code, 0, submitted)
        self.scenarios['sops'][1]['scenarios'][1]['expected'] = ['修订后的预期']
        self.save_scenarios()
        value = self.pending()
        self.assertEqual([(r['id'], r['reason']) for r in value['pending']], [('T-N', 'changed')])
        self.assertEqual(value['summary_counts']['passed'], 3)
        import validation
        from common import load_profile, Invalid
        with self.assertRaises(Invalid):
            validation.verify_runs(self.root, load_profile(self.root), read(self.root / self.current()['task']['path']),
                                   [ran['artifact']['path']])
        # 范围核对与交付报告共用 changed_paths；验收材料归入方案材料。
        changed = validation.changed_paths(self.root, self.task, load_profile(self.root), self.design)
        self.assertNotIn('scenarios.json', changed)

    def test_product_change_uses_current_regression_cases_and_preserves_failures(self):
        self.prepare()
        # Go 的逐项报告提供两条已通过用例和一条已跳过用例。
        events = [{'Action': action, 'Package': 'p', 'Test': name} for action, name in
                  (('pass', 'TestA'), ('pass', 'TestB'), ('skip', 'TestSkip'))] + [{'Action': 'pass', 'Package': 'p'}]
        self.check('print(' + repr('\n'.join(json.dumps(event) for event in events)) + ')', format='go-json',
                   required_cases=['p::TestA'])
        from test_workflow import write_config
        write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::TestA', 'p::TestB']}
        self.scenarios['sops'][0]['scenarios'][1]['regression'] = {'check': 'unit', 'cases': ['p::TestSkip']}
        self.scenarios['sops'][1]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::Missing']}
        self.save_scenarios()
        code, value = self.submit([self.result(key, 'fail' if key == 'T-N' else 'pass')
                                   for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual(code, 0, value)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a + b  # 产品变化\n')
        self.assertEqual(self.pending()['summary_counts'], {'passed': 0, 'failed': 1, 'blocked': 0, 'pending': 3})
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        value = self.pending()
        self.assertEqual(value['summary_counts'], {'passed': 1, 'failed': 1, 'blocked': 0, 'pending': 2})
        self.assertEqual([(r['id'], r['reason']) for r in value['pending']],
                         [('S-N', 'source-changed'), ('T-P', 'source-changed'), ('T-N', 'failed')])

    def test_result_contract_collects_line_errors_and_leaves_materials_unchanged(self):
        self.prepare()
        path = self.evidence.parent / 'invalid.jsonl'
        good = self.result('S-P')
        invalid = [[], {**good, 'extra': 1}, {**good, 'actual': ' '}, {**good, 'executor': 8},
                   {**good, 'executed_at': '2099-01-01T00:00:00Z'}, {**good, 'executed_at': '2020-01-01T00:00:00'},
                   {**good, 'status': 'other'}, {**good, 'status': 'blocked'}, {**good, 'status': 'skip'},
                   {**good, 'evidence': []}, {**good, 'evidence': '../outside.txt'},
                   {**good, 'evidence': ['../outside.txt']}, {**good, 'scenario': 'outside'},
                   {**good, 'evidence': ['missing.txt']}, {**good, 'session': {}}, {**good, 'note': []},
                   {**good, 'evidence': [3]}, {**good, 'evidence': ['/tmp/outside']},
                   {**good, 'finding': ' '}, {**good, 'evidence': ['observed.txt'], 'status': 'fail', 'actual': ''}]
        before = self.current_path().read_bytes()
        path.write_text('\n'.join(json.dumps(row) for row in invalid) + '\n{\n')
        code, value = self.call('scenarios', 'submit', '--task', self.task['id'], '--results', path)
        self.assertEqual((code, value['error_code']), (1, 'scenario-result-invalid'))
        self.assertEqual({row['line'] for row in value['errors']}, set(range(1, len(invalid) + 2)))
        self.assertIn('修正结果文件中列出的行', value['next_action'])
        self.assertEqual(before, self.current_path().read_bytes())
        # 空文件也应指向结果格式修复，随后再核对清单完整性。
        path.write_text('')
        code, value = self.call('scenarios', 'submit', '--task', self.task['id'], '--results', path)
        self.assertEqual((code, value['error_code']), (1, 'scenario-result-invalid'))
        self.assertEqual(value['errors'][0]['line'], 1)

    def test_submit_requires_each_pending_result_and_an_independent_executor(self):
        self.prepare()
        before = self.current_path().read_bytes()
        code, value = self.submit([self.result('S-P')])
        self.assertEqual((code, value['error_code']), (1, 'scenario-results-incomplete'))
        self.assertEqual(value['missing'], ['S-N', 'T-P', 'T-N'])
        self.assertIn('按列出的场景补齐结果后重新提交', value['next_action'])
        code, value = self.submit([self.result(key, executor=' BOB ') for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual((code, value['error_code']), (1, 'independence-required'))
        self.assertEqual(before, self.current_path().read_bytes())
        code, value = self.submit([self.result(key) for key in ('S-P', 'S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual((code, value['error_code']), (1, 'scenario-result-invalid'))
        self.assertEqual(value['errors'][0]['line'], 2)

    def test_evidence_reuses_size_and_executable_guards(self):
        self.prepare()
        before = self.current_path().read_bytes()
        for head in (b'\x7fELFpayload', b'MZpayload'):
            self.evidence.write_bytes(head)
            code, value = self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])
            self.assertEqual((code, value['error_code']), (1, 'scenario-result-invalid'))
            self.assertIn('executable', value['problem'])
        with self.evidence.open('wb') as handle:
            handle.truncate(64 * 1024 * 1024 + 1)
        code, value = self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual((code, value['error_code']), (1, 'scenario-result-invalid'))
        self.assertIn('64 MiB', value['problem'])
        self.assertEqual(before, self.current_path().read_bytes())

    def test_statistics_compare_latest_executor_results_and_first_current_content(self):
        self.prepare()
        keys = ('S-P', 'S-N', 'T-P', 'T-N')
        rows = [self.result(key, status, **({'finding': 'F-' + key, 'evidence': []} if status in ('blocked', 'skip') else {}))
                for key, status in zip(keys, ('pass', 'fail', 'blocked', 'skip'))]
        code, first = self.submit(rows)
        self.assertEqual(code, 0, first)
        self.assertEqual(first['statistics']['first_pass'], {'numerator': 1, 'denominator': 2, 'rate': 0.5})
        self.assertEqual(first['statistics']['summary_counts'], {'passed': 1, 'failed': 1, 'blocked': 2, 'pending': 0})
        code, second = self.submit([self.result(key, executor='agent:session-1', session='会话一') for key in keys])
        self.assertEqual(code, 0, second)
        self.assertEqual(second['statistics']['agreement'], {'numerator': 1, 'denominator': 2, 'rate': 0.5})
        code, third = self.submit([self.result('S-N')])
        self.assertEqual(code, 0, third)
        self.assertEqual(third['round'], 3)
        self.assertEqual(third['statistics']['agreement'], {'numerator': 2, 'denominator': 2, 'rate': 1.0})
        self.assertEqual(third['statistics']['by_executor']['carol'],
                         {'executed': 4, 'pass': 2, 'fail': 0, 'blocked': 1, 'skip': 1})
        code, dashboard = self.submit([self.result(key, executor='项目看板导出') for key in keys])
        self.assertEqual(code, 0, dashboard)
        self.assertEqual(dashboard['statistics']['agreement'], {'numerator': 4, 'denominator': 4, 'rate': 1.0})
        self.assertEqual(dashboard['statistics']['first_pass'], first['statistics']['first_pass'])
        self.assertEqual(dashboard['pending_count'], 0)
        code, flow = self.call('status', '--task', self.task['id'])
        self.assertEqual(code, 0, flow)
        self.assertEqual(flow['next_step']['id'], 'run')
        self.assertEqual(dashboard['next_action'], flow['next_step']['next_command'])
        self.scenarios['sops'][0]['scenarios'][0]['expected'] = ['全新内容']
        self.save_scenarios()
        current = self.pending()['statistics']
        self.assertEqual(current['first_pass'], {'numerator': 0, 'denominator': 1, 'rate': 0.0})
        self.assertEqual(current['agreement'], {'numerator': 3, 'denominator': 3, 'rate': 1.0})

    def test_new_context_keeps_rounds_and_product_passes(self):
        self.prepare()
        code, value = self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual(code, 0, value)
        old = self.current()
        self.write('approval-design', designs.approval_draft(self.design, 'dave', '新批准', mode='design'))
        code, started = self.call('start', '--task', self.name('task'), '--design', self.name('design'),
                                  '--approval', self.name('approval-design'))
        self.assertEqual(code, 0, started)
        self.assertFalse(started['continued'])
        self.assertNotEqual(old['context'], self.current()['context'])
        self.assertEqual(old['scenario_rounds'], self.current()['scenario_rounds'])
        self.assertEqual(self.pending()['summary_counts'], {'passed': 4, 'failed': 0, 'blocked': 0, 'pending': 0})

    def test_status_displays_scenario_step_and_metrics_lists_rounds(self):
        self.prepare()
        code, status = self.call('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        ids = [row['id'] for row in status['steps']]
        self.assertEqual(ids[ids.index('run') + 1], 'scenarios')
        # 仅增加展示，现有流程下一步仍指向运行检查。
        self.assertEqual(status['next_step']['id'], 'run')
        step = next(row for row in status['steps'] if row['id'] == 'scenarios')
        self.assertEqual(step['summary_counts']['pending'], 4)
        self.assertEqual(step['first_pass'], {'numerator': 0, 'denominator': 0, 'rate': None})
        self.assertIn('tw team scenarios pending --task ' + self.task['id'], step['next_command'])
        self.assertIn('场景验收', '\n'.join(status['step_lines']))
        self.assertEqual(self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])[0], 0)
        self.assertEqual(self.submit([self.result('S-P')])[0], 0)
        code, value = self.call('metrics', '--task', self.task['id'])
        self.assertEqual(code, 0, value)
        metrics = value['metrics'][0]['scenarios']
        self.assertEqual([row['round'] for row in metrics['rounds']], [1, 2])
        self.assertEqual([row['statistics']['executed'] for row in metrics['rounds']], [4, 1])
        self.assertEqual(metrics['statistics']['first_pass'], {'numerator': 4, 'denominator': 4, 'rate': 1.0})
        self.assertIn('第 2 轮', '\n'.join(value['lines']))

    def test_new_context_keeps_current_regression_available(self):
        self.prepare()
        events = [{'Action': 'pass', 'Package': 'p', 'Test': 'TestA'}, {'Action': 'pass', 'Package': 'p'}]
        self.check('print(' + repr('\n'.join(json.dumps(event) for event in events)) + ')', format='go-json')
        from test_workflow import write_config
        write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::TestA']}
        self.save_scenarios()
        self.assertEqual(self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])[0], 0)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a+b  # 新实现\n')
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        before = self.pending()
        self.assertEqual(before['summary_counts'], {'passed': 1, 'failed': 0, 'blocked': 0, 'pending': 3})
        self.write('approval-design', designs.approval_draft(self.design, 'dave', '新批准', mode='design'))
        code, started = self.call('start', '--task', self.name('task'), '--design', self.name('design'),
                                  '--approval', self.name('approval-design'))
        self.assertEqual(code, 0, started)
        self.assertFalse(started['continued'])
        self.assertEqual(self.pending()['summary_counts'], before['summary_counts'])

    def test_submit_rejects_source_content_or_evidence_mutation_during_copy(self):
        import contextlib
        import io
        from pathlib import Path
        from unittest.mock import patch
        import workflow
        self.prepare()
        rows = [self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')]
        path = self.evidence.parent / 'race.jsonl'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        original_write = Path.write_bytes
        for change in ('source', 'scenario', 'evidence'):
            with self.subTest(change=change):
                before = self.current_path().read_bytes()
                fired = []
                def copying(target, data):
                    result = original_write(target, data)
                    if not fired and target.name.endswith('-observed.txt'):
                        fired.append(True)
                        if change == 'source':
                            app = self.root / 'app.py'
                            app.write_text(app.read_text() + '\n# 并发产品修改\n')
                        elif change == 'scenario':
                            self.scenarios['sops'][0]['scenarios'][0]['expected'] = ['并发场景修改']
                            self.save_scenarios()
                        else:
                            self.evidence.write_text('并发证据修改')
                    return result
                output = io.StringIO()
                with patch.object(Path, 'write_bytes', copying), contextlib.redirect_stdout(output):
                    code = workflow.main(['--root', str(self.root), 'scenarios', 'submit', '--task', self.task['id'], '--results', str(path)])
                value = json.loads(output.getvalue())
                self.assertTrue(fired)
                self.assertEqual((code, value['error_code']),
                                 (1, 'scenario-result-invalid' if change == 'evidence' else 'source-stale'), value)
                if change == 'evidence':
                    self.assertEqual(value['errors'][0]['line'], 1)
                self.assertEqual(before, self.current_path().read_bytes())

    def test_explicit_context_selection_keeps_task_level_rounds(self):
        self.prepare()
        old_context = self.current()['context']
        self.assertEqual(self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])[0], 0)
        refs = self.current()['scenario_rounds']
        self.task['non_goals'] = ['切换任务说明']
        self.write('task', self.task)
        self.assertEqual(self.call('start', '--task', self.name('task'))[0], 0)
        code, status = self.call('status', '--task', self.task['id'], '--context', old_context['path'])
        self.assertEqual(code, 0, status)
        step = next(row for row in status['steps'] if row['id'] == 'scenarios')
        self.assertEqual(step['summary_counts'], {'passed': 4, 'failed': 0, 'blocked': 0, 'pending': 0})
        self.assertEqual(self.current()['scenario_rounds'], refs)

    def test_product_fingerprint_excludes_own_markdown_materials_and_keeps_foreign_files(self):
        self.prepare()
        own = self.root / 'docs/own.md'
        own.parent.mkdir(parents=True)
        own.write_text(designs.render(self.design))
        foreign = copy.deepcopy(self.design)
        foreign['task_id'] = '另一个任务'
        other = self.root / 'docs/foreign.md'
        other.write_text(designs.render(foreign))
        code, initial = self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])
        self.assertEqual(code, 0, initial)
        own.write_text(own.read_text() + '\n本任务验收材料的补充说明。\n')
        value = self.pending()
        self.assertNotEqual(value['source_digest'], initial['source_digest'])
        self.assertEqual(value['product_digest'], initial['product_digest'])
        self.assertEqual(value['summary_counts']['passed'], 4)
        other.write_text(other.read_text() + '\n其他任务的变化。\n')
        self.assertEqual(self.pending()['summary_counts']['pending'], 4)

    def test_regression_reuses_go_parent_and_child_case_validation(self):
        self.prepare()
        events = [{'Action': 'pass', 'Package': 'p', 'Test': 'TestA'},
                  {'Action': 'pass', 'Package': 'p', 'Test': 'TestParent'},
                  {'Action': 'skip', 'Package': 'p', 'Test': 'TestParent/Child'},
                  {'Action': 'pass', 'Package': 'p'}]
        self.check('print(' + repr('\n'.join(json.dumps(event) for event in events)) + ')', format='go-json',
                   required_cases=['p::TestA'])
        from test_workflow import write_config
        write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::TestA']}
        self.scenarios['sops'][0]['scenarios'][1]['regression'] = {'check': 'unit', 'cases': ['p::TestParent']}
        self.save_scenarios()
        self.assertEqual(self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])[0], 0)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a+b  # 新版本\n')
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        value = self.pending()
        self.assertEqual(value['summary_counts'], {'passed': 1, 'failed': 0, 'blocked': 0, 'pending': 3})
        self.assertEqual(next(row['reason'] for row in value['pending'] if row['id'] == 'S-N'), 'source-changed')

    def test_command_check_without_case_report_keeps_regression_pending(self):
        self.prepare()
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::TestA']}
        self.save_scenarios()
        self.assertEqual(self.submit([self.result(key) for key in ('S-P', 'S-N', 'T-P', 'T-N')])[0], 0)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a+b  # 新实现\n')
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        self.assertEqual(self.pending()['summary_counts']['pending'], 4)
