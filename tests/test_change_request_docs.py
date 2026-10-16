"""Approved v3 entry points remain discoverable in the shipped team instructions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/team-workflow'


class ChangeRequestDocs(unittest.TestCase):
    def test_status_records_and_successfully_submitted_reviews_are_documented(self):
        text = (SKILL / 'references/contracts.md').read_text()
        for rule in ('业务结论以新的 accept 为准', '评审在成功提交后计为完成'):
            self.assertIn(rule, text)
        delivery = (SKILL / 'references/team-delivery.md').read_text()
        self.assertIn('(contracts.md#进度恢复与统计)', delivery)

    def test_close_note_guidance_covers_one_platform_owner_and_a_directed_agent_within_existing_length(self):
        lengths = []
        for name in ('SKILL.md', 'references/team-delivery.md', 'references/contracts.md', 'references/coordination.md'):
            with self.subTest(name=name):
                text = (SKILL / name).read_text()
                lengths.append(len(text))
                if name == 'references/coordination.md':
                    for token in ('一位平台负责人', '本人或其指挥的代理', '无须另行负责的共享仓库', '无跨服务风险'):
                        self.assertTrue(token in text, name + ' must document ' + token)
                elif name == 'SKILL.md':
                    self.assertIn('(references/team-delivery.md)', text)
                else:
                    self.assertIn('(coordination.md#单人任务的收尾说明)', text)
        self.assertLessEqual(sum(lengths[1:]), 29055)
        self.assertLessEqual(lengths[0], 2499)

    def test_revision_and_platform_submission_contracts_are_documented_within_budget(self):
        for name in ('references/designs.md', 'references/contracts.md'):
            with self.subTest(name=name):
                text = (SKILL / name).read_text()
                self.assertIn('revision', text)
                self.assertIn('--from-platform', text)
        text = (SKILL / 'references/platform.md').read_text()
        for token in ('change', 'review', '绑定区', '变更请求描述'):
            self.assertIn(token, text)
        self.assertLessEqual(len(text), 3000)

    def test_simple_platform_delivery_and_design_first_draft_convention_are_discoverable(self):
        for name in ('SKILL.md', 'references/team-delivery.md'):
            with self.subTest(name=name):
                text = (SKILL / name).read_text()
                tokens = ('start', 'run', 'deliver', '变更请求')
                if name == 'references/team-delivery.md':
                    tokens += ('草稿变更请求',)
                for token in tokens:
                    self.assertIn(token, text)
                self.assertIn('designs.md#内容与依赖', text)
                if name == 'references/team-delivery.md':
                    design = (SKILL / 'references/designs.md').read_text()
                    for token in ('中等、复杂任务', '草稿变更请求', '获批后实施'):
                        self.assertIn(token, design)
                self.assertIn('--from-platform', text)
                if name == 'SKILL.md':
                    self.assertLessEqual(len(text), 2500)


if __name__ == '__main__':
    unittest.main()
