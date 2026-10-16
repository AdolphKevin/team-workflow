"""Publication instructions prevent stale history and identify edits when it changes."""
import copy
import unittest
from unittest.mock import patch

import test_coordination as shared
import coordination
import issue_draft
import plan_fixtures as plans
from platform_fixtures import transport
from tw_runtime.team import platform_script


class PublishingGuidance(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def test_design_draft_orders_edits_generation_and_immutable_history(self):
        self.prepare()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            draft = plans.draft_design(self.root, self.url, self.design)
        self.assertEqual(len(draft['next_steps']), 3)
        self.assertIn('任务正文', draft['next_steps'][0])
        self.assertIn('变更请求描述', draft['next_steps'][0])
        self.assertIn('最后生成', draft['next_steps'][1])
        self.assertIn('立即发布', draft['next_steps'][1])
        self.assertIn('之前的评论', draft['next_steps'][2])

    def test_approval_request_and_issue_steps_follow_the_design_carrier(self):
        self.prepare()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            draft = issue_draft.draft(self.root, self.profile, plans.written_task(self.task), self.design,
                                      design_path=plans.design_source(self.root, self.design))
        text = '\n'.join(draft['next_steps']) + draft['issues'][0]['approval_request']
        self.assertIn('承载方案的变更请求', text)
        self.assertIn('没有变更请求时', text)
        self.assertIn('请阅读方案原文', text)
        self.assertNotIn('本 Issue 上的方案记录', text)
        self.assertNotIn('design issue', text)

    def test_history_mismatch_names_later_edits_or_missing_inserted_comment(self):
        self.prepare()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            first = plans.draft_design(self.root, self.url, self.design)
            self.publish_fixture(first, 'alice')
            self.issue['comments_data'][0].update(created_at='2026-10-15T01:00:00Z', updated_at='2026-10-15T01:00:00Z')
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.publish_fixture(approval, 'carol')
            self.issue['comments_data'][1].update(created_at='2026-10-15T02:00:00Z', updated_at='2026-10-15T02:00:00Z')
            self.issue['comments_data'][0]['updated_at'] = '2026-10-15T03:00:00Z'
            gaps = coordination.load(self.url)['gaps']
            mismatch = next(gap for gap in gaps if 'Preceding history changed' in gap)
            self.assertIn(self.url + '#issuecomment-1', mismatch)
            self.assertIn('重新生成', mismatch)
            self.issue['comments_data'][0]['updated_at'] = '2026-10-15T01:00:00Z'
            self.issue['comments_data'][0]['body'] = first['markdown'].replace('方案第 1 版已发布', '说明改动')
            # Metadata is unchanged but an inserted record still changes the preceding digest.
            self.issue['comments_data'].insert(0, {**copy.deepcopy(self.issue['comments_data'][0]),
                'html_url': self.url + '#issuecomment-99'})
            mismatch = next(gap for gap in coordination.load(self.url)['gaps'] if 'Preceding history changed' in gap)
            self.assertIn('更早的评论可能已被删除或插入', mismatch)
