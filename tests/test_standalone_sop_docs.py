"""TW-SOP-1 SOP-03：独立验证的采用说明、决策记录与安装要求。"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / 'skills/team-workflow/references'


class StandaloneSopDocs(unittest.TestCase):
    def test_scenario_guide_points_to_onboarding_and_onboarding_lists_adoption(self):
        scenarios = (GUIDES / 'scenarios.md').read_text(encoding='utf-8')
        self.assertIn('未接入团队流程的项目见[接入指南](onboarding.md)的独立验证方式', scenarios)
        onboarding = (GUIDES / 'onboarding.md').read_text(encoding='utf-8')
        line = next(text for text in onboarding.splitlines() if 'sop-verify' in text)
        for words in ('praxis-skills', '同一场景格式', 'sop-board', 'acceptance_entries', 'tw team scenarios submit'):
            self.assertIn(words, line)

    def test_decision_records_ownership_and_handshake(self):
        decision = (ROOT / '.tw/decisions/2026-10-19-standalone-sop-verification.md').read_text(encoding='utf-8')
        for words in ('`sop-verify` 归 praxis-skills', '看板归 sop-board', 'sop-board 的 `docs/proposals/`',
                      '场景文件与结果 JSONL 两种格式', '格式只加字段', 'team-workflow 不依赖另外两个仓库的代码'):
            self.assertIn(words, decision)

    def test_install_steps_keep_praxis_and_board_optional(self):
        install = '\n'.join((ROOT / name).read_text(encoding='utf-8')
                            for name in ('README.md', 'docs/install.md', 'skills/team-workflow/SKILL.md'))
        for command in re.findall(r'npx skills add [^\n`]+', install):
            self.assertNotIn('praxis-skills', command)
            self.assertNotIn('sop-board', command)
        onboarding = (GUIDES / 'onboarding.md').read_text(encoding='utf-8')
        line = next(text for text in onboarding.splitlines() if 'sop-verify' in text)
        self.assertIn('可选', line)


if __name__ == '__main__':
    unittest.main()
