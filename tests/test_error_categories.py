"""R1：错误类别由失败对象与原因决定。"""
import unittest
import copy
import contextlib
import io
import json
import shlex
from pathlib import Path
from unittest.mock import patch

import test_workflow
from common import Invalid, obj
import commands
import repairs
import workflow
import validation
import execution
import delivery
import artifacts
import designs
from test_designs import example


class ErrorCategories(unittest.TestCase):
    def test_generic_object_errors_are_independent_of_field_words(self):
        for fields in ({'approval_notes'}, {'reporter'}, {'arbitrary'}):
            with self.subTest(fields=fields):
                with self.assertRaises(Invalid) as raised:
                    obj({}, fields)
                self.assertEqual(raised.exception.error_code, 'invalid-or-incomplete-input')
                with self.assertRaises(Invalid) as raised:
                    obj({next(iter(fields)): True}, set())
                self.assertEqual(raised.exception.error_code, 'invalid-or-incomplete-input')

    def test_missing_materials_and_dependency_use_the_failed_object(self):
        for name, code, expected in [('design', 'design-input-invalid', 'start'),
                                      ('brief', 'knowledge-brief-incomplete', 'brief')]:
            args = workflow.parser().parse_args(['accept', '--root', '/tmp/category', '--task', 'task-1'])
            if name == 'brief':
                args.design = Path('design.md')
            with self.subTest(name=name):
                with self.assertRaises(Invalid) as raised:
                    commands.report_input(args, args.root, {})
                self.assertEqual(raised.exception.error_code, code)
                self.assertIn('tw team ' + expected, repairs.failure(args, raised.exception)['next_action'])
        with self.assertRaises(Invalid) as raised:
            commands.predecessor_checks(args, args.root, {}, {}, example(), dependencies=[{'section': 'T1'}])
        self.assertEqual(raised.exception.error_code, 'task-input-invalid')

    def test_local_status_missing_design_uses_start_default(self):
        args = workflow.parser().parse_args(['status', '--root', '/tmp/category', '--task', 'task-1'])
        with self.assertRaises(Invalid) as raised:
            commands._status(args, args.root, {}, {}, None)
        self.assertEqual(raised.exception.error_code, 'invalid-or-incomplete-input')
        self.assertIn('tw team start', repairs.failure(args, raised.exception)['next_action'])

    def test_request_id_format_is_request_input(self):
        with self.assertRaises(Invalid) as raised:
            artifacts.directory(Path('/tmp/category'), 'task-1', '!')
        self.assertEqual(raised.exception.error_code, 'request-input-invalid')

    def test_occupied_request_categories_follow_process_state(self):
        import tempfile
        import os
        from tw_fixtures import make_repo
        with tempfile.TemporaryDirectory() as directory:
            root = make_repo(directory)
            (root / '.tw').mkdir()
            (root / '.tw/.gitignore').write_text('local/\n')
            artifacts.Request(root, 'task-1', {}, 'occupied')
            active = artifacts.Request(root, 'task-1', {}, 'occupied').cached
            self.assertEqual(active['error_code'], 'request-active')
            with patch.object(os, 'kill', side_effect=ProcessLookupError):
                interrupted = artifacts.Request(root, 'task-1', {}, 'occupied').cached
            self.assertEqual(interrupted['error_code'], 'request-interrupted')

    def test_approval_missing_design_snapshot_is_design_history(self):
        original = example()
        approval = designs.approval_draft(original, 'carol')
        current = copy.deepcopy(original)
        current['revision'] = 2
        result = designs.approval_status(current, [approval], history=[], changed_paths=[])
        self.assertEqual(result.get('error_code'), 'design-history-incomplete')

    def test_specific_categories_keep_recovery_with_arbitrary_messages(self):
        rows = [('check-config-invalid', '.tw/config.json'), ('check-result-invalid', 'tw team run'),
                ('project-not-initialized', 'tw init'), ('acceptance-record-missing', 'tw team accept'),
                ('approval-commit-unavailable', '提交取到本地'), ('approved-source-invalid', '修正批准源码中的文件链接'),
                ('acceptance-stale', 'tw team accept'),
                ('platform-records-changed', 'tw team verify'), ('knowledge-brief-incomplete', 'tw team brief'),
                ('design-history-incomplete', '--design-history'), ('request-active', 'tw team status'),
                ('request-interrupted', 'tw team verify'), ('request-input-invalid', 'tw team verify')]
        for category, expected in rows:
            actions = []
            for message in ('任意说明甲', 'approval report 批准 完全不同的说明乙'):
                args = workflow.parser().parse_args(['verify', '--root', '/tmp/category', '--task', 'task-1',
                                                     '--report', 'delivery.json'])
                exc = Invalid(message, error_code=category)
                result = repairs.failure(args, exc)
                actions.append(result['next_action'])
                with self.subTest(category=category, message=message):
                    self.assertIn(expected, result['next_action'])
            self.assertEqual(actions[0], actions[1])

    def test_failed_check_selection_is_preserved(self):
        args = workflow.parser().parse_args(['run', '--root', '/tmp/category', '--task', 'task-1'])
        result = repairs.annotate(args, {'ok': False, 'error_code': 'check-result-invalid',
            'checks': [{'id': 'passed', 'status': 'passed'}, {'id': 'unit', 'status': 'failed'}]})
        self.assertIn('--check unit', result['next_action'])
        self.assertNotIn('--check passed', result['next_action'])

    def test_platform_retry_retains_original_material_arguments(self):
        business = ['accept', '--root', '/tmp/category', '--task', '.tw/local/task.json',
                    '--report', '.tw/local/report.json', '--review', '.tw/local/review-new.json',
                    '--run', '.tw/local/run-new.json', '--approval', '.tw/local/approval-new.json']
        for operational in ([], ['--request-id', 'old', '--out', '.tw/local/old.json'],
                            ['--request-id=old', '--out=.tw/local/old.json']):
            output = io.StringIO()
            def changed(args, root):
                args.task = 'task-resolved-identity'
                raise Invalid('平台记录已经改变', error_code='platform-records-changed')
            with self.subTest(operational=operational), patch.object(commands, 'dispatch', side_effect=changed), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(workflow.main(business + operational), 1)
            result = json.loads(output.getvalue())
            invocation = shlex.split(result['next_action'].partition('：')[2])
            self.assertEqual(invocation, ['tw', 'team', *business])


class ApprovalCategoryCLI(unittest.TestCase):
    base = __import__('test_approval_revision').ApprovalRevision
    setUp, git, check, configure, command, status_with_revision = (
        base.setUp, base.git, base.check, base.configure, base.command, base.status_with_revision)

    def test_status_preserves_unavailable_commit_category(self):
        self.configure()
        code, result = self.status_with_revision('f' * 40)
        self.assertEqual(code, 0)
        self.assertEqual(result.get('error_code'), 'approval-commit-unavailable')
        self.assertIn('提交取到本地', result['next_action'])

    def test_status_preserves_invalid_approved_source_category(self):
        self.configure()
        link = self.root / 'approved-link'
        link.symlink_to('missing')
        self.git('add', 'approved-link')
        self.git('commit', '-qm', 'approved source link fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        link.unlink()
        code, result = self.status_with_revision(revision)
        self.assertEqual(code, 0, result)
        self.assertEqual(result.get('error_code'), 'approved-source-invalid')
        self.assertIn('修正批准源码中的文件链接', result['next_action'])


class CheckCategorySources(unittest.TestCase):
    setUp, git, check = (test_workflow.WorkflowCases.setUp, test_workflow.WorkflowCases.git,
                         test_workflow.WorkflowCases.check)

    def test_junit_registration_errors_point_to_check_configuration(self):
        from common import profile_valid
        for report in ('wrong.xml', '{output}/results.xml'):
            self.check('print(1)', format='junit', report=report)
            with self.subTest(report=report):
                with self.assertRaises(Invalid) as raised:
                    profile_valid(self.profile, self.root)
                self.assertEqual(raised.exception.error_code, 'check-config-invalid')
                args = workflow.parser().parse_args(['accept', '--root', str(self.root), '--task', 'task-1'])
                action = repairs.failure(args, raised.exception)['next_action']
                self.assertIn('.tw/config.json', action)
                self.assertNotIn('tw team deliver', action)

    def test_unavailable_approved_commit_points_to_local_objects(self):
        with self.assertRaises(Invalid) as raised:
            validation.revision_files(self.root, self.profile, 'a' * 40)
        self.assertEqual(raised.exception.error_code, 'approval-commit-unavailable')
        args = workflow.parser().parse_args(['accept', '--root', str(self.root), '--task', 'task-1'])
        action = repairs.failure(args, raised.exception)['next_action']
        self.assertIn('提交取到本地', action)
        self.assertNotIn('approval-draft', action)

    def test_complete_approved_objects_with_invalid_links_require_source_repair(self):
        link = self.root / 'approved-link'
        for target in ('missing', 'approved-link', '../outside'):
            with self.subTest(target=target):
                link.symlink_to(target)
                self.git('add', 'approved-link')
                self.git('commit', '-qm', 'approved source link fixture')
                self.git('fsck', '--full')
                revision = self.git('rev-parse', 'HEAD').strip()
                with self.assertRaises(Invalid) as raised:
                    validation.revision_files(self.root, self.profile, revision)
                self.assertEqual(raised.exception.error_code, 'approved-source-invalid')
                args = workflow.parser().parse_args(['accept', '--root', str(self.root), '--task', 'task-1'])
                action = repairs.failure(args, raised.exception)['next_action']
                self.assertIn('修正批准源码中的文件链接', action)
                self.assertIn('检查与评审', action)
                self.assertNotIn('提交取到本地', action)
            link.unlink()

    def test_missing_registered_case_keeps_configuration_category(self):
        path = self.root / 'results.xml'
        path.write_text('<testsuite tests="1"><testcase classname="Real" name="works"/></testsuite>')
        check = {'format': 'junit', 'required_cases': ['Wrong::works']}
        decoded = execution.decode(check, {'state': 'finished', 'exit_code': 0, 'stdout': ''}, path)
        self.assertEqual(getattr(decoded, 'error_code', None), 'check-config-invalid')

    def test_original_check_report_failure_requires_rerun(self):
        row = self.check("from pathlib import Path; Path('{output}/results.xml').write_text('<testsuite tests=\"1\"><testcase name=\"works\"/></testsuite>')",
                         format='junit', report='{output}/results.xml')
        output = self.root / '.tw/local/original'
        result = validation.capture(self.root, self.profile, 'unit', output)
        (output / 'results.xml').write_text('<testsuite tests="1"><testcase name="works"><failure/></testcase></testsuite>')
        from common import artifact
        result['artifacts'] = [artifact(self.root, self.root / ref['path']) for ref in result['artifacts']]
        with self.assertRaises(Invalid) as raised:
            validation.reevaluate(self.root, self.profile, 'unit', result)
        self.assertEqual(raised.exception.error_code, 'check-result-invalid')
        args = workflow.parser().parse_args(['verify', '--root', str(self.root), '--task', 'task-1'])
        self.assertIn('tw team run', repairs.failure(args, raised.exception)['next_action'])

    def test_reused_run_keeps_registration_category(self):
        self.check("from pathlib import Path; Path('{output}/results.xml').write_text('<testsuite tests=\"1\"><testcase name=\"works\"/></testsuite>')",
                   format='junit', report='{output}/results.xml')
        path, _ = validation.run_batch(self.root, self.profile, [self.task])
        self.profile['checks']['unit']['required_cases'] = ['Wrong::works']
        with self.assertRaises(Invalid) as raised:
            validation.verify_runs(self.root, self.profile, self.task, [path.relative_to(self.root).as_posix()], live=False)
        self.assertEqual(raised.exception.error_code, 'check-config-invalid')


class CheckCategoryCLI(unittest.TestCase):
    base = __import__('test_four_command_delivery').FourCommandDelivery
    setUp, git, check, configure, command, start = (
        base.setUp, base.git, base.check, base.configure, base.command, base.start)

    def test_run_keeps_registration_error_through_saved_result(self):
        self.start()
        self.check("from pathlib import Path; Path('{output}/results.xml').write_text('<testsuite tests=\"1\"><testcase classname=\"Real\" name=\"works\"/></testsuite>')",
                   format='junit', report='{output}/results.xml', required_cases=['Wrong::works'])
        test_workflow.write_config(self.root, self.profile)
        code, result = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1)
        self.assertEqual(result.get('error_code'), 'check-config-invalid')
        self.assertIn('.tw/config.json', result['next_action'])
        self.assertNotIn('tw team run', result['next_action'])


class PortableCategorySources(unittest.TestCase):
    base = __import__('test_portable').PortableCases
    setUp, git, check, prepare, configure_check, capture, pack = (
        base.setUp, base.git, base.check, base.prepare, base.configure_check, base.capture, base.pack)

    def test_imported_claims_must_match_original_check_report(self):
        import portable
        self.prepare()
        manifest = self.capture()
        manifest['execution']['cases'] = {'Fake::claim': 'passed'}
        with self.assertRaises(Invalid) as raised:
            portable.validate_result(self.root, self.profile, manifest, self.directory, live=False)
        self.assertEqual(raised.exception.error_code, 'check-result-invalid')

    def test_imported_originals_keep_registration_diagnosis(self):
        import portable
        self.prepare()
        manifest = self.capture()
        self.profile['checks']['unit']['required_cases'] = ['Wrong::adds']
        with self.assertRaises(Invalid) as raised:
            portable.validate_result(self.root, self.profile, manifest, self.directory, live=False)
        self.assertEqual(raised.exception.error_code, 'check-config-invalid')


class AcceptanceCategorySources(unittest.TestCase):
    base = __import__('test_delivery').DeliveryCases
    setUp, git, check, setup_task, write, name = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name)

    def test_changed_accepted_materials_require_current_acceptance(self):
        from common import read
        self.setup_task()
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.write('acceptance', accepted)
        self.report.update(acceptance=self.name('acceptance'), knowledge={'files': [], 'reason': '本次沿用现有知识'})
        review = read(self.root / self.name('review'))
        review['standards']['summary'] = '已按现行规范重新独立核对原始结果。'
        self.write('review-new', review)
        self.report['review'] = self.name('review-new')
        with self.assertRaises(Invalid) as raised:
            delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertEqual(raised.exception.error_code, 'acceptance-stale')
        args = workflow.parser().parse_args(['verify', '--root', str(self.root), '--task', self.task['id']])
        self.assertIn('tw team accept', repairs.failure(args, raised.exception)['next_action'])

    def test_missing_acceptance_owner_is_design_input(self):
        self.setup_task()
        self.design['roles']['acceptance_owner'] = ''
        self.write('design', self.design)
        with self.assertRaises(Invalid) as raised:
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertEqual(raised.exception.error_code, 'design-input-invalid')
        args = workflow.parser().parse_args(['accept', '--root', str(self.root), '--task', self.task['id']])
        self.assertIn('tw team start', repairs.failure(args, raised.exception)['next_action'])


class PlatformCategorySources(unittest.TestCase):
    fixture = __import__('test_close_note').CloseNote
    base = fixture.base
    setUp, git, check, setup_task, write, name, github, publish = (
        fixture.setUp, fixture.git, fixture.check, fixture.setup_task, fixture.write,
        fixture.name, fixture.github, fixture.publish)

    def test_platform_change_requires_the_same_command(self):
        from platform_fixtures import transport
        from tw_runtime.team import platform_script
        calls = []
        def changing(endpoint, **options):
            response = self.github(endpoint, **options)
            if endpoint == 'repos/example/project/issues/149':
                calls.append(endpoint)
                if len(calls) > 1:
                    response['assignees'] = [{'login': 'carol'}]
            return response
        with patch.object(platform_script, 'call', side_effect=transport(changing)):
            with self.assertRaises(Invalid) as raised:
                delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertEqual(raised.exception.error_code, 'platform-records-changed')
        for command in ('accept', 'verify'):
            args = workflow.parser().parse_args([command, '--root', str(self.root), '--task', self.task['id'],
                                                  '--report', self.name('report')])
            action = repairs.failure(args, raised.exception)['next_action']
            self.assertIn('tw team ' + command, action)
            self.assertIn('--report ' + self.name('report'), action)
            self.assertNotIn('approval-draft', action)


if __name__ == '__main__':
    unittest.main()
