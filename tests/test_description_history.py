"""Editing a change-request description preserves published design and approval history."""
import copy
import unittest
from unittest.mock import patch

import test_coordination as shared
import coordination
import designs
import plan_fixtures as plans
from platform_fixtures import task_data, transport
from tw_runtime.team import platform_script


class DescriptionHistory(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def test_editing_description_after_publishing_preserves_digest_design_and_approval(self):
        self.prepare()
        change = {'url': 'https://github.com/example/project/pull/3', 'author': 'alice',
                  'created_at': '2026-10-12T00:00:00+00:00', 'updated_at': '2026-10-12T00:00:00+00:00',
                  'kind': 'change', 'body': 'Initial design display'}
        api = transport(self.github)

        def call(root, operation, *args):
            value = api(root, operation, *args)
            if operation == 'task':
                value['items'].append(copy.deepcopy(change))
                value['items'][1:] = sorted(value['items'][1:], key=lambda row: (row['created_at'], row['url']))
            return value

        with patch.object(platform_script, 'call', side_effect=call):
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.publish_fixture(approval, 'carol')
            before = coordination.load(self.url)
            change.update(body='Updated display after both records were published', updated_at='2026-10-16T01:00:00+00:00')
            after = coordination.load(self.url)
        self.assertEqual(after['history_digest'], before['history_digest'])
        self.assertEqual(after['design_previous'], before['design_previous'])
        self.assertEqual(after['design'], self.design)
        self.assertEqual(after['approvals'], [approval['record']['approval']])
        self.assertEqual(after['gaps'], [])
        status = designs.approval_status(after['design'], after['approvals'], history=after['history'], changed_paths=[])
        self.assertTrue(status['fully_approved'], status)
