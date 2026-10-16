"""批次 2 已确认命令场景的补充断言；业务预期来自原场景文件。"""
import copy
import json
import unittest

import test_scenario_acceptance as acceptance


class Batch2Regressions(unittest.TestCase):
    base = acceptance.ScenarioAcceptance
    setUp, git, check, setup_task, write, name, current, current_path = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.current, base.current_path)
    call, prepare, save_scenarios, approve_start, pending, result, submit, all_results = (
        base.call, base.prepare, base.save_scenarios, base.approve_start, base.pending, base.result, base.submit, base.all_results)
    field, reviewed = base.field, base.reviewed

    def completed(self, text):
        text = self.base.completed(self, text)
        if '- 批准方案与代码：' in text:
            text = self.field(text, '## 评审信息', '批准方案与代码', '是')
            text = self.field(text, '## 评审信息', '批准说明', '已独立核对方案、代码与当前运行')
        return text

    def declare_regression(self):
        self.prepare()
        self.design['assessment']['complexity'] = 'simple'
        self.write('design', self.design)
        xml = '<testsuite><testcase classname="CalcTests" name="test_add"/></testsuite>'
        self.check('from pathlib import Path; import sys; Path(sys.argv[1]).write_text(' + repr(xml) + ')',
                   format='junit', report='{output}/junit.xml')
        self.profile['checks']['unit']['argv'].append('{output}/junit.xml')
        from test_workflow import write_config
        write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['CalcTests::test_add']}
        self.save_scenarios()
        self.approve_start()

    def test_product_change_keeps_only_one_automated_scenario_passed(self):
        self.declare_regression()
        self.assertEqual(self.submit(self.all_results())[0], 0)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a + b  # 产品变化\n')
        before = self.pending()
        self.assertEqual([row['id'] for row in before['pending']], ['S-P', 'S-N', 'T-P', 'T-N'])
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        after = self.pending()
        self.assertEqual(after['summary_counts'], {'passed': 1, 'failed': 0, 'blocked': 0, 'pending': 3})
        self.assertEqual([row['id'] for row in after['pending']], ['S-N', 'T-P', 'T-N'])

    def test_delivery_lists_three_pending_regressions_and_one_automated(self):
        self.declare_regression()
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, delivered = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'])
        self.assertTrue(delivered['regression_pending'])
        self.assertEqual([row['id'] for row in delivered['automation_status']['pending']], ['S-N', 'T-P', 'T-N'])
        self.assertEqual(delivered['automation_status']['automated'], [
            {'id': 'S-P', 'check': 'unit', 'cases': ['CalcTests::test_add']}])
        self.assertIn('整体交付未完成', delivered['summary_markdown'])
        for key in ('S-N', 'T-P', 'T-N'):
            self.assertIn(key, delivered['summary_markdown'])

    def test_start_reports_inline_scenario_or_manual_verification_line_without_new_context(self):
        self.prepare()
        original = (self.root / self.name('design')).read_text()
        before = sorted((self.root / '.tw/local/tasks').glob('*/requests/*/context.json'))
        for label in ('角色', '初始状态', '步骤', '预期', '反例', '验证'):
            raw = (original.replace('- 验证：自动', '- 验证：人工') if label == '验证' else
                   original.replace('- 场景：', '- ' + label + '：内联内容\n- 场景：', 1))
            path = self.root / '.tw/local/invalid-design.md'
            path.write_text(raw)
            line = next(i for i, text in enumerate(raw.splitlines(), 1) if text.startswith('- ' + label + '：'))
            code, rejected = self.call('start', '--task', self.name('task'), '--design', str(path))
            self.assertEqual(code, 1, rejected)
            self.assertEqual(rejected['line'], line)
            self.assertIn('scenarios submit' if label == '验证' else '场景写在场景文件', rejected['problem'])
            if label != '验证':
                self.assertIn('- 场景：', rejected['problem'])
            self.assertEqual(sorted((self.root / '.tw/local/tasks').glob('*/requests/*/context.json')), before)

    def test_added_scenario_is_the_only_new_pending_entry(self):
        self.prepare()
        self.assertEqual(self.submit(self.all_results())[0], 0)
        added = copy.deepcopy(self.scenarios['sops'][0]['scenarios'][0])
        added.update(id='S-ADDED', title='补充遗漏的场景')
        self.scenarios['sops'][0]['scenarios'].append(added)
        self.save_scenarios()
        current = self.pending()
        self.assertEqual([(row['id'], row['reason']) for row in current['pending']], [('S-ADDED', 'new')])
        self.assertEqual(current['summary_counts']['passed'], 4)
