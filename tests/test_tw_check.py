"""`tw check`: repository-level structure, ignore rules, references and branch hints."""
import unittest

from tw_fixtures import Case, commit, entry, git, make_repo, tree_state, write


class Check(Case):
    def errors(self, *args):
        code, result = self.tw_json('check', *args)
        return code, [f'{x["path"]}：{x["message"]}' for x in result['errors']], [f'{x["path"]}：{x["message"]}' for x in result['warnings']]

    def test_fresh_init_reports_the_overview_placeholder_only(self):
        self.tw('init', '--apply')
        code, errors, _ = self.errors()
        self.assertEqual(code, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('.tw/overview.md：残留占位内容', errors[0])

    def test_clean_project_passes_and_check_writes_nothing(self):
        self.initialize()
        write(self.root, '.tw/rules/order-transaction.md', entry(
            '订单与库存预留共享事务', '订单写入与库存预留必须在同一事务中提交。', scope=['self:internal/orders/**'],
            source=['https://github.com/acme/orders/issues/17'], verified=self.verified(),
            guards=['self:tests/test_orders.py#test_inventory_rollback']))
        before = tree_state(self.root)
        code, errors, warnings = self.errors()
        self.assertEqual((code, errors, warnings), (0, [], []))
        self.assertEqual(tree_state(self.root), before)

    def test_missing_config_and_legacy_directories(self):
        write(self.root, '.codestable/wiki/INDEX.md', '# old\n')
        write(self.root, '.team-workflow.json', '{}')
        code, errors, _ = self.errors()
        self.assertEqual(code, 1)
        joined = '\n'.join(errors)
        self.assertTrue(any(error.startswith('.tw/config.json：') for error in errors))
        self.assertIn('.codestable：旧系统目录仍存在', joined)
        self.assertIn('.team-workflow.json：旧系统目录仍存在', joined)

    def test_ignore_rules(self):
        self.initialize()
        write(self.root, '.gitignore', '.tw/\n')
        _, errors, _ = self.errors()
        self.assertTrue(any('整个目录被忽略规则覆盖' in e for e in errors))
        write(self.root, '.gitignore', '')
        write(self.root, '.tw/.gitignore', '')
        write(self.root, '.tw/local/cache/x.json', '{}')
        git(self.root, 'add', '-f', '.tw/local/cache/x.json')
        _, errors, _ = self.errors()
        joined = '\n'.join(errors)
        self.assertIn('应包含一行 local/', joined)
        self.assertIn('没有被 git 忽略', joined)
        self.assertIn('有已跟踪的文件', joined)

    def test_scope_guard_related_and_stray_files(self):
        self.initialize()
        write(self.root, '.tw/rules/bad-refs.md', entry(
            '引用错误的规则', '内容。', scope=['self:internal/payments/**', 'billing:api/**'], source=['s'],
            verified=self.verified(), guards=['self:tests/test_orders.py#test_missing', 'check:unit'],
            related=['rules/nope.md']))
        write(self.root, '.tw/decisions/2026-10-14-planned.md', entry(
            '计划中的决策', '还没实现。', scope=['self:internal/payments/**'], source=['s'], status='accepted'))
        write(self.root, '.tw/notes.md', 'stray\n')
        _, errors, warnings = self.errors()
        joined, notes = '\n'.join(errors), '\n'.join(warnings)
        self.assertIn('scope self:internal/payments/** 匹配不到任何文件', joined)
        self.assertIn('未在 config.shared 中声明的仓库：billing', joined)
        self.assertIn('守护测试 test_missing 不在 self:tests/test_orders.py 中', joined)
        self.assertIn('未配置的检查：unit', joined)
        self.assertIn('related 指向不存在的条目：rules/nope.md', joined)
        self.assertIn('.tw/notes.md：不是知识条目', joined)
        self.assertIn('2026-10-14-planned.md：scope self:internal/payments/** 匹配不到任何文件', notes)
        self.assertNotIn('2026-10-14-planned.md', joined)

    def test_scope_can_name_project_files_under_tw_but_not_knowledge_entries(self):
        self.initialize()
        write(self.root, '.tw/platform.py', 'print(1)\n')
        write(self.root, '.tw/rules/tooling.md', entry(
            '项目脚本约束', '内容。', scope=['self:.tw/platform.py', 'self:.tw/config.json'], source=['s'],
            verified=self.verified()))
        write(self.root, '.tw/rules/self-scope.md', entry(
            '指向知识的范围', '内容。', scope=['self:.tw/rules/tooling.md'], source=['s'], verified=self.verified()))
        _, errors, warnings = self.errors()
        joined = '\n'.join(errors + warnings)
        self.assertNotIn('tooling.md：scope', joined)
        self.assertIn('self-scope.md：scope self:.tw/rules/tooling.md 匹配不到任何文件', joined)

    def test_documents_must_exist_and_have_one_owner(self):
        self.initialize()
        write(self.root, 'docs/adr/0001-a.md', '# A\n')
        config = (self.root / '.tw/config.json').read_text()
        write(self.root, '.tw/config.json', config.rstrip().rstrip('}') + ', "documents": ['
              '{"id": "adr", "title": "ADR", "source": "self:docs/adr/*.md"},'
              '{"id": "first-adr", "title": "第一篇", "source": "self:docs/adr/0001-a.md"},'
              '{"id": "prd", "title": "PRD", "source": "https://notion.so/x"},'
              '{"id": "gone", "title": "已删除", "source": "self:docs/missing.md"}]}\n')
        _, errors, _ = self.errors()
        joined = '\n'.join(errors)
        self.assertIn('同一份原文被登记了 2 次（adr, first-adr）', joined)
        self.assertIn('documents gone 的原文不存在', joined)
        self.assertNotIn('prd', joined)

    def test_duplicate_titles_and_lessons_without_guards_warn(self):
        self.initialize()
        for name in ('a', 'b'):
            write(self.root, f'.tw/lessons/2026-10-14-{name}.md', entry(
                '同一个坑', '现象：重复。', scope=['self:internal/**'], source=['s'], verified=self.verified()))
        _, errors, warnings = self.errors()
        self.assertEqual(errors, [])
        joined = '\n'.join(warnings)
        self.assertIn('疑似重复', joined)
        self.assertIn('没有守护测试', joined)

    def test_branch_hint_when_scope_code_changes_without_knowledge(self):
        self.initialize()
        write(self.root, '.tw/rules/order-transaction.md', entry(
            '订单事务', '必须同一事务。', scope=['self:internal/orders/**'], source=['s'], verified=self.verified()))
        base = commit(self.root, 'knowledge')
        write(self.root, 'internal/orders/service.go', 'package orders\nfunc Create() { /* changed */ }\n')
        _, _, warnings = self.errors('--base', base)
        self.assertTrue(any('本分支改动了它的 scope 内代码（internal/orders/service.go）' in w for w in warnings))
        write(self.root, '.tw/rules/order-transaction.md', entry(
            '订单事务', '必须同一事务，并已复核。', scope=['self:internal/orders/**'], source=['s'], verified=self.verified()))
        _, _, warnings = self.errors('--base', base)
        self.assertFalse(any('本分支改动了' in w for w in warnings))

    def test_guidance_that_still_points_at_the_old_cs_warns(self):
        self.initialize()
        write(self.root, 'AGENTS.md', '# 规则\n\n开工前使用独立 CS 读取知识。\n')
        _, errors, warnings = self.errors()
        self.assertEqual(errors, [])
        self.assertTrue(any(w.startswith('AGENTS.md：第 3 行仍要求使用旧 CS') for w in warnings))
        self.tw('init', '--apply', '--guidance')
        write(self.root, 'AGENTS.md', (self.root / 'AGENTS.md').read_text().replace('开工前使用独立 CS 读取知识。', '开工前读取知识。'))
        self.assertFalse(any('旧 CS' in w for w in self.errors()[2]))
        write(self.root, 'AGENTS.md', (self.root / 'AGENTS.md').read_text() + '\n完成后按 CS 规则更新同一逻辑任务。\n')
        self.assertTrue(any('仍要求使用旧 CS' in w for w in self.errors()[2]))

    def test_uninitialized_project_with_legacy_directories_points_at_the_migration_guide(self):
        write(self.root, '.codestable/wiki/INDEX.md', '# old\n')
        code, _, err = self.tw('brief', '--task', 'x')
        self.assertEqual(code, 2)
        self.assertIn('references/migration.md', err)

    def test_cached_checks_the_staged_version(self):
        self.initialize()
        path = '.tw/rules/order-transaction.md'
        write(self.root, path, entry('订单事务', '必须同一事务。', scope=['self:internal/orders/**'], source=['s'], verified=self.verified()))
        git(self.root, 'add', '-A')
        write(self.root, path, entry('订单事务', '__REPLACE__', scope=['self:internal/orders/**'], source=['s'], verified=self.verified()))
        self.assertEqual(self.errors('--cached')[1], [])
        self.assertTrue(any('残留占位' in e for e in self.errors()[1]))

    def test_shared_repository_identity_and_scope(self):
        common = make_repo(self.base, 'common', 'https://github.com/acme/common.git')
        write(common, 'protos/brand.proto', 'syntax = "proto3";\n')
        commit(common, 'init')
        self.initialize()
        config = (self.root / '.tw/config.json').read_text()
        write(self.root, '.tw/config.json', config.rstrip().rstrip('}') + ', "shared": {"common": {"id": "github.com/acme/common"}}}\n')
        write(self.root, '.tw/rules/brand-contract.md', entry(
            '品牌协议字段', '字段编号不得复用。', scope=['common:protos/**'], source=['s'], verified=self.verified()))
        _, errors, warnings = self.errors()
        self.assertEqual(errors, [])
        self.assertTrue(any('未配置本机路径' in w for w in warnings))
        write(self.root, '.tw/local/repositories.json', '{"repositories": {"common": "../common"}}\n')
        _, errors, warnings = self.errors()
        self.assertEqual(errors, [])
        self.assertTrue(any('尚未迁移' in w for w in warnings))
        other = make_repo(self.base, 'other', 'https://github.com/acme/other.git')
        write(other, 'x', 'x')
        commit(other, 'init')
        write(self.root, '.tw/local/repositories.json', '{"repositories": {"common": "../other"}}\n')
        _, errors, _ = self.errors()
        self.assertTrue(any('检出身份不符：期望 github.com/acme/common，实际 github.com/acme/other' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
