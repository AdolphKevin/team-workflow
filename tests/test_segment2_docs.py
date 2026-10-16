"""Distributed examples describe the same written task and approval contracts as the CLI."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / 'skills/team-workflow/references'


class Segment2Docs(unittest.TestCase):
    def test_scenario_guide_covers_entries_evidence_incremental_runs_and_retest_tools(self):
        text = (REFERENCES / 'scenarios.md').read_text()
        for heading in ('1. 场景文件', '2. 验收入口', '3. 三种交付形态', '4. 用例导入与覆盖',
                        '5. 执行与提交', '6. 增量验收', '7. 复测看板契约与搭建'):
            with self.subTest(heading=heading):
                self.assertIn('## ' + heading, text)
        for token in ('../templates/scenarios.yaml', 'acceptance_entries', 'verify', 'regression',
                      'initial_state', 'steps', 'expected', 'forbidden_effects',
                      'scenarios pending', '--format json', 'scenarios submit',
                      'scenario', 'status', 'actual', 'evidence', 'executed_at', 'executor',
                      'session', 'finding', 'note', '仓库外或 `.tw/local/`',
                      '真实账号由用户在真实浏览器登录', '临时 `HOME`',
                      'test-capability.md#75-模型与智能体输出', '转换脚本', '缺陷链接', 'context'):
            with self.subTest(token=token):
                self.assertIn(token, text)
        self.assertLessEqual(len(text), 5000)
        import importlib.util
        spec = importlib.util.spec_from_file_location('scenario_release_check', ROOT / 'scripts/check_release.py')
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        self.assertEqual(release.TEAM_BUDGETS['references/scenarios.md'], 5000)

    def test_evidence_definition_and_authoring_entrypoints_use_scenario_rounds(self):
        standard = (REFERENCES / 'business-acceptance.md').read_text()
        self.assertIn('- 场景证据：场景轮次中每条场景的实际结果与证据文件', standard)
        self.assertIn('由独立执行者经声明的验收入口留下', standard)
        self.assertIn('验收使用的平台评审保留实际作者与原文', standard)
        self.assertIn('应沉淀的场景尚未自动化', standard)
        self.assertIn('沉淀后把检查与用例写回场景的 `regression`', standard)
        self.assertNotIn('人工观察记录', standard)
        for name in ('business-acceptance.md', 'onboarding.md', 'platform.md'):
            with self.subTest(name=name):
                self.assertIn('scenarios.md' if name != 'platform.md' else 'business-acceptance.md#1-术语',
                              (REFERENCES / name).read_text())
        delivery = (ROOT / 'skills/team-workflow/templates/business-delivery.md').read_text()
        self.assertIn('scenarios.md#5-执行与提交', delivery)
        self.assertIn('场景编号 | 状态 | 实际结果与证据位置', delivery)

    def test_tester_confirmed_cases_and_quality_metrics_have_explicit_sources(self):
        capability = (REFERENCES / 'test-capability.md').read_text()
        self.assertIn('经测试同事评审过的用例集是已确认的业务依据，确认人是该测试同事', capability)
        self.assertIn('有歧义时以测试同事的理解为准', capability)
        self.assertIn('`regression.pending`', capability)
        self.assertIn('scenarios.md#1-场景文件', capability)
        self.assertNotIn('pending-automation', capability)
        standard = (REFERENCES / 'business-acceptance.md').read_text()
        self.assertIn('质量结论来自实际交付与缺陷案例', standard)
        self.assertIn('一次通过率描述研发自测后交给测试的版本质量，按轮次与样本量记录', standard)
        weekly = (ROOT / 'skills/team-workflow/templates/weekly-quality-review.md').read_text()
        self.assertIn('提测质量指标', weekly)
        self.assertIn('scenarios.md#5-执行与提交', weekly)

    def test_portable_usage_links_definitions_and_keeps_function_signatures_in_code(self):
        text = (REFERENCES / 'portable.md').read_text()
        self.assertIn('business-acceptance.md#1-术语', text)
        self.assertIn('contracts.md#工具做什么', text)
        for name in ('capture', 'import_result', 'validate_import', 'aggregate'):
            with self.subTest(name=name):
                self.assertNotIn(name + '(', text)

    def test_linking_guidance_keeps_description_for_design_and_relations_in_script(self):
        text = (REFERENCES / 'onboarding.md').read_text()
        self.assertIn('变更请求描述只展示方案原文', text)
        self.assertIn('由项目平台脚本识别', text)
        self.assertIn('例如在 Issue 正文中写变更请求地址', text)
        self.assertNotIn('（如正文写 `Closes #N`）', text)

    def test_task_template_and_references_describe_ids_pending_selection_and_file_urls(self):
        template = json.loads((ROOT / 'skills/team-workflow/templates/task.json').read_text())
        self.assertEqual(template['acceptance'], [{'id': 'A1'}])
        contracts = (REFERENCES / 'contracts.md').read_text()
        self.assertIn('验收项只写编号，内容以方案为准', contracts)
        self.assertNotIn('平台任务块须写全', contracts)
        self.assertIn('pending_sections', contracts)
        designs = (REFERENCES / 'designs.md').read_text()
        self.assertIn('--sections A3,T2', designs)
        self.assertIn('--sections all', designs)
        self.assertIn('没有需要批准的章节', designs)
        self.assertIn('deletion_ids', designs)
        platform = (REFERENCES / 'platform.md').read_text()
        self.assertIn('file-url', platform)
        self.assertIn('--path', platform)
        self.assertIn('http(s)', platform)
        delivery = (REFERENCES / 'team-delivery.md').read_text()
        self.assertIn('待确认章节', delivery)
