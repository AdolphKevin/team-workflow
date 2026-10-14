"""`tw brief`: selection, abandoned reminders, budget, drift and shared repositories."""
import importlib.util
from pathlib import Path
import unittest

from tw_fixtures import Case, commit, entry, make_repo, tree_state, write


class Brief(Case):
    def setUp(self):
        super().setUp()
        self.initialize(overview='订单服务负责下单、库存预留和品牌归档。')
        write(self.root, '.tw/rules/order-transaction.md', entry(
            '订单与库存预留共享事务', '订单写入与库存预留必须在同一事务中提交。', scope=['self:internal/orders/**'],
            source=['https://github.com/acme/orders/issues/17'], verified=self.verified(), tags=['下单'],
            symbols=['OrderService.Create'], related=['decisions/2026-10-14-brand-archive.md']))
        write(self.root, '.tw/decisions/2026-10-14-brand-archive.md', entry(
            '归档超期后保留品牌及历史', '超期后永久保留，不提供删除。\n\n## 放弃过的做法\n'
            '- 满 30 天由 Owner 显式永久删除\n  放弃原因：合规要求保留历史\n  来源：旧卡 k-1\n  关键词：永久删除、清理任务',
            scope=['self:internal/brand/**'], source=['s'], status='accepted', tags=['品牌归档']))
        write(self.root, '.tw/decisions/2026-10-14-no-graphql.md', entry(
            '不引入 GraphQL', '团队约定。\n\n## 理由\n接口少，REST 足够。', scope=['self:README.md'], source=['s'],
            status='rejected', tags=['graphql']))
        write(self.root, '.tw/glossary.md', entry(
            '订单上下文', '## Language\n\n**库存预留**:\n下单时锁定的库存。\n_Avoid_: 锁库存', source=['s']))
        self.head2 = commit(self.root, 'knowledge')

    def brief(self, *args):
        code, result = self.tw_json('brief', *args)
        self.assertEqual(code, 0, result)
        return result

    def labels(self, result):
        return [e['label'] for e in result['entries']]

    def test_path_symbol_tag_and_explicit_entry(self):
        self.assertEqual(self.labels(self.brief('--task', 'x', '--path', 'internal/orders/service.go'))[0], 'rules/order-transaction.md')
        self.assertEqual(self.labels(self.brief('--task', 'x', '--symbol', 'OrderService.Create'))[0], 'rules/order-transaction.md')
        self.assertIn('decisions/2026-10-14-brand-archive.md', self.labels(self.brief('--task', 'x', '--tag', '品牌归档')))
        result = self.brief('--task', 'x', '--entry', '.tw/decisions/2026-10-14-no-graphql.md', '--entry', 'rules/missing.md')
        self.assertEqual(self.labels(result), ['decisions/2026-10-14-no-graphql.md'])
        self.assertEqual(result['missing'], ['rules/missing.md'])

    def test_related_expansion_is_one_hop_and_ranked_last(self):
        result = self.brief('--task', 'x', '--path', 'internal/orders/service.go')
        self.assertEqual(self.labels(result), ['rules/order-transaction.md', 'decisions/2026-10-14-brand-archive.md'])
        self.assertEqual(result['entries'][1]['reasons'], ['由 rules/order-transaction.md 关联'])

    def test_abandoned_approach_and_glossary_alias_from_task_text(self):
        result = self.brief('--task', '给品牌增加永久删除功能，并检查锁库存')
        self.assertIn('decisions/2026-10-14-brand-archive.md', self.labels(result))
        self.assertEqual(result['abandoned'], ['decisions/2026-10-14-brand-archive.md'])
        self.assertEqual(result['terms'], ['库存预留'])
        self.assertIn('### 放弃过的做法', result['markdown'])
        self.assertIn('**库存预留**：下单时锁定的库存。（避免：锁库存）', result['markdown'])

    def test_abandoned_approaches_in_lessons_are_reminded_too(self):
        write(self.root, '.tw/lessons/2026-10-14-retry-storm.md', entry(
            '同步重试放大故障', '现象：下游超时后同步重试，请求翻倍。\n\n## 放弃过的做法\n'
            '- 每次失败立即重试三次\n  放弃原因：放大下游故障\n  来源：Issue #9\n  关键词：立即重试',
            scope=['self:internal/orders/**'], source=['https://x/9'], verified=self.verified()))
        result = self.brief('--task', '在下单失败时加上立即重试')
        self.assertIn('lessons/2026-10-14-retry-storm.md', result['abandoned'])
        self.assertEqual(self.tw_json('audit')[1]['abandoned_approaches'], 2)

    def test_short_fragments_of_an_abandoned_head_do_not_trigger_reminders(self):
        write(self.root, '.tw/decisions/2026-10-14-tooling.md', entry(
            '迁移交给代理', '不写脚本。\n\n## 放弃过的做法\n- 重建工具：盘点、暂存、恢复\n  放弃原因：只管最新设计\n  来源：方案\n  关键词：重建工具',
            scope=['self:README.md'], source=['s'], status='accepted'))
        self.assertNotIn('decisions/2026-10-14-tooling.md', self.brief('--task', '恢复两个仓库的独立发布')['abandoned'])
        self.assertIn('decisions/2026-10-14-tooling.md', self.brief('--task', '再做一个重建工具')['abandoned'])

    def test_overview_is_shown_up_to_its_own_limit(self):
        long = '。'.join(['订单服务负责下单、库存预留和品牌归档'] * 40)[:1150]
        write(self.root, '.tw/overview.md', entry('订单服务总览', long, source=['self:README.md']))
        markdown = self.brief('--task', 'x')['markdown']
        self.assertIn(long, markdown)
        self.assertNotIn('总览较长', markdown)

    def test_rejected_decision_shows_only_its_reason(self):
        markdown = self.brief('--task', '要不要引入 graphql')['markdown']
        self.assertIn('## 不引入 GraphQL（已拒绝）\n接口少，REST 足够。', markdown)
        self.assertNotIn('团队约定。', markdown)

    def test_budget_moves_whole_entries_to_the_index(self):
        write(self.root, '.tw/lessons/2026-10-14-long.md', entry(
            '下单时的长教训', '现象：' + '库存不足时重复下单。' * 60, scope=['self:internal/orders/**'], source=['s'],
            verified=self.verified()))
        result = self.brief('--task', '下单与品牌归档', '--path', 'internal/orders/service.go', '--budget', '1000')
        self.assertLessEqual(result['chars'], 1000)
        rendered = [e for e in result['entries'] if e['rendered']]
        indexed = [e for e in result['entries'] if not e['rendered']]
        self.assertTrue(indexed)
        for item in indexed:
            self.assertIn(f'→ {item["label"]}', result['markdown'])
        self.assertTrue(all(e['label'] not in [i['label'] for i in indexed] for e in rendered))
        index_only = self.brief('--task', '下单', '--path', 'internal/orders/service.go', '--index')
        self.assertFalse(any(e['rendered'] for e in index_only['entries']))
        self.assertIn('## 继续阅读', index_only['markdown'])

    def test_drift_counts_commits_in_scope_and_unknown_baselines(self):
        write(self.root, 'internal/orders/service.go', 'package orders\nfunc Create() { /* v2 */ }\n')
        commit(self.root, 'orders change')
        write(self.root, 'internal/brand/archive.go', 'package brand\nfunc Archive() { /* dirty */ }\n')
        statuses = {e['label']: e['status'] for e in self.brief('--task', '下单 品牌归档', '--path', 'internal/orders/service.go')['entries']}
        self.assertEqual(statuses['rules/order-transaction.md'], '核实于 2026-10-14，之后 scope 内有 1 个提交')
        self.assertEqual(statuses['decisions/2026-10-14-brand-archive.md'], '未记录核实基线')
        write(self.root, '.tw/rules/order-transaction.md', entry(
            '订单与库存预留共享事务', '同一事务。', scope=['self:internal/orders/**'], source=['s'],
            verified=self.verified('f' * 40), tags=['下单']))
        statuses = {e['label']: e['status'] for e in self.brief('--task', '下单')['entries']}
        self.assertIn('之后的变化未知', statuses['rules/order-transaction.md'])

    def test_brief_and_audit_write_nothing(self):
        before = tree_state(self.root)
        self.brief('--task', '下单与品牌永久删除', '--path', 'internal/orders/service.go')
        self.assertEqual(self.tw('audit')[0], 0)
        self.assertEqual(tree_state(self.root), before)

    def test_shared_repository_entries_and_checkout_status(self):
        common = make_repo(self.base, 'common', 'https://github.com/acme/common.git')
        write(common, 'protos/brand.proto', 'syntax = "proto3";\n')
        common_head = commit(common, 'init')
        self.tw('init', '--apply', root=common)
        write(common, '.tw/overview.md', entry('公共协议', '跨服务协议。', source=['s']))
        write(common, '.tw/config.json', (common / '.tw/config.json').read_text().rstrip().rstrip('}') +
              ', "shared": {"orders": {"id": "github.com/acme/orders"}}}\n')
        write(common, '.tw/rules/brand-fields.md', entry(
            '品牌协议字段编号不得复用', '删除的字段保留编号。', scope=['self:protos/**', 'orders:internal/brand/**'],
            source=['s'], verified={'self': {'commit': common_head, 'date': '2026-10-14'}}))
        commit(common, 'knowledge')
        config = (self.root / '.tw/config.json').read_text()
        write(self.root, '.tw/config.json', config.rstrip().rstrip('}') + ', "shared": {"common": {"id": "github.com/acme/common"}}}\n')
        result = self.brief('--task', 'x', '--path', 'internal/brand/archive.go', '--repository', f'common={common}')
        self.assertIn('common:rules/brand-fields.md', self.labels(result))
        self.assertIn('无未提交修改', result['repositories']['common']['description'])
        unmapped = self.brief('--task', 'x', '--path', 'internal/brand/archive.go')
        self.assertNotIn('common:rules/brand-fields.md', self.labels(unmapped))
        self.assertEqual(unmapped['repositories']['common']['status'], 'unmapped')

    def test_cache_rebuild_matches_live_computation(self):
        write(self.root, 'internal/orders/service.go', 'package orders\nfunc Create() { /* v2 */ }\n')
        commit(self.root, 'orders change')
        live = self.brief('--task', '下单')['entries']
        code, _, _ = self.tw('cache', '--rebuild')
        self.assertEqual(code, 0)
        self.assertTrue((self.root / '.tw/local/cache/changes.json').is_file())
        self.assertEqual(self.brief('--task', '下单')['entries'], live)
        self.assertEqual(self.tw('cache', '--clear')[0], 0)
        self.assertFalse((self.root / '.tw/local/cache').exists())

    def test_replay_reports_recall_against_expectations(self):
        spec = importlib.util.spec_from_file_location('replay_brief', Path(__file__).resolve().parents[1] / 'scripts/replay_brief.py')
        replay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(replay)
        report = replay.replay(self.root, [
            {'id': 'orders', 'task': '调整下单流程', 'paths': ['internal/orders/service.go'], 'expected': ['rules/order-transaction.md']},
            {'id': 'brand', 'task': '品牌永久删除', 'expected': ['decisions/2026-10-14-brand-archive.md', 'rules/missing.md']},
        ])
        self.assertEqual((report['recall_listed'], report['rows'][1]['missing']), (0.667, ['rules/missing.md']))


if __name__ == '__main__':
    unittest.main()
