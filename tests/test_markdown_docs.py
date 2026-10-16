"""P6: the shipped authoring guide and all entry points name the current source format."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MarkdownDocumentationCases(unittest.TestCase):
    def test_current_verification_and_reconciliation_are_documented(self):
        base = ROOT / 'skills/team-workflow'
        template = (base / 'templates/design.md').read_text()
        self.assertIn('- 验证：自动\n', template)
        for name in ('references/designs.md', 'references/contracts.md'):
            value = (base / name).read_text()
            self.assertNotIn('- 验证：自动；层级', value)
            self.assertNotIn('result,coverage,evidence', value)
            self.assertIn('substitutes', value)
        contracts = (base / 'references/contracts.md').read_text()
        designs = (base / 'references/designs.md').read_text()
        delivery = (base / 'references/team-delivery.md').read_text()
        self.assertIn('未指明用例，证据为整项检查通过', contracts)
        self.assertIn('(contracts.md#实施批准与代码评审)', designs)
        self.assertIn('--reconcile', designs)
        self.assertIn('第 1 版', designs)
        self.assertIn('(designs.md#发布与隐藏记录)', delivery)

    def test_scenario_contracts_define_tools_bindings_and_result_flow(self):
        text = (ROOT / 'skills/team-workflow/references/contracts.md').read_text()
        for heading in ('## 工具做什么', '### 记录绑定', '## 场景与证据'):
            self.assertIn(heading, text)
        for token in ('平台只读', '验收材料', '产品指纹', 'acceptance_entries', 'case_imports',
                      'case_coverage', 'scenario_rounds', 'scenarios pending',
                      'scenarios submit', 'executed_at', 'executor', 'first_pass',
                      'regression_pending', '[场景指南](scenarios.md)'):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_authoring_entrypoints_use_markdown(self):
        base = ROOT / 'skills/team-workflow'
        for name in ('SKILL.md', 'references/designs.md', 'references/contracts.md', 'references/team-delivery.md', 'references/onboarding.md'):
            with self.subTest(name=name):
                value = (base / name).read_text()
                self.assertNotIn('design.json', value)
        value = (base / 'references/designs.md').read_text()
        for label in ('需求级验收', '场景', '前置任务', '确认依据', 'tw-issues', 'tw-section', 'tw-record'):
            self.assertIn(label, value)
        contracts = (base / 'references/contracts.md').read_text()
        for field in ('initial_state', 'isolation_evidence'):
            self.assertIn(field, contracts)
        self.assertIn('(contracts.md#场景与证据)', value)
        self.assertFalse((base / 'templates/design.json').exists())
        self.assertTrue((base / 'templates/design.md').is_file())
