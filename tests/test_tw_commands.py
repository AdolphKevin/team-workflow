"""`tw init`, `new`, `read`, `audit` and `version`."""
import json
import unittest

from tw_fixtures import Case, commit, entry, tree_state, write
from tw_runtime import install


class Init(Case):
    def test_preview_writes_nothing_and_apply_creates_three_files(self):
        before = tree_state(self.root)
        code, result = self.tw_json('init')
        self.assertEqual(code, 0)
        self.assertEqual([a['action'] for a in result['actions']], ['create'] * 3)
        self.assertEqual(tree_state(self.root), before)
        self.tw('init', '--apply')
        created = sorted(set(tree_state(self.root)) - set(before))
        self.assertEqual(created, ['.tw/.gitignore', '.tw/config.json', '.tw/overview.md'])
        config = json.loads((self.root / '.tw/config.json').read_text())
        self.assertEqual(config, {'format': 'channelwill/team-workflow', 'data_version': 1,
                                  'project': {'id': 'github.com/acme/orders', 'name': 'orders'}})
        self.assertEqual(self.tw_json('init')[1]['summary'], '已是最新，无需写入')

    def test_guidance_blocks_keep_user_content(self):
        write(self.root, 'AGENTS.md', '# 项目规则\n\n用户自己的规则。\n')
        write(self.root, 'CLAUDE.md', '@AGENTS.md\n')
        self.tw('init', '--apply', '--guidance')
        agents = (self.root / 'AGENTS.md').read_text()
        self.assertTrue(agents.startswith('# 项目规则\n\n用户自己的规则。\n\n<!-- team-workflow:guidance:knowledge start -->'))
        block = agents.split('<!-- team-workflow:guidance:knowledge start -->')[1].split('<!-- team-workflow:guidance:knowledge end -->')[0]
        self.assertLessEqual(len(block.strip()), 400)
        self.assertEqual((self.root / 'CLAUDE.md').read_text(), '@AGENTS.md\n')
        actions = {a['path']: a['action'] for a in self.tw_json('init', '--guidance')[1]['actions']}
        self.assertEqual(actions['AGENTS.md'], 'unchanged')

    def test_existing_relative_import_of_agents_is_respected(self):
        write(self.root, 'CLAUDE.md', '# 导入通用标准\n@./AGENTS.md\n')
        self.tw('init', '--apply', '--guidance')
        self.assertEqual((self.root / 'CLAUDE.md').read_text(), '# 导入通用标准\n@./AGENTS.md\n')

    def test_claude_rules_are_kept_and_the_import_block_does_not_claim_them(self):
        write(self.root, 'CLAUDE.md', '# Claude 专属规范\n\n提交前运行 make lint。\n')
        self.tw('init', '--apply', '--guidance')
        text = (self.root / 'CLAUDE.md').read_text()
        self.assertTrue(text.startswith('# Claude 专属规范\n\n提交前运行 make lint。\n'))
        block = text.split('<!-- team-workflow:guidance:claude start -->')[1].split('<!-- team-workflow:guidance:claude end -->')[0]
        self.assertIn('@AGENTS.md', block)
        self.assertNotIn('只做引用', block)
        self.assertNotIn('不另写规则', block)

    def test_partial_own_layout_is_completed(self):
        write(self.root, '.tw/.gitignore', 'local/\n')
        write(self.root, '.tw/local/repositories.json', '{}')
        code, result = self.tw_json('init', '--apply')
        self.assertEqual(code, 0, result)
        self.assertEqual({a['path']: a['action'] for a in result['actions']},
                         {'.tw/config.json': 'create', '.tw/.gitignore': 'unchanged', '.tw/overview.md': 'create'})

    def test_refuses_a_foreign_tw_directory(self):
        write(self.root, '.tw/config.json', '{"format": "someone-else"}')
        code, _, err = self.tw('init', '--apply')
        self.assertEqual(code, 2)
        self.assertIn('拒绝接管', err)
        write(self.root, '.tw/config.json', '')
        (self.root / '.tw/config.json').unlink()
        write(self.root, '.tw/state.yaml', 'x: 1\n')
        self.assertIn('拒绝接管', self.tw('init')[2])


class New(Case):
    def test_skeleton_is_flagged_until_filled(self):
        self.initialize()
        code, result = self.tw_json('new', 'lesson', '--slug', 'placeholder-leak', '--title', '占位符被提交',
                                    '--scope', 'self:internal/**', '--source', 'https://x/1', '--verified-at-head')
        self.assertEqual(code, 0)
        path = self.root / result['path']
        self.assertRegex(result['path'], r'^\.tw/lessons/\d{4}-\d{2}-\d{2}-placeholder-leak\.md$')
        self.assertIn(f'"commit": "{self.head}"', path.read_text())
        self.assertTrue(any('残留占位' in e['message'] for e in self.tw_json('check')[1]['errors']))
        code, _, err = self.tw('new', 'lesson', '--slug', 'placeholder-leak', '--title', '占位符被提交',
                               '--scope', 'self:internal/**', '--source', 'https://x/1')
        self.assertEqual((code, '已存在' in err), (2, True))

    def test_rejects_bad_arguments(self):
        self.initialize()
        self.assertIn('slug', self.tw('new', 'rule', '--slug', 'Bad_Slug', '--title', 't', '--scope', 'self:a', '--source', 's')[2])
        self.assertIn('--scope', self.tw('new', 'rule', '--slug', 'ok', '--title', 't', '--scope', '../x', '--source', 's')[2])
        self.assertIn('只用于 decision', self.tw('new', 'rule', '--slug', 'ok', '--title', 't', '--scope', 'self:a',
                                              '--source', 's', '--status', 'rejected')[2])


class Read(Case):
    def setUp(self):
        super().setUp()
        self.initialize()
        write(self.root, 'docs/adr/0001-a.md', '# A\n\n## 背景\n原因。\n\n## 决定\n做法。\n')
        write(self.root, 'docs/adr/0002-b.md', '# B\n')
        config = (self.root / '.tw/config.json').read_text()
        write(self.root, '.tw/config.json', config.rstrip().rstrip('}') + ', "documents": ['
              '{"id": "adr", "title": "架构决策", "source": "self:docs/adr/*.md"},'
              '{"id": "first", "title": "第一篇", "source": "self:docs/adr/0001-a.md"},'
              '{"id": "prd", "title": "需求", "source": "https://notion.so/x"}]}\n')
        commit(self.root, 'docs')

    def test_documents_entries_and_sections(self):
        self.assertIn('- adr：架构决策（self:docs/adr/*.md）', self.tw('read', '--list')[1])
        self.assertIn('- self:docs/adr/0001-a.md\n- self:docs/adr/0002-b.md', self.tw('read', 'adr')[1])
        self.assertEqual(self.tw('read', 'first', '--section', '背景')[1], '## 背景\n原因。\n')
        self.assertIn('加 --online 读取正文', self.tw('read', 'prd')[1])
        self.assertIn('订单服务负责', self.tw('read', 'overview.md')[1])
        self.assertIn('找不到', self.tw('read', 'rules/none.md')[2])


class AuditAndVersion(Case):
    def test_audit_reports_hotspots_local_usage_and_undecided_truth(self):
        self.initialize()
        write(self.root, '.tw/lessons/2026-10-14-a.md', entry('教训', '现象：A。', scope=['self:internal/orders/**'],
                                                             source=['s'], verified=self.verified()))
        commit(self.root, 'knowledge')
        write(self.root, 'internal/orders/service.go', 'package orders\nfunc Create() { /* v2 */ }\n')
        commit(self.root, 'change')
        write(self.root, '.tw/local/tasks/t1/big.log', 'x' * 10)
        code, report = self.tw_json('audit')
        self.assertEqual(code, 0)
        self.assertEqual(report['change_hotspots'][0]['path'], '.tw/lessons/2026-10-14-a.md')
        self.assertEqual(report['lessons_without_guards'], ['.tw/lessons/2026-10-14-a.md'])
        self.assertEqual(report['local']['files'], 1)
        self.assertIn('未判定', report['business_truth'])

    def test_manifest_integrity(self):
        shipped = json.loads((install.SKILL / install.MANIFEST).read_text())
        self.assertEqual(shipped, install.manifest(), 'skills/team-knowledge/MANIFEST.json is stale; run python3 scripts/package.py --manifest')
        self.assertEqual(install.integrity(install.SKILL)['status'], 'intact')


if __name__ == '__main__':
    unittest.main()
