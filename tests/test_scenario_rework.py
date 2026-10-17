"""R1/R2：场景下一步复用流程，受阻问题按方案职责和引用预填。"""
import copy
from datetime import datetime, timezone
import json
import unittest

import test_four_command_delivery as four
import test_scenario_acceptance as acceptance
from common import read, write


class ScenarioNextStep(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, command, configure, start, run_checks = (
        base.setUp, base.git, base.check, base.command, base.configure, base.start, base.run_checks)
    current_path, current, draft_path, field, completed, submit, reviewed = (
        base.current_path, base.current, base.draft_path, base.field, base.completed, base.submit, base.reviewed)

    def assert_flow_action(self, value, expected):
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(status['next_step']['id'], expected, status)
        self.assertEqual(value['next_action'], status['next_step']['next_command'])
        self.assertEqual(value['next_action'], status['next_action'])
        step = next(row for row in status['steps'] if row['id'] == 'scenarios')
        self.assertEqual(step['state'], 'done')
        self.assertNotIn('next_command', step)
        self.assertFalse(any(line.startswith('   下一步：') for line in status['step_lines']))

    def test_completed_scenarios_follow_run_then_review_after_new_file_content(self):
        self.reviewed()
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'])
        path = self.root / 'tests/fixtures/scenarios.json'
        document = read(path)
        added = copy.deepcopy(document['sops'][0]['scenarios'][0])
        added.update(id='S-ADDED', title='补充的验收场景')
        document['sops'][0]['scenarios'].append(added)
        write(path, document)
        code, pending = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, pending)
        self.assertEqual(pending['pending'], [])
        self.assertEqual(pending['task_phase'], 'delivered')
        results = self.root / '.tw/local/rework-results.jsonl'
        results.write_text(json.dumps({'scenario': 'S-ADDED', 'status': 'blocked', 'finding': 'Q9',
            'actual': '新入口等待环境开放', 'executor': 'carol',
            'executed_at': datetime.now(timezone.utc).isoformat(), 'evidence': []}) + '\n')
        code, submitted = self.command('scenarios', 'submit', '--task', self.task['id'], '--results', str(results))
        self.assertEqual(code, 0, submitted)
        self.assertEqual(submitted['pending_count'], 0)
        self.assert_flow_action(submitted, 'run')
        code, empty = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, empty)
        self.assert_flow_action(empty, 'run')
        code, ran = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        code, empty = self.command('scenarios', 'pending', '--task', self.task['id'])
        self.assertEqual(code, 0, empty)
        self.assert_flow_action(empty, 'review')
        code, submitted = self.command('scenarios', 'submit', '--task', self.task['id'], '--results', str(results))
        self.assertEqual(code, 0, submitted)
        self.assert_flow_action(submitted, 'review')


class ScenarioFindingIdentity(unittest.TestCase):
    base = acceptance.ScenarioAcceptance
    setUp, git, check, setup_task, write, name, current, current_path = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.current, base.current_path)
    call, prepare, save_scenarios, approve_start, pending, result, submit, all_results, field, completed = (
        base.call, base.prepare, base.save_scenarios, base.approve_start, base.pending, base.result, base.submit,
        base.all_results, base.field, base.completed)

    def test_prefilled_identity_uses_acceptance_owner_and_all_referencing_acceptances(self):
        self.prepare()
        self.design['roles']['acceptance_owner'] = 'acceptance-team'
        original = self.design['sections'][1]
        additional = copy.deepcopy(original)
        additional.update(id='A2', title='同一节点的另一验收项')
        additional['data']['scenarios'][0]['nodes'] = ['S']
        self.design['sections'].append(additional)
        self.design['sections'][0]['data']['requirement_acceptance'].append('A2')
        self.design['sections'][0]['data']['impact'][0]['acceptance'].append('A2')
        self.design['sections'][2]['data']['acceptance'].append('A2')
        self.task['acceptance'].append({'id': 'A2', 'expectation': additional['body'], 'checks': ['unit']})
        self.write('task', self.task)
        self.write('design', self.design)
        self.approve_start()
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        rows = self.all_results()
        rows[0].update(status='blocked', finding='Q9', actual='新入口等待环境开放', evidence=[])
        self.assertEqual(self.submit(rows)[0], 0)
        code, draft = self.call('review', '--task', self.task['id'])
        self.assertEqual(code, 0, draft)
        binding = read(self.root / draft['binding']['path'])
        issue = next(row for row in binding['template']['findings'] if row['id'] == 'Q9')
        self.assertEqual({key: issue[key] for key in ('id', 'owner', 'affects', 'blocks', 'summary')},
                         {'id': 'Q9', 'owner': 'acceptance-team', 'affects': ['A1', 'A2'],
                          'blocks': ['acceptance'], 'summary': 'S-P：新入口等待环境开放'})
        path = self.root / draft['review_file']
        text = self.completed(path.read_text())
        for field, value in (('结论', '通过'), ('理由', '已核对该节点的场景结果')):
            text = self.field(text, '## 验收 A2', field, value)
        path.write_text(text)
        code, submitted = self.call('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, submitted)
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'scenario-acceptance-incomplete'), refused)
        self.assertIn('S-P', refused['problem'])
        for field, value in {'状态': 'deferred', '处置理由': '环境开放后复验', '处置证据': 'SOP#env',
                             '确认人': 'user', '跟进任务': 'TASK-env（2026-11-01）', '范围调整': '后续任务复验 S-P'}.items():
            text = self.field(text, '### 问题 Q9', field, value)
        path.write_text(text)
        code, submitted = self.call('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, submitted)
        code, delivered = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['business_accepted'])
        self.assertTrue(delivered['delivery_complete'])
        self.assertEqual(delivered['unverified_scope'], [{'scenario': 'S-P', 'status': 'blocked',
            'finding': 'Q9', 'finding_state': 'deferred'}])
        self.assertIn('S-P：blocked；问题 Q9：deferred', delivered['summary_markdown'])
