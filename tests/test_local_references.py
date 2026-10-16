"""A3: committed knowledge and original documents cannot depend on local material."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from tw_fixtures import Case, entry, git, tree_state, write


class LocalReferences(Case):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'config-home')})
        environment.start()
        self.addCleanup(environment.stop)
        self.initialize()

    def register(self, source='self:docs/original.md'):
        path = self.root / '.tw/config.json'
        config = json.loads(path.read_text())
        config['documents'] = [{'id': 'original', 'title': '原文', 'source': source}]
        path.write_text(json.dumps(config))

    def test_a3_check_rejects_local_material_in_entries_and_registered_documents(self):
        write(self.root, '.tw/rules/evidence.md', entry(
            '证据结论', '结论依据 `.tw/local/batch0/x`。', scope=['self:README.md'],
            source=['s'], verified=self.verified()))
        write(self.root, 'docs/original.md', '# 原文\n结论依据 `.tw/local/migration/report.md`。\n')
        write(self.root, 'docs/unregistered.md', '# 未登记\n.tw/local/manual/report.md\n')
        self.register()
        before = tree_state(self.root)
        code, report = self.tw_json('check')
        self.assertEqual(code, 1, report)
        self.assertEqual({row['path'] for row in report['errors']},
                         {'.tw/rules/evidence.md', 'docs/original.md'})
        messages = '\n'.join(row['message'] for row in report['errors'])
        self.assertIn('.tw/local/batch0', messages)
        self.assertIn('.tw/local/migration', messages)
        self.assertEqual(tree_state(self.root), before)

    def test_a3_managed_layouts_and_bare_local_root_are_allowed(self):
        layout = """.tw/local/
.tw/local/tasks/<身份>/
.tw/local/batches/<批次>/
.tw/local/imports/<材料>/
.tw/local/validation-active/<进程>.json
.tw/local/agents/<台账>.json
.tw/local/cache/changes.json
.tw/local/repositories.json
.tw/local/**
"""
        write(self.root, '.tw/rules/layout.md', entry('本机布局', layout, scope=['self:README.md'],
                                                    source=['s'], verified=self.verified()))
        write(self.root, 'docs/original.md', layout)
        self.register()
        code, report = self.tw_json('check')
        self.assertEqual((code, report['errors']), (0, []), report)

    def test_a3_cached_check_reads_staged_entries_and_originals(self):
        name = '.tw/rules/evidence.md'
        write(self.root, name, entry('本机证据', '已提交结论。', scope=['self:README.md'],
                                     source=['s'], verified=self.verified()))
        write(self.root, 'docs/original.md', '# 已提交结论\n')
        self.register()
        git(self.root, 'add', '-A')
        write(self.root, name, entry('本机证据', '.tw/local/batch0/x', scope=['self:README.md'],
                                     source=['s'], verified=self.verified()))
        write(self.root, 'docs/original.md', '.tw/local/batch0/x\n')
        self.assertEqual(self.tw_json('check', '--cached')[0], 0)
        self.assertEqual(self.tw_json('check')[0], 1)
        git(self.root, 'add', '-A')
        write(self.root, name, entry('本机证据', '已修正结论。', scope=['self:README.md'],
                                     source=['s'], verified=self.verified()))
        write(self.root, 'docs/original.md', '# 已修正结论\n')
        self.assertEqual(self.tw_json('check')[0], 0)
        code, report = self.tw_json('check', '--cached')
        self.assertEqual(code, 1, report)
        self.assertEqual({row['path'] for row in report['errors']}, {name, 'docs/original.md'})

    def test_a3_release_checks_unregistered_docs(self):
        from tw_runtime import install
        repository = Path(__file__).resolve().parents[1]
        target = self.base / 'release'
        def ignore(directory, names):
            return {name for name in names if name in {'.git', '__pycache__', 'dist'}
                    or (Path(directory).name == '.tw' and name == 'local')}
        shutil.copytree(repository, target, ignore=ignore)
        for name in ('team-knowledge', 'team-workflow'):
            skill = target / 'skills' / name
            (skill / 'MANIFEST.json').write_text(json.dumps(install.manifest(skill)))
        # Plain text avoids the existing broken-Markdown-link check catching this defect.
        write(target, 'docs/local-reference.md', '# 证据\n参见 `.tw/local/batch0/x`。\n')
        spec = importlib.util.spec_from_file_location('local_state_release_check', repository / 'scripts/check_release.py')
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        with self.assertRaisesRegex(AssertionError, 'docs/local-reference.md'):
            release.check(target)
