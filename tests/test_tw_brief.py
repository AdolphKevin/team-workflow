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

    def test_source_summary_prefers_url_and_read_keeps_all_sources(self):
        long_url = 'https://example.com/' + 'a' * 90
        cases = [
            (['用户确认', 'http://example.com/first', 'https://example.com/second'], 'http://example.com/first 等 3 项'),
            (['确认记录', 'self:README.md'], '确认记录 等 2 项'),
            (['self:README.md'], 'self:README.md'),
            ([long_url], long_url[:80] + '…'),
            (['文' * 81], '文' * 80 + '…'),
            ([], '未写'),
        ]
        for sources, summary in cases:
            with self.subTest(sources=sources):
                write(self.root, '.tw/rules/sources.md', entry(
                    '来源摘要示例', '完整结论。', scope=['self:README.md'], source=sources))
                markdown = self.brief('--task', 'x', '--entry', 'rules/sources.md')['markdown']
                self.assertIn(f'来源：{summary} · 未记录核实基线\n', markdown)
                code, full, err = self.tw('read', 'rules/sources.md')
                self.assertEqual(code, 0, err)
                for source in sources:
                    self.assertIn(source, full)

    def test_path_symbol_tag_and_explicit_entry(self):
        self.assertEqual(self.labels(self.brief('--task', 'x', '--path', 'internal/orders/service.go'))[0], 'rules/order-transaction.md')
        self.assertEqual(self.labels(self.brief('--task', 'x', '--symbol', 'OrderService.Create'))[0], 'rules/order-transaction.md')
        self.assertIn('decisions/2026-10-14-brand-archive.md', self.labels(self.brief('--task', 'x', '--tag', '品牌归档')))
        result = self.brief('--task', 'x', '--entry', '.tw/decisions/2026-10-14-no-graphql.md', '--entry', 'rules/missing.md')
        self.assertEqual(self.labels(result), ['decisions/2026-10-14-no-graphql.md'])
        self.assertEqual(result['missing'], ['rules/missing.md'])

    def test_guard_file_matches_at_scope_tier_with_path_specificity(self):
        write(self.root, '.tw/rules/guarded.md', entry(
            '回滚约束', '失败必须回滚。', scope=['self:internal/orders/**'], source=['s'],
            guards=['self:tests/test_orders.py#test_inventory_rollback', 'check:unit']))
        write(self.root, '.tw/rules/broad.md', entry(
            '测试目录约束', '保持隔离。', scope=['self:tests/**'], source=['s']))
        result = self.brief('--task', 'x', '--path', 'tests/test_orders.py')
        self.assertEqual(self.labels(result)[:2], ['rules/guarded.md', 'rules/broad.md'])
        guarded = result['entries'][0]
        self.assertEqual((guarded['tier'], guarded['reasons']), (1, ['守护测试 tests/test_orders.py']))
        for path in ['tests', 'tests/test_orders.py/child', 'tests/other.py']:
            with self.subTest(path=path):
                self.assertNotIn('rules/guarded.md', self.labels(self.brief('--task', 'x', '--path', path)))
        for guard in ['check:unit', 'self:tests/#test_inventory_rollback',
                      'self:tests/**#test_inventory_rollback', 'self:tests/test_*.py#test_inventory_rollback',
                      'self:tests/test_order?.py#test_inventory_rollback',
                      'self:tests/test_orders.py', 'other:tests/test_orders.py#test_inventory_rollback']:
            with self.subTest(guard=guard):
                write(self.root, '.tw/rules/guarded.md', entry(
                    '回滚约束', '失败必须回滚。', scope=['self:internal/orders/**'], source=['s'], guards=[guard]))
                self.assertNotIn('rules/guarded.md', self.labels(self.brief('--task', 'x', '--path', 'tests/test_orders.py')))
        write(self.root, '.tw/rules/guarded.md', entry(
            '回滚约束', '失败必须回滚。', scope=['self:internal/orders/**'], source=['s'],
            guards=['self:tests#test_inventory_rollback']))
        self.assertNotIn('rules/guarded.md', self.labels(self.brief('--task', 'x', '--path', 'tests')))

    def test_shared_guards_resolve_project_identity_and_keep_self_local(self):
        common = make_repo(self.base, 'common', 'https://github.com/acme/common.git')
        write(common, 'README.md', '公共协议。')
        commit(common, 'init')
        self.initialize(root=common)
        write(common, '.tw/config.json', (common / '.tw/config.json').read_text().rstrip().rstrip('}') +
              ', "shared": {"orders": {"id": "github.com/acme/orders"}}}\n')
        for name, alias in [('consumer', 'orders'), ('own', 'self')]:
            write(common, f'.tw/rules/{name}.md', entry(
                f'约束 {name}', '失败必须回滚。', scope=['self:README.md'], source=['s'],
                guards=[f'{alias}:tests/test_orders.py#test_inventory_rollback']))
        write(self.root, '.tw/config.json', (self.root / '.tw/config.json').read_text().rstrip().rstrip('}') +
              ', "shared": {"common": {"id": "github.com/acme/common"}}}\n')
        result = self.brief('--task', 'x', '--path', 'tests/test_orders.py', '--repository', f'common={common}')
        self.assertEqual(self.labels(result), ['common:rules/consumer.md'])
        self.assertEqual((result['entries'][0]['tier'], result['entries'][0]['reasons']),
                         (1, ['守护测试 tests/test_orders.py']))

    def test_related_expansion_is_one_hop_and_ranked_last(self):
        result = self.brief('--task', 'x', '--path', 'internal/orders/service.go')
        self.assertEqual(self.labels(result), ['rules/order-transaction.md', 'decisions/2026-10-14-brand-archive.md'])
        self.assertEqual(result['entries'][1]['reasons'], ['由 rules/order-transaction.md 关联'])

    def test_related_reverse_expansion_stops_after_one_hop(self):
        write(self.root, '.tw/rules/reverse.md', entry(
            '反向关联', '关联下单规则。', scope=['self:README.md'], source=['s'],
            related=['self:.tw/rules/order-transaction.md']))
        write(self.root, '.tw/rules/two-hop.md', entry(
            '第二跳', '仅关联反向条目。', scope=['self:README.md'], source=['s'], related=['rules/reverse.md']))
        result = self.brief('--task', 'x', '--entry', 'rules/order-transaction.md')
        self.assertEqual(self.labels(result), ['rules/order-transaction.md',
                         'decisions/2026-10-14-brand-archive.md', 'rules/reverse.md'])
        reverse = result['entries'][2]
        self.assertEqual((reverse['tier'], reverse['reasons']), (3, ['与 rules/order-transaction.md 关联']))
        result = self.brief('--task', 'x', '--entry', 'decisions/2026-10-14-brand-archive.md')
        self.assertEqual(self.labels(result), ['decisions/2026-10-14-brand-archive.md', 'rules/order-transaction.md'])

    def test_related_cross_repo_aliases_resolve_in_the_authors_config(self):
        import json
        common = make_repo(self.base, 'common', 'https://github.com/acme/common.git')
        protocol = make_repo(self.base, 'protocol', 'https://github.com/acme/protocol.git')
        for root in [common, protocol]:
            write(root, 'README.md', '公共协议。')
            commit(root, 'init')
            self.initialize(root=root)
        config = json.loads((common / '.tw/config.json').read_text())
        config['shared'] = {'consumer': {'id': 'github.com/acme/orders'},
                            'wire': {'id': 'github.com/acme/protocol'},
                            'unknown': {'id': 'github.com/acme/unknown'}}
        write(common, '.tw/config.json', json.dumps(config))
        write(common, '.tw/rules/bridge.md', entry(
            '跨仓关系', '引用消费者和协议。', scope=['self:README.md'], source=['s'],
            related=['consumer:.tw/rules/order-transaction.md', 'wire:rules/fields.md',
                     'unknown:rules/fields.md', 'protocol:rules/collision.md', 'self:rules/sibling.md']))
        write(common, '.tw/rules/sibling.md', entry(
            '共享仓内关系', '同仓。', scope=['self:README.md'], source=['s']))
        for name in ['fields', 'collision']:
            write(protocol, f'.tw/rules/{name}.md', entry(
                f'字段 {name}', '字段约定。', scope=['self:README.md'], source=['s']))
        config = json.loads((self.root / '.tw/config.json').read_text())
        config['shared'] = {'common': {'id': 'github.com/acme/common'},
                            'protocol': {'id': 'github.com/acme/protocol'}}
        write(self.root, '.tw/config.json', json.dumps(config))
        repos = ['--repository', f'common={common}', '--repository', f'protocol={protocol}']
        forward = self.brief('--task', 'x', '--entry', 'common:rules/bridge.md', *repos)
        self.assertEqual(self.labels(forward), ['common:rules/bridge.md', 'common:rules/sibling.md',
                                               'protocol:rules/fields.md', 'rules/order-transaction.md'])
        for label in ['rules/order-transaction.md', 'protocol:rules/fields.md', 'common:rules/sibling.md']:
            with self.subTest(label=label):
                reverse = self.brief('--task', 'x', '--entry', label, *repos)
                bridge = next((e for e in reverse['entries'] if e['label'] == 'common:rules/bridge.md'), None)
                self.assertIsNotNone(bridge)
                self.assertEqual((bridge['tier'], bridge['reasons']), (3, [f'与 {label} 关联']))
                self.assertNotIn('protocol:rules/collision.md', self.labels(reverse))

    def test_related_expands_from_abandoned_text_seeds(self):
        write(self.root, '.tw/rules/retention.md', entry(
            '历史保留约束', '保留历史。', scope=['self:README.md'], source=['s'],
            related=['decisions/2026-10-14-brand-archive.md']))
        result = self.brief('--task', '清理任务')
        self.assertIn('rules/retention.md', self.labels(result))
        self.assertEqual(next(e for e in result['entries'] if e['label'] == 'rules/retention.md')['tier'], 3)

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

    def test_footer_counts_each_kind_and_names_a_runnable_command(self):
        for index in range(40):
            write(self.root, f'.tw/rules/nav-{index:02}.md', entry(
                f'导航 {index:02}', '完整正文。' * 60, scope=['self:docs/nav.py'], source=['s']))
        args = ['--task', '整理导航', '--path', 'docs/nav.py', '--budget', '2000']
        result = self.brief(*args)
        hidden = sum(not e['listed'] for e in result['entries'])
        self.assertTrue(any(e['rendered'] for e in result['entries']))
        self.assertGreater(hidden, 0)
        self.assertIn(f'（未列出：{hidden} 个条目。用相同的 --task、--path 加 --index 查看）', result['markdown'])
        self.assertNotIn('条未列出', result['markdown'])
        # The footer's advice must work as written: the same arguments plus --index show more entries.
        more = self.brief(*args, '--index')
        self.assertGreater(sum(e['listed'] for e in more['entries']), sum(e['listed'] for e in result['entries']))

    def test_navigation_lists_a_sorted_prefix_and_tracks_visibility(self):
        for index in range(24):
            write(self.root, f'.tw/rules/nav-{index:02}.md', entry(
                f'导航 {index:02}', '完整正文。' * 200, scope=['self:docs/nav.py'], source=['s'], tags=['navigation']))
        result = self.brief('--task', 'x', '--path', 'docs/nav.py', '--tag', 'navigation', '--index', '--budget', '1000')
        markdown = result['markdown']
        self.assertIn('- 导航 00 → rules/nav-00.md（路径 docs/nav.py）\n', markdown)
        self.assertNotIn('；标签', markdown)
        visible = [e for e in result['entries'] if e['listed']]
        self.assertGreater(len(visible), 0)
        self.assertLess(len(visible), 24)
        self.assertEqual([e['label'] for e in visible], [f'rules/nav-{i:02}.md' for i in range(len(visible))])
        self.assertEqual(result['omitted_lines'], 24 - len(visible))
        self.assertIn(f'（未列出：{24 - len(visible)} 个条目。加大 --budget 或用 --entry 查看）', markdown)
        for item in result['entries']:
            self.assertFalse(item['rendered'])
            self.assertEqual(item['listed'], f'→ {item["label"]}（' in markdown)
        self.assertLessEqual(result['chars'], 1000)

    def test_abandoned_navigation_is_truncated_by_whole_lines(self):
        for index in range(30):
            write(self.root, f'.tw/decisions/2026-10-14-old-{index:02}.md', entry(
                f'替代方案 {index:02}', '现行做法。\n\n## 放弃过的做法\n'
                f'- 旧清理方案 {index:02}\n  放弃原因：破坏历史\n  来源：需求记录\n  关键词：旧清理方案',
                scope=['self:docs/old.py'], source=['s'], status='accepted'))
        result = self.brief('--task', '旧清理方案', '--path', 'docs/old.py', '--index', '--budget', '1000')
        self.assertIn('## 曾放弃的方向\n- 旧清理方案 00 — 放弃原因：破坏历史 → decisions/2026-10-14-old-00.md\n', result['markdown'])
        self.assertNotIn('旧清理方案 29 —', result['markdown'])
        self.assertGreater(result['omitted_lines'], 0)
        self.assertLessEqual(result['chars'], 1000)

    def test_missing_and_shared_checkout_take_priority_over_navigation_and_commits(self):
        import json
        config = json.loads((self.root / '.tw/config.json').read_text())
        config['shared'] = {'common': {'id': 'github.com/acme/common'}}
        write(self.root, '.tw/config.json', json.dumps(config))
        for index in range(30):
            write(self.root, f'.tw/rules/nav-{index:02}.md', entry(
                f'导航 {index:02}', '完整正文。' * 200, scope=['self:README.md'], source=['s']))
        write(self.root, 'README.md', '扩充项目说明。')
        commit(self.root, '说明变更' * 100)
        result = self.brief('--task', 'x', '--path', 'README.md', '--entry', 'rules/missing.md', '--index', '--budget', '1000')
        self.assertIn('## 未找到的条目\n- rules/missing.md\n', result['markdown'])
        self.assertIn('## 共享仓\n- common：未配置本机路径', result['markdown'])
        self.assertIn('## 继续阅读', result['markdown'])
        self.assertNotIn('## 相关提交', result['markdown'])
        markdown = result['markdown']
        self.assertLess(markdown.index('## 继续阅读'), markdown.index('## 共享仓'))
        self.assertLess(markdown.index('## 共享仓'), markdown.index('## 未找到的条目'))
        hidden = sum(not e['listed'] for e in result['entries'])
        # README.md has two known commits; both count when their section is omitted.
        self.assertEqual(result['omitted_lines'], hidden + 2)
        self.assertIn(f'（未列出：{hidden} 个条目、2 条相关提交。', markdown)
        self.assertLessEqual(result['chars'], 1000)

    def test_budget_bounds_long_overview_and_task_without_cutting_entry_bodies(self):
        intro = '项目总览。' * 30
        write(self.root, '.tw/overview.md', entry('总览', intro + '\n\n' + '长段落。' * 2000, source=['s']))
        body = '前置条件。\n\n' + '必须全部完成。' * 25 + '\n\n否定条件：库存不足不得提交。'
        write(self.root, '.tw/rules/complete.md', entry(
            '完整约束', body, scope=['self:docs/complete.py'], source=['s']))
        for budget in [1000, 1200, 6000]:
            for task in ['x', '任务描述。' * 3000]:
                with self.subTest(budget=budget, long_task=len(task) > 1):
                    result = self.brief('--task', task, '--path', 'docs/complete.py', '--budget', str(budget))
                    self.assertEqual(result['chars'], len(result['markdown']))
                    self.assertLessEqual(result['chars'], budget)
                    self.assertEqual(result['task'], task)
                    for item in result['entries']:
                        self.assertEqual(item['listed'], f'→ {item["label"]}' in result['markdown'])
                        if item['rendered']:
                            self.assertIn(body, result['markdown'])
                        else:
                            self.assertNotIn('前置条件。', result['markdown'])
                    if task == 'x' and budget == 6000:
                        self.assertIn(intro, result['markdown'])
                        self.assertIn('总览较长', result['markdown'])
                        self.assertTrue(result['entries'][0]['rendered'])

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
        self.tw('init', '--apply', '--source', 'self:protos/brand.proto', root=common)
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
        self.assertEqual((report['recall_full'], report['recall_visible']), (0.667, 0.667))
        self.assertEqual(report['rows'][1]['missing'], ['rules/missing.md'])
        self.assertEqual(report['rows'][0]['index_only'], [])
        self.assertEqual(report['rows'][0]['extra'], ['decisions/2026-10-14-brand-archive.md'])
        self.assertEqual(set(report), {'queries', 'recall_full', 'recall_visible', 'rows'})

    def test_replay_counts_only_visible_entries_and_extras(self):
        spec = importlib.util.spec_from_file_location('replay_brief', Path(__file__).resolve().parents[1] / 'scripts/replay_brief.py')
        replay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(replay)
        for index in range(100):
            write(self.root, f'.tw/rules/nav-{index:02}.md', entry(
                f'导航 {index:02}', '完整正文。' * 200, scope=['self:README.md'], source=['s'], tags=['navigation']))
        report = replay.replay(self.root, [
            {'id': 'navigation', 'task': 'navigation', 'expected': ['rules/nav-00.md', 'rules/nav-99.md']},
        ], budget=1000)
        row = report['rows'][0]
        self.assertEqual(row['missing'], ['rules/nav-99.md'])
        self.assertEqual((report['recall_full'], report['recall_visible']), (0.0, 0.5))
        self.assertEqual(row['index_only'], ['rules/nav-00.md'])
        self.assertIn('rules/nav-01.md', row['extra'])
        self.assertNotIn('rules/nav-98.md', row['extra'])


if __name__ == '__main__':
    unittest.main()
