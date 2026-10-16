"""场景引用从工作区或方案的同一提交读取。"""
import copy
import json
import unittest
from pathlib import Path
import test_scenarios as fixtures
from test_designs import example
from common import Invalid
import design_files
import designs


class ScenarioDesignCases(unittest.TestCase):
    setUp, git, call, save = fixtures.ScenarioCases.setUp, fixtures.ScenarioCases.git, fixtures.ScenarioCases.call, fixtures.ScenarioCases.save
    def test_reference_binding_roundtrip_and_content_change(self):
        value = example('simple')
        # 用当前场景引用格式构造输入，旧实现应在 render 处失败。
        for row in value['sections']:
            if row['type'] == 'acceptance':
                row['data'].pop('scenario', None)
                row['data']['sources'] = [{'ref': '合成依据', 'version': '1', 'confirmed_by': '乙'}]
                row['data']['scenarios'] = [{'path': 'scenarios.json', 'sha256': '0' * 64, 'nodes': ['S']}]
        from test_scenarios import scenario_file
        path = self.save(scenario_file())
        raw = designs.render(value)
        self.assertIn('- 场景：scenarios.json#S', raw)
        design_path = self.root / 'design.md'
        design_path.write_text(raw)
        before = design_files.read(design_path)
        self.assertEqual(designs.load(designs.render(before), scenario_reader=design_files.scenario_reader(self.root)), before)
        self.assertEqual(before['sections'][3]['data']['scenarios'][0]['sha256'], __import__('common').sha(path))
        revision = self.git('rev-parse', 'HEAD').strip()
        self.git('add', 'design.md', 'scenarios.json', '.tw/config.json')
        self.git('commit', '-qm', '合成方案与场景')
        commit = self.git('rev-parse', 'HEAD').strip()
        import hashlib
        ref = {'id': value['id'], 'revision': 1, 'repository': 'github.com/example/source',
               'path': 'design.md', 'commit': commit, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}
        self.git('remote', 'add', 'origin', 'https://github.com/example/source.git')
        changed = scenario_file()
        changed['sops'][0]['scenarios'][0]['regression'] = {'pending': 'ISSUE-2'}
        self.save(changed)
        after = design_files.read(design_path)
        self.assertNotEqual(designs.fingerprints(before)['sections']['A1'], designs.fingerprints(after)['sections']['A1'])
        frozen, _ = design_files.source(self.root, ref)
        self.assertEqual(frozen, before)
        self.assertNotEqual(revision, commit)

    def test_retired_labels_are_explicit_errors_even_before_current_labels(self):
        value = example()
        raw = designs.render(value)
        for label in ('角色', '初始状态', '步骤', '预期', '反例'):
            changed = raw.replace('<!-- tw-section id=A1 type=acceptance depends=api-1 -->',
                                  '<!-- tw-section id=A1 type=acceptance depends=api-1 -->\n- ' + label + '：合成内容')
            number = next(i for i, line in enumerate(changed.splitlines(), 1) if line == '- ' + label + '：合成内容')
            with self.subTest(label=label), self.assertRaisesRegex(Invalid, f'第 {number} 行.*场景写在场景文件'):
                designs.load(changed, scenario_reader=design_files.scenario_reader(self.root))

    def test_missing_node_or_invalid_file_rejects_design(self):
        from test_scenarios import scenario_file
        self.save(scenario_file())
        value = example()
        raw = designs.render(value)
        # 读取点按仓内路径解析，错误应定位场景标签。
        raw = raw.replace('tests/fixtures/scenarios.json#SYNTH-01', 'scenarios.json#missing')
        with self.assertRaisesRegex(Invalid, 'missing'):
            designs.load(raw, scenario_reader=design_files.scenario_reader(self.root))

    def test_publication_uses_scenarios_in_design_commit(self):
        self.save(fixtures.scenario_file())
        value = __import__('test_designs').example('simple')
        for row in value['sections']:
            if row['type'] == 'acceptance':
                row['data']['scenarios'] = [{'path': 'scenarios.json', 'sha256': '0' * 64, 'nodes': ['S']}]
        path = self.root / 'design.md'
        path.write_text(designs.render(value))
        self.git('remote', 'add', 'origin', 'https://github.com/example/source.git')
        self.git('add', 'design.md', 'scenarios.json', '.tw/config.json')
        self.git('commit', '-qm', '合成固定版本')
        changed = fixtures.scenario_file()
        changed['sops'][0]['scenarios'][0]['expected'] = ['工作区的新结果']
        self.save(changed)
        current = design_files.read(path)
        with self.assertRaisesRegex(Invalid, '场景'):
            design_files.publication(self.root, path, current)
