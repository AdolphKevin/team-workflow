"""Distributed examples describe the same written task and approval contracts as the CLI."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / 'skills/team-workflow/references'


class Segment2Docs(unittest.TestCase):
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
