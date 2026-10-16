"""Report-only declaration checks through the preparation commands."""
import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

import test_workflow as fixtures
import contracts
import coordination
import designs
import plan_fixtures as plans
import test_coordination as shared
import test_delivery as local
import workflow
from platform_fixtures import transport
from tw_runtime.team import platform_script


class VerificationGaps(unittest.TestCase):
    setUp, git, check = (fixtures.WorkflowCases.setUp, fixtures.WorkflowCases.git, fixtures.WorkflowCases.check)
    setup_task, name, write = (local.DeliveryCases.setup_task, local.DeliveryCases.name, local.DeliveryCases.write)
    prepare, body, github, publish_fixture, establish_design = (
        shared.CoordinationCases.prepare, shared.CoordinationCases.body, shared.CoordinationCases.github,
        shared.CoordinationCases.publish_fixture, shared.CoordinationCases.establish_design)

    def command(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = workflow.main([*args, '--root', str(self.root)])
        return code, out.getvalue()

    def incompatible(self):
        self.design['sections'][1]['data']['verification'].update(cases=['Suite::case'], substitutes=['existing'])
        self.profile['checks']['unit']['coverage'].update(level='unit', substitutes=['recorder'], isolation='unresolved')

    def assert_gaps(self, result):
        self.assertTrue(result['ok'], result)
        self.assertEqual(result.get('gaps', []), [])
        gaps = result['verification_gaps']
        self.assertEqual(len(gaps), 4, gaps)
        for gap in gaps:
            self.assertIn('A1', gap)
            self.assertIn('unit', gap)
        self.assertIn('checks.unit.coverage', gaps[0])
        self.assertIn('把 A1 的验证行改为：- 验证：自动；用例 Suite::case；替身 existing、recorder', gaps[1])
        self.assertIn('journey', gaps[2])
        self.assertIn('删除用例', gaps[3])
        if result.get('pending_sections'):
            self.assertTrue(result['next_action'].startswith('tw team approval-draft '), result)
        else:
            self.assertTrue(result['next_action'].startswith(gaps[0]), result)

    def test_early_gaps_are_actionable_and_report_only_in_local_commands(self):
        self.setup_task()
        self.incompatible()
        self.write('design', self.design)
        fixtures.write_config(self.root, self.profile)
        for command in ('design-draft', 'approval-draft', 'start'):
            options = ['--reviewer', 'carol'] if command == 'approval-draft' else []
            args = [command, '--task', self.name('task'), '--design', self.name('design'), *options]
            with self.subTest(command=command):
                code, out = self.command(*args)
                self.assertEqual(code, 0, out)
                result = json.loads(out)
                self.assert_gaps(result)
                if command == 'start':
                    self.assertTrue(result['implementation_ready'], result)
                code, text = self.command(*args, '--format', 'text')
                self.assertEqual(code, 0, text)
                self.assertIn('\n\n验收无法满足：\n', text)
                for gap in result['verification_gaps']:
                    self.assertIn('- ' + gap, text)

    def test_shared_drafts_and_start_report_the_same_gaps(self):
        self.prepare(complexity='simple')
        self.incompatible()
        fixtures.write_config(self.root, self.profile)
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            self.establish_design(approved=False)
            source = plans.design_source(self.root, {**self.design, 'revision': 2})
            for command in ('design-draft', 'approval-draft', 'start'):
                options = (['--record', str(source)] if command == 'design-draft' else
                           ['--reviewer', 'carol'] if command == 'approval-draft' else [])
                with self.subTest(command=command):
                    code, out = self.command(command, '--issue', self.url, *options)
                    self.assertEqual(code, 0, out)
                    self.assert_gaps(json.loads(out))

    def test_missing_coverage_names_the_acceptance_and_config_fix(self):
        self.setup_task()
        del self.profile['checks']['unit']['coverage']
        gaps = contracts.execution_environment(self.profile, self.task, self.design)
        self.assertEqual(len(gaps), 2, gaps)
        self.assertIn('A1', gaps[0])
        self.assertIn('checks.unit.coverage', gaps[0])
        self.assertIn('journey', gaps[1])
        manual = copy.deepcopy(self.design)
        manual['sections'][1]['data']['verification'] = {'method': 'manual', 'cases': [], 'substitutes': []}
        self.assertEqual(contracts.execution_environment(self.profile, self.task, manual), [])

    def test_substitute_fix_is_paste_ready_with_list_delimiters(self):
        self.setup_task()
        allowed, missing = '缓存、记录器', '队列；替身'
        self.design['sections'][1]['data']['verification']['substitutes'] = [allowed]
        self.profile['checks']['unit']['coverage']['substitutes'] = [missing]
        gap, = contracts.execution_environment(self.profile, self.task, self.design)
        fix = gap.split('改为：', 1)[1].split('（检查 ', 1)[0]
        raw = designs.render(self.design)
        line = next(line for line in raw.splitlines() if line.startswith('- 验证：'))
        loaded = designs.load(raw.replace(line, fix), scenario_reader=plans.scenario_reader)
        self.assertEqual(loaded['sections'][1]['data']['verification']['substitutes'], [allowed, missing])
