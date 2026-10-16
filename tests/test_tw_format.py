"""Front matter, globs and file-local entry validation."""
import unittest

import tw_fixtures  # noqa: F401  (adds the team-knowledge scripts to sys.path)
from tw_runtime import entries, frontmatter, globs, textmatch


class FrontMatter(unittest.TestCase):
    def test_round_trip_keeps_order_and_unicode(self):
        text = frontmatter.dump({'scope': ['self:a/**'], 'title': '订单'}, '# 订单\n')
        self.assertTrue(text.startswith('---\ntitle: "订单"\nscope: ["self:a/**"]\n---\n'))
        fields, body, errors = frontmatter.parse(text)
        self.assertEqual((fields, body, errors), ({'title': '订单', 'scope': ['self:a/**']}, '# 订单\n', []))

    def test_reports_problems_instead_of_raising(self):
        self.assertIn('第一行', frontmatter.parse('# no header')[2][0])
        _, _, errors = frontmatter.parse('---\ntitle: "a"\ntitle: "b"\nscope: [oops\nbad line\n---\n')
        self.assertTrue(any('重复字段' in e for e in errors))
        self.assertTrue(any('不是合法 JSON' in e for e in errors))
        self.assertTrue(any('字段: JSON值' in e for e in errors))
        self.assertIn('缺少结束行', frontmatter.parse('---\ntitle: "a"\n')[2][-1])


class Globs(unittest.TestCase):
    def test_star_stays_in_one_directory(self):
        self.assertTrue(globs.matches('internal/*.go', 'internal/a.go'))
        self.assertFalse(globs.matches('internal/*.go', 'internal/x/a.go'))
        self.assertTrue(globs.matches('internal/**', 'internal/x/y/a.go'))
        self.assertTrue(globs.matches('**/a.go', 'a.go'))
        self.assertTrue(globs.matches('**/a.go', 'x/y/a.go'))
        self.assertTrue(globs.matches('internal/?.go', 'internal/a.go'))
        self.assertFalse(globs.matches('internal/?.go', 'internal/ab.go'))

    def test_literal_directory_matches_files_below(self):
        self.assertTrue(globs.matches('internal/orders', 'internal/orders/service.go'))
        self.assertFalse(globs.matches('internal/orders', 'internal/orders_old/service.go'))

    def test_invalid_patterns_and_specificity(self):
        for bad in ('/abs', '../x', 'a//b', 'a/**b', 'a/[ab]', 'a\\b', ''):
            self.assertIsNotNone(globs.problem(bad), bad)
        self.assertEqual(globs.split('self:internal/**')[:2], ('self', 'internal/**'))
        self.assertIsNotNone(globs.split('internal/**')[2])
        self.assertGreater(globs.specificity('internal/orders/*.go'), globs.specificity('internal/**'))


class Validation(unittest.TestCase):
    def validate(self, kind, ref, text):
        return entries.validate(entries.load(kind, ref, text))

    def test_valid_rule(self):
        text = '---\ntitle: "规则"\nscope: ["self:a/**"]\nsource: ["https://x/1"]\nverified: {"self": {"commit": "' + 'a' * 40 + '", "date": "2026-10-14"}}\n---\n# 规则\n\n必须这样。\n'
        self.assertEqual(self.validate('rule', 'rules/a-rule.md', text), ([], []))

    def test_required_fields_types_and_unknown_fields(self):
        errors, _ = self.validate('rule', 'rules/a.md', '---\ntitle: "规则"\nfuture_use: []\nscope: "self:a"\n---\n# 规则\n\n内容\n')
        joined = '\n'.join(errors)
        for expected in ('不使用字段：future_use', '缺少必填字段：source', '缺少必填字段：verified', 'scope 必须是非空字符串数组'):
            self.assertIn(expected, joined)

    def test_each_empty_or_mistyped_field_has_one_problem(self):
        from tw_fixtures import entry
        fields = {'scope': ['self:a'], 'source': ['s'], 'verified': {'self': {'commit': None, 'date': '2026-10-16'}}}
        for key in ('scope', 'source', 'verified', 'title'):
            for value in (None, '', [], {}):
                with self.subTest(key=key, value=value):
                    values = {'title': '规则', **fields, key: value}
                    errors, _ = self.validate('rule', 'rules/a.md', entry(values.pop('title'), '完整正文。', **values))
                    matching = [message for message in errors if key in message]
                    self.assertEqual(matching, ['缺少必填字段：' + key])
        for key in ('scope', 'source'):
            for value in ('s', 3, [''], [3]):
                with self.subTest(key=key, value=value):
                    errors, _ = self.validate('rule', 'rules/a.md', entry('规则', '完整正文。', **{**fields, key: value}))
                    self.assertEqual([e for e in errors if key in e], [key + ' 必须是非空字符串数组'])

    def test_title_heading_file_name_and_status(self):
        errors, _ = self.validate('decision', 'decisions/bad_name.md',
                                  '---\ntitle: "决策"\nscope: ["self:a"]\nsource: ["s"]\nstatus: "superseded"\n---\n# 另一个标题\n')
        joined = '\n'.join(errors)
        self.assertIn('YYYY-MM-DD-<slug>.md', joined)
        self.assertIn('status 只能是 accepted 或 rejected', joined)
        self.assertIn('与 title 一致', joined)
        self.assertIn('日期不合法', '\n'.join(self.validate('lesson', 'lessons/2026-13-01-x.md', '---\n---\n')[0]))

    def test_placeholders_are_errors(self):
        for marker in ('__REPLACE__', '（待填写：原因）', 'TODO', '待补充'):
            errors, _ = self.validate('lesson', 'lessons/2026-10-14-x.md',
                                      f'---\ntitle: "教训"\nscope: ["self:a"]\nsource: ["s"]\nverified: {{"self": {{"commit": null, "date": "2026-10-14"}}}}\n---\n# 教训\n\n现象：{marker}\n')
            self.assertTrue(any('残留占位' in e for e in errors), marker)

    def test_abandoned_items_need_reason_and_source(self):
        body = '# 决策\n\n现行做法。\n\n## 放弃过的做法\n- 永久删除\n  放弃原因：合规要求\n- 异步清理\n  重新考虑的条件：无\n'
        errors, _ = self.validate('decision', 'decisions/2026-10-14-d.md',
                                  '---\ntitle: "决策"\nscope: ["self:a"]\nsource: ["s"]\nstatus: "accepted"\n---\n' + body)
        self.assertIn('“放弃过的做法”第 1 项缺少来源', errors)
        self.assertIn('“放弃过的做法”第 1 项缺少关键词', errors)
        self.assertIn('“放弃过的做法”第 2 项缺少放弃原因', errors)
        self.assertIn('“放弃过的做法”第 2 项缺少来源', errors)
        self.assertEqual(entries.abandoned(body)[0], '永久删除\n放弃原因：合规要求')

    def test_size_limits_and_transient_warnings(self):
        errors, _ = self.validate('overview', 'overview.md', '---\ntitle: "总览"\nsource: ["s"]\n---\n# 总览\n\n' + '字' * 1300)
        self.assertTrue(any('超过上限 1200' in e for e in errors))
        _, warnings = self.validate('rule', 'rules/r.md', '---\ntitle: "规则"\nscope: ["self:a"]\nsource: ["s"]\nverified: {"self": {"commit": null, "date": "2026-10-14"}}\n---\n'
                                    '# 规则\n\n本次 436 项测试全部通过；见 service.go:120；CodeStable 2.1.0。\n')
        joined = '\n'.join(warnings)
        for expected in ('一次性的运行结果', '测试计数', '行号锚点', '工具版本'):
            self.assertIn(expected, joined)

    def test_glossary_terms(self):
        terms = entries.glossary_terms('# 上下文\n\n## Language\n\n**库存预留**:\n下单时锁定的库存。\n_Avoid_: 锁库存, 占库存\n\n**品牌**:\n组织下的主体。\n')
        self.assertEqual(terms[0], {'term': '库存预留', 'aliases': ['锁库存', '占库存'], 'text': '下单时锁定的库存。'})
        self.assertEqual(terms[1]['term'], '品牌')


class TextMatch(unittest.TestCase):
    def test_longest_phrase_wins_and_no_bigram_noise(self):
        hits = textmatch.find('调整库存预留逻辑', {'库存预留', '库存', '预留', '品牌'})
        self.assertEqual(hits, {'库存预留'})
        self.assertEqual(textmatch.find('会话语言路由', {'语言回写规则'}), set())

    def test_ascii_phrases_need_word_boundaries(self):
        self.assertEqual(textmatch.find('fix ordering bug', {'order'}), set())
        self.assertEqual(textmatch.find('fix order bug', {'order'}), {'order'})
        self.assertEqual(textmatch.find('ＯＲＤＥＲ', {'order'}), {'order'})

    def test_title_phrases_and_slug_words(self):
        self.assertEqual(textmatch.title_phrases('建会话前确定语言，并使用独立字段保存'), {'建会话前确定语言', '并使用独立字段保存'})
        self.assertNotIn('0.65', textmatch.title_phrases('阈值 0.65'))
        self.assertEqual(textmatch.slug_words('decisions/2026-10-13-conversation-language.md'), {'conversation', 'language'})


if __name__ == '__main__':
    unittest.main()
