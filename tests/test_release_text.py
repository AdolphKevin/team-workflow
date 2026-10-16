"""F13：发布规则来自数据，违反规则时提供文件、行号和可执行报告。"""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_text_entry', ROOT / 'scripts/check_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseText(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        shutil.copytree(ROOT / 'skills', root / 'skills', ignore=shutil.ignore_patterns('__pycache__'))
        return root

    def test_current_skills_have_no_rule_errors(self):
        rows = release.skill_document_checks(ROOT)
        self.assertEqual({r['name'] for r in rows}, {'concepts', 'versions', 'negative-chains', 'links', 'retest-board'})
        self.assertTrue(all(not row['errors'] for row in rows), rows)

    def test_each_violation_reports_its_file_and_line(self):
        for rule, addition in (('concepts', '仅一位平台负责人'), ('concepts', '未指明用例'),
                              ('concepts', '工具不执行关闭'), ('concepts', '团队约定，工具不强制'),
                              ('versions', '兼容旧格式'), ('versions', '第六版'), ('versions', '行为不变'),
                              ('versions', '原行为'), ('versions', '不再读取'),
                              ('negative-chains', '只有获得批准才实施'),
                              ('negative-chains', '没有新的理由前不要重新采用'),
                              ('negative-chains', '回归未完成时，\n整体交付仍未完成。'),
                              ('negative-chains', '缺业务证据时，交付不能完成。'),
                              ('negative-chains', '没有来源时，不应交付。')):
            with self.subTest(rule=rule, addition=addition):
                root = self.fixture()
                path = root / 'skills/team-workflow/references/violation.md'
                path.write_text('# 临时文档\n\n' + addition + '\n')
                rows = release.skill_document_checks(root)
                errors = next(r['errors'] for r in rows if r['name'] == rule)
                self.assertTrue(any(e['path'] == path.relative_to(root).as_posix() and e['line'] == 3 for e in errors), errors)

    def test_link_violation_is_part_of_the_document_group(self):
        root = self.fixture()
        path = root / 'skills/team-workflow/references/violation.md'
        path.write_text('# 链接\n\n[外部正文](../../../outside.md)\n')
        (root / 'outside.md').write_text('正文')
        rows = release.skill_document_checks(root)
        errors = next(r['errors'] for r in rows if r['name'] == 'links')
        self.assertEqual(errors[0]['path'], path.relative_to(root).as_posix())
        self.assertEqual(errors[0]['line'], 3)

    def test_enumerations_and_preserved_guidance_are_not_negative_chains(self):
        root = self.fixture()
        path = root / 'skills/team-workflow/references/nouns.md'
        path.write_text('空输入、对象缺失、权限不足、未执行、未验证。\n- 未参与实现的说明：待填\n- 响应及不应发生的副作用：待填\n- 独立复验人、角色及未参与实现的说明：待填\n- 复验时间、环境、入口：待填\n- 响应及不应发生的副作用：待填\n')
        for name in ('guidance-global.md', 'guidance-project.md'):
            (root / 'skills/team-workflow/templates' / name).write_text('只有批准才实施；不再处理；未检查时，交付未完成。')
        self.assertTrue(all(not r['errors'] for r in release.skill_document_checks(root)))

    def test_missing_condition_with_incomplete_result_is_a_negative_chain(self):
        root = self.fixture()
        path = root / 'skills/team-workflow/references/chain.md'
        path.write_text('第一行\n缺任一项时标记为未完成并列出所缺项。\n应沉淀的回归尚未\n  完成或未实际运行时，交付仍未完成。\n')
        errors = next(r['errors'] for r in release.skill_document_checks(root) if r['name'] == 'negative-chains')
        name = path.relative_to(root).as_posix()
        self.assertEqual([(e['path'], e['line']) for e in errors], [(name, 2), (name, 3)])

    def test_retest_board_rule_covers_project_contract_and_runtime_service_boundary(self):
        root = self.fixture()
        path = root / 'skills/team-knowledge/scripts/tw_runtime/team/board.py'
        path.write_text('# 场景服务\nfrom http.server import HTTPServer\n')
        rows = release.skill_document_checks(root)
        errors = next(r['errors'] for r in rows if r['name'] == 'retest-board')
        self.assertTrue(any(e['path'] == path.relative_to(root).as_posix() and e['line'] == 2 for e in errors))
        path.unlink()
        guide = root / 'skills/team-workflow/references/scenarios.md'
        guide.write_text(guide.read_text().replace('导出结果契约文件与证据目录', '导出内容'))
        rows = release.skill_document_checks(root)
        self.assertTrue(next(r['errors'] for r in rows if r['name'] == 'retest-board'))

    def test_rule_names_and_failure_locations_are_written_to_junit(self):
        import xml.etree.ElementTree as ET
        root = self.fixture()
        path = root / 'skills/team-workflow/references/violation.md'
        path.write_text('# 文档\n\n没有批准前不实施。\n')
        output = root / 'rules.xml'
        release.write_junit(output, release.skill_document_checks(root))
        suite = ET.parse(output).getroot()
        cases = {row.get('classname') + '::' + row.get('name'): row for row in suite.iter('testcase')}
        self.assertIn('SkillDocs::negative-chains', cases)
        self.assertIn('references/violation.md:3', cases['SkillDocs::negative-chains'].find('failure').text)
        self.assertIsNone(cases['SkillDocs::versions'].find('failure'))
