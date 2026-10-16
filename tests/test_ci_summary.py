"""CI 摘要从选中的真实导入记录读取；平台调用在传输边界提供固定响应。"""
import copy
import unittest
from unittest.mock import patch

import test_portable as portable_fixture
import test_delivery as delivery_fixture
import test_workflow as fixtures
import plan_fixtures as plans
from common import artifact, read
import delivery
import designs
import knowledge
import validation
from platform_fixtures import CONFIG, transport
from tw_runtime.team import platform_script


class ImportedSummary(unittest.TestCase):
    setUp, git, check = fixtures.WorkflowCases.setUp, fixtures.WorkflowCases.git, fixtures.WorkflowCases.check
    setup_task, name, write = delivery_fixture.DeliveryCases.setup_task, delivery_fixture.DeliveryCases.name, delivery_fixture.DeliveryCases.write
    configure_check, capture, pack, api, import_result = (portable_fixture.PortableCases.configure_check,
        portable_fixture.PortableCases.capture, portable_fixture.PortableCases.pack,
        portable_fixture.PortableCases.api, portable_fixture.PortableCases.import_result)

    def test_accept_summary_lists_only_selected_imported_checks(self):
        self.setup_task(complexity='medium')
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.profile['platform'] = copy.deepcopy(CONFIG)
        self.configure_check()
        fixtures.write_config(self.root, self.profile)
        self.git('add', '.')
        self.git('commit', '-qm', '合成 CI 源码')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.write('task', self.task)
        self.write('brief', knowledge.brief(self.root, self.task, [], []))
        self.capture()
        imported, _ = self.import_result()
        self.report['runs'] = [imported.relative_to(self.root).as_posix()]
        self.write('approval', designs.approval_draft(self.design, 'carol', '确认方案', mode='design'))
        plans.submit_scenarios(self.root, self.task, self.report)
        ref = artifact(self.root, imported)
        with patch.object(platform_script, 'call', side_effect=transport(self.api)):
            review = delivery.review_template(self.root, self.profile, self.task, self.report)
            review.update(reviewer='carol', knowledge_conflicts_resolved=True)
            for axis in ('standards', 'spec'):
                review[axis] = {'status': 'passed', 'summary': '已独立核对', 'evidence': [ref]}
            review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': '实际用例通过', 'evidence': [ref],
                                     'observations': plans.observations(self.root, ref)}]
            self.write('review', review)
            accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
            self.assertEqual(accepted['ci_verified_checks'], ['unit'])
            self.assertIn('导入的 CI 检查：unit', accepted['summary_markdown'])
            self.assertNotIn('CI 未验证', accepted['summary_markdown'])
            # A newer selected local run supersedes CI; historical imports do not verify this selection.
            local, _ = validation.run_batch(self.root, self.profile, [self.task])
            self.report['runs'].append(local.relative_to(self.root).as_posix())
            ref = artifact(self.root, local)
            review = delivery.review_template(self.root, self.profile, self.task, self.report)
            review.update(reviewer='carol', knowledge_conflicts_resolved=True)
            for axis in ('standards', 'spec'):
                review[axis] = {'status': 'passed', 'summary': '已独立核对', 'evidence': [ref]}
            review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': '当前本机用例通过', 'evidence': [ref],
                                     'observations': plans.observations(self.root, ref)}]
            self.write('review', review)
            local_acceptance = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
            self.assertEqual(local_acceptance['ci_verified_checks'], [])
            self.assertIn('CI 未验证', local_acceptance['summary_markdown'])
