"""Issue comments and change/review records share the same immutable history."""
import plan_fixtures as plans
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_coordination as coordination_cases
import test_designs as design_cases
import coordination
import designs
from tw_runtime.team import platform_script
from platform_fixtures import task_data


class ChangeRequestRecords(unittest.TestCase):
    base = coordination_cases.CoordinationCases
    setUp, git, check, prepare, body, publish_fixture = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.publish_fixture)

    def response(self, kinds=()):
        value = task_data(self.issue)
        for item, kind in zip(value['items'][1:], kinds):
            item['kind'] = kind
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps({'task': value})
        platform_script.clear_cache()

    def setup_platform(self):
        self.prepare()
        self.profile['platform'] = {'argv': [sys.executable, str(Path(__file__).with_name('platform_fixture.py'))],
                                    'operations': ['task']}
        import test_workflow as fixtures
        fixtures.write_config(self.root, self.profile)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.response()

    def equivalent(self, kinds):
        self.response()
        comments = coordination.load(self.url, root=self.root)
        self.response(kinds)
        change = coordination.load(self.url, root=self.root)
        self.assertEqual(change, comments)
        self.assertEqual(change['gaps'], [])
        return change

    def test_published_comment_and_review_approval_keep_the_same_history(self):
        self.setup_platform()
        self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
        self.response(['comment'])
        self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol'}), 'carol')
        result = self.equivalent(['comment', 'review'])
        status = designs.approval_status(result['design'], result['approvals'], changed_paths=[])
        self.assertTrue(status['fully_approved'], status)
        self.assertEqual(status['approved'], ['A1', 'T1', 'scope-global'])

    def test_new_published_comment_or_review_only_invalidates_affected_sections(self):
        self.setup_platform()
        self.design['sections'] += [design_cases.section('api-1', 'interface'),
                                    design_cases.section('api-2', 'interface')]
        self.design['sections'][1]['depends_on'] = ['api-1']
        for kind in ('comment', 'review'):
            with self.subTest(kind=kind):
                self.issue['comments_data'] = []
                self.response()
                self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
                self.response(['comment'])
                self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol', 'section_ids': 'all'}), 'carol')
                self.response(['comment', 'review'])
                revised = design_cases.changed(self.design, 'api-1')
                self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
                result = self.equivalent(['comment', 'review', kind])
                status = designs.approval_status(result['design'], result['approvals'], history=result['history'], changed_paths=[])
                self.assertEqual(status['stale'], ['A1', 'T1', 'api-1'])
                self.assertEqual(status['approved'], ['api-2', 'scope-global'])
                self.response(['comment', 'review', kind])
                self.publish_fixture(coordination.draft_approval(self.url, {
                    'reviewer': 'carol', 'section_ids': ['A1', 'T1', 'api-1']}), 'carol')
                result = self.equivalent(['comment', 'review', kind, 'review'])
                status = designs.approval_status(result['design'], result['approvals'], history=result['history'], changed_paths=[])
                self.assertEqual(status['stale'], [])
                self.assertTrue(status['fully_approved'], status)


if __name__ == '__main__':
    unittest.main()
