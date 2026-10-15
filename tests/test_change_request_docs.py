"""Approved v3 entry points remain discoverable in the shipped team instructions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/team-workflow'


class ChangeRequestDocs(unittest.TestCase):
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
                for token in ('start', 'run', 'deliver', '变更请求', '草稿变更请求', '团队约定', '工具不强制'):
                    self.assertIn(token, text)
                self.assertIn('--from-platform', text)
                if name == 'SKILL.md':
                    self.assertLessEqual(len(text), 2500)


if __name__ == '__main__':
    unittest.main()
