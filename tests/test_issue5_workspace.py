"""工作区清单只由检出目录内的忽略规则决定。"""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from tw_runtime import gitutil
from common import snapshot
import knowledge
import portable
import validation


class WorkspaceInventory(unittest.TestCase):
    setUp, git = fixtures.WorkflowCases.setUp, fixtures.WorkflowCases.git

    def test_inventory_and_changed_paths_follow_checkout_rules_across_xdg_environments(self):
        self.git('remote', 'add', 'origin', 'https://github.com/acme/orders.git')
        (self.root / '.gitignore').write_text('__pycache__/\nproject.local\n')
        (self.root / '.git/info/exclude').write_text('checkout.local\n')
        for name in ('global.local', 'project.local', 'checkout.local'):
            (self.root / name).write_text('本机内容\n')
        entry = self.root / '.tw/lessons/global.md'
        entry.parent.mkdir(parents=True)
        entry.write_text('待整理的教训\n')
        states = []
        for name, rules in [('xdg-with-ignore', 'global.local\n.tw/lessons/global.md\n'), ('xdg-empty', '')]:
            config = Path(self.tmp.name).parent / (self.root.name + '-' + name)
            config.mkdir()
            self.addCleanup(__import__('shutil').rmtree, config)
            (config / 'git').mkdir()
            (config / 'git/ignore').write_text(rules)
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(config), GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1'):
                states.append({
                    'digest': validation.source_digest(self.root, self.profile),
                    'paths': validation.changed_paths(self.root, self.task, self.profile),
                    'files': snapshot(self.root, self.profile)['files'],
                    'knowledge': knowledge.changed_since(self.root, self.task['base']),
                    'portable': portable.source_state(self.root, self.profile),
                    'runtime': gitutil.files(self.root),
                    'dirty': gitutil.dirty_paths(self.root),
                    'changed': gitutil.changed_since_ref(self.root, self.task['base']),
                    'ignored': gitutil.ignored(self.root, 'global.local'),
                })
        self.assertEqual(states[0], states[1])
        for key in ('paths', 'files', 'runtime', 'dirty', 'changed'):
            self.assertIn('global.local', states[0][key])
            self.assertNotIn('project.local', states[0][key])
            self.assertNotIn('checkout.local', states[0][key])
        self.assertFalse(states[0]['ignored'])
        self.assertEqual(states[0]['knowledge'], {'.tw/lessons/global.md'})
