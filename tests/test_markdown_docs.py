"""P6: the shipped authoring guide and all entry points name the current source format."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MarkdownDocumentationCases(unittest.TestCase):
    def test_authoring_entrypoints_use_markdown(self):
        base = ROOT / 'skills/team-workflow'
        for name in ('SKILL.md', 'references/designs.md', 'references/contracts.md', 'references/team-delivery.md', 'references/onboarding.md'):
            with self.subTest(name=name):
                value = (base / name).read_text()
                self.assertNotIn('design.json', value)
        value = (base / 'references/designs.md').read_text()
        for label in ('需求级验收', '初始状态', '隔离依据', '前置任务', '确认依据', 'tw-issues', 'tw-section', 'tw-record'):
            self.assertIn(label, value)
        self.assertFalse((base / 'templates/design.json').exists())
        self.assertTrue((base / 'templates/design.md').is_file())
