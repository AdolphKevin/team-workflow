"""Shared fixtures and execution checks in isolated real Git repositories."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-knowledge/scripts/tw_runtime/team'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1]))
# The source tree changes during development; integrity gates are proven in test_integrity.py.
os.environ.setdefault('TEAM_WORKFLOW_ALLOW_MODIFIED_TOOL', '1')
from common import Invalid, artifact, profile_valid, snapshot, task_valid, write
import execution
import validation
import workflow


def configuration(root, profile):
    from tw_runtime import FORMAT
    from tw_runtime.gitutil import remote_identity
    return {'format': FORMAT, 'data_version': 1,
            'project': {'id': remote_identity(root) or 'local:sample', 'name': profile['project']},
            'context': list(profile['context']), 'shared': {}, 'documents': [],
            **{key: profile[key] for key in ('checks', 'required_checks', 'risk_checks', 'inputs',
                                          'external_inputs', 'environment_versions', 'accounts')},
            'acceptance_entries': profile.get('acceptance_entries', {'cli': {'surface': 'cli', 'operate': '运行命令', 'observe': ['输出'], 'evidence': ['输出'], 'isolation': '临时目录'}}),
            **({'platform': profile['platform']} if 'platform' in profile else {})}


def write_config(root, profile):
    write(root / '.tw/config.json', configuration(root, profile))


class WorkflowCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        from tw_runtime.team import platform_script as platform_read
        token = platform_read.PROJECT_ROOT.set(self.root)
        self.addCleanup(platform_read.PROJECT_ROOT.reset, token)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / '.gitignore').write_text('__pycache__/\n')
        (self.root / 'AGENTS.md').write_text('Respect the public behavior.\n')
        (self.root / 'app.py').write_text('def add(a, b):\n    return a+b\n')
        import shutil
        scenario = self.root / 'tests/fixtures/scenarios.json'
        scenario.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / 'fixtures/scenarios.json', scenario)
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.profile = {'data_version': 1, 'project': 'sample', 'context': ['AGENTS.md'],
                        'external_inputs': {}, 'accounts': [],
                        'checks': {}, 'required_checks': {'code': [], 'docs': []},
                        'risk_checks': {}, 'inputs': [], 'environment_versions': {}}
        self.task = {'data_version': 1, 'id': 'TASK-fixture', 'base': self.git('rev-parse', 'HEAD').strip(),
                     'goal': 'Addition works', 'non_goals': [], 'kind': 'code', 'risks': [],
                     'acceptance': [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': []}],
                     'design_id': 'D-add', 'section_ids': ['T1'], 'acceptance_scope': 'requirement', 'paths': ['app.py']}

        from tw_runtime import init
        from tw_fixtures import entry
        init.run(self.root, apply=True, sources=['self:AGENTS.md'])
        (self.root / '.tw/overview.md').write_text(entry('算术服务', '通过 app.add 计算加法。', source=['self:AGENTS.md']))
        write_config(self.root, self.profile)
        self.git('add', '.tw')
        self.git('commit', '-qm', 'initialized knowledge and team configuration')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def check(self, code, format='command', **kw):
        from plan_fixtures import coverage
        row = {'argv': [sys.executable, '-c', code], 'cwd': '.', 'timeout': 5, 'purpose': 'Actual behavior',
               'format': format, 'required_cases': [], 'required_env': [], 'coverage': coverage(), **kw}
        if row['required_env']:
            row.setdefault('environment', {'kind': 'fixture', 'identity': [sys.executable, '-c', "print('fixture')"]})
        else:
            row.setdefault('environment', {'kind': 'stateless'})
        self.profile['checks']['unit'] = row
        self.profile['required_checks']['code'] = ['unit']
        self.task['acceptance'][0]['checks'] = ['unit']
        return row

    def run_check(self):
        profile_valid(self.profile, self.root)
        return validation.run_batch(self.root, self.profile, [self.task])




    def test_unexpected_exception_is_reported_as_tool_defect_with_response(self):
        import commands
        import plan_fixtures as plans
        write_config(self.root, self.profile)
        write(self.root / '.tw/local/task.json', plans.written_task(self.task))
        output = io.StringIO()
        with patch.object(commands, 'produce', side_effect=NameError("name 'read' is not defined")), \
                contextlib.redirect_stdout(output):
            status = workflow.main(['task-export', '--root', str(self.root), '--task', '.tw/local/task.json',
                                    '--request-id', 'defect'])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(result['error_code'], 'tool-defect')
        self.assertIn('NameError', result['problem'])
        self.assertIn('installed skill', result['next_action'])
        responses = list((self.root / '.tw/local/tasks').glob('*/requests/defect/response.json'))
        self.assertEqual(len(responses), 1)
        with patch.object(commands, 'dispatch', side_effect=RuntimeError('boom')), contextlib.redirect_stdout(io.StringIO()) as raw:
            self.assertEqual(workflow.main(['snapshot', '--root', str(self.root), '--task', '.tw/local/task.json']), 1)
        self.assertEqual(json.loads(raw.getvalue())['error_code'], 'tool-defect')

    def test_deleted_and_untracked_files_change_fingerprint(self):
        old = snapshot(self.root, self.profile)
        (self.root / 'app.py').unlink()
        deleted = snapshot(self.root, self.profile)
        self.assertNotEqual(old, deleted)
        (self.root / 'new.txt').write_text('input')
        self.assertNotEqual(deleted, snapshot(self.root, self.profile))

    def test_source_mutation_during_test_cannot_pass(self):
        self.check("from pathlib import Path; Path('app.py').write_text('changed')")
        _, record = self.run_check()
        self.assertFalse(record['source_unchanged'])

    def test_knowledge_write_does_not_invalidate_source(self):
        old = snapshot(self.root, self.profile)
        (self.root / '.tw/overview.md').write_text((self.root / '.tw/overview.md').read_text() + '\n新的说明。\n')
        self.assertEqual(old, snapshot(self.root, self.profile))

    def test_unknown_risk_and_unmapped_risk_block(self):
        for risk in ('persistence', 'misspelled'):
            self.task['risks'] = [risk]
            with self.assertRaises(Invalid):
                task_valid(self.task, self.profile, self.root)

    def test_exit_failure_timeout_and_missing_environment(self):
        for code, kw, status in [('raise SystemExit(7)', {}, 'failed'),
                                  ('import time; time.sleep(20)', {'timeout': 1}, 'timeout'),
                                  ('raise RuntimeError()', {'required_env': ['MISSING_WORKFLOW_TEST_ENV']}, 'unavailable')]:
            with self.subTest(status=status):
                self.check(code, **kw)
                _, record = self.run_check()
                self.assertEqual(record['results'][0]['status'], status)

    def test_go_zero_skipped_incomplete_and_failed_tests(self):
        cases = [([{'Action':'pass','Package':'p'}], 'incomplete'),
                 ([{'Action':'skip','Package':'p','Test':'TestDB'}, {'Action':'pass','Package':'p'}], 'incomplete'),
                 ([{'Action':'run','Package':'p','Test':'TestDB'}, {'Action':'pass','Package':'p'}], 'incomplete'),
                 ([{'Action':'fail','Package':'p','Test':'TestDB'}, {'Action':'pass','Package':'p'}], 'incomplete'),
                 ([{'Action':'pass','Package':'p','Test':'TestDB'}, {'Action':'pass','Package':'p'}], 'passed')]
        for events, expected in cases:
            self.check('print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')', format='go-json')
            _, record = self.run_check()
            self.assertEqual(record['results'][0]['status'], expected)

    def test_only_unrelated_skips_allowed_with_explicit_required_cases(self):
        events = [{'Action':'pass','Package':'p','Test':'TestRequired'},
                  {'Action':'skip','Package':'p','Test':'TestOptional'}, {'Action':'pass','Package':'p'}]
        row = self.check('print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')', format='go-json')
        row['required_cases'] = ['p::TestRequired']
        _, record = self.run_check()
        self.assertEqual(record['results'][0]['status'], 'passed')
        row['required_cases'] = ['p::Absent']
        _, record = self.run_check()
        self.assertEqual(record['results'][0]['status'], 'incomplete')

    def test_junit_fresh_report_and_required_case(self):
        xml = '<testsuites><testsuite tests="2"><testcase classname="t" name="yes"/><testcase classname="t" name="optional"><skipped/></testcase></testsuite></testsuites>'
        self.check("from pathlib import Path; Path('{output}/results.xml').write_text(" + repr(xml) + ')', format='junit',
                   report='{output}/results.xml', required_cases=['t::yes'])
        _, record = self.run_check()
        self.assertEqual(record['results'][0]['status'], 'passed')
        self.profile['checks']['unit']['argv'] = [sys.executable, '-c', "print('{output}')"]
        _, record = self.run_check()
        self.assertEqual(record['results'][0]['status'], 'incomplete')

    def test_failure_cannot_be_overwritten_by_later_success(self):
        xml = '<testsuite><testcase name="same"><failure/></testcase><testcase name="same"/></testsuite>'
        path = self.root / 'result.xml'
        path.write_text(xml)
        self.assertEqual(execution.junit_cases(path)['::same'], 'failed')

    def test_docs_need_no_code_commands(self):
        self.check('raise RuntimeError()')
        self.task['kind'] = 'docs'
        self.task['acceptance'][0]['checks'] = []
        _, record = self.run_check()
        self.assertEqual(record['results'], [])

    def test_ignored_explicit_input_changes_binding(self):
        (self.root / '.gitignore').write_text('secret-config.json\n')
        (self.root / 'secret-config.json').write_text('one')
        self.profile['inputs'] = ['secret-config.json']
        before = snapshot(self.root, self.profile)
        (self.root / 'secret-config.json').write_text('two')
        self.assertNotEqual(before, snapshot(self.root, self.profile))

    def test_traversal_and_external_symlinks_rejected(self):
        self.profile['inputs'] = ['../escape']
        with self.assertRaises(Invalid):
            snapshot(self.root, self.profile)
        self.profile['inputs'] = []
        (self.root / 'escape').symlink_to('/etc/hosts')
        with self.assertRaises(Invalid):
            snapshot(self.root, self.profile)

    def test_secrets_in_environment_are_redacted_in_capture(self):
        self.check("import os; print(os.environ['WORKFLOW_TEST_TOKEN'])")
        with patch.dict(os.environ, {'WORKFLOW_TEST_TOKEN': 'synthetic-sensitive-value'}):
            _, record = self.run_check()
        stdout = self.root / record['results'][0]['artifacts'][0]['path']
        self.assertNotIn('synthetic-sensitive-value', stdout.read_text())
        self.assertIn('REDACTED', stdout.read_text())

    def test_project_check_does_not_execute_project_commands(self):
        self.check("from pathlib import Path; Path('should-not-exist').touch()")
        write_config(self.root, self.profile)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.main(['project', '--root', str(self.root)]), 0)
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_scenario_requires_fresh_bound_review(self):
        out = self.root / '.tw/local/scenario'
        out.mkdir(parents=True)
        write(out / 'manifest.json', {'run_id': 'scenario-1'})
        write(out / 'suite-transcript.json', {'actual': 'fixture'})
        check = {'review': {'format': 'codex-scenario', 'path': '{output}/codex-review.json',
                           'required_artifacts': ['manifest.json', 'suite-transcript.json']}}
        captures = {artifact(self.root, p)['path']: artifact(self.root, p)['sha256']
                    for p in out.iterdir()}
        with self.assertRaises(Invalid):
            validation.scenario_review(self.root, out, check, captures)
        report = {'schema_version': 1, 'reviewer': 'codex', 'run_id': 'scenario-1',
                  'status': 'PASS', 'scenario_run_status': 'COMPLETED', 'summary': 'Reviewed full fixture',
                  'findings': [], 'reviewed_artifacts': {Path(k).name: 'sha256:' + v for k, v in captures.items()}}
        write(out / 'codex-review.json', report)
        validation.scenario_review(self.root, out, check, captures)
        report['run_id'] = 'old-run'
        write(out / 'codex-review.json', report)
        with self.assertRaises(Invalid):
            validation.scenario_review(self.root, out, check, captures)
        report['run_id'] = 'scenario-1'
        write(out / 'codex-review.json', report)
        write(out / 'suite-transcript.json', {'actual': 'changed'})
        with self.assertRaises(Invalid):
            validation.scenario_review(self.root, out, check, captures)

    def test_project_rejects_unknown_format_and_output_escape(self):
        self.check('print(1)')
        self.profile['checks']['unit']['format'] = 'invented'
        with self.assertRaises(Invalid):
            profile_valid(self.profile, self.root)
        with self.assertRaises(Invalid):
            execution.output_path(self.root, self.root / '.tw/local', '{output}/../escape')

    def test_incomplete_package_or_junit_counts_cannot_pass(self):
        stream = '\n'.join(json.dumps(e) for e in [
            {'Action': 'pass', 'Package': 'p1', 'Test': 'TestOK'},
            {'Action': 'pass', 'Package': 'p1'},
            {'Action': 'start', 'Package': 'p2'}])
        with self.assertRaises(Invalid):
            execution.go_cases(stream)
        path = self.root / 'incomplete.xml'
        path.write_text('<testsuite tests="2"><testcase name="only-one"/></testsuite>')
        with self.assertRaises(Invalid):
            execution.junit_cases(path)

    def test_external_workspace_input_changes_evidence(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        path = Path(outside.name) / 'go.work'
        path.write_text('workspace A')
        self.profile['external_inputs'] = {'workspace': {'kind': 'file'}}
        write(self.root / '.tw/local/repositories.json', {'inputs': {'workspace': str(path)}})
        profile_valid(self.profile, self.root)
        before = snapshot(self.root, self.profile)
        path.write_text('workspace B')
        self.assertNotEqual(before, snapshot(self.root, self.profile))

    def test_edited_or_emptied_output_cannot_verify(self):
        self.check("import app; assert app.add(1,2)==3")
        path, record = self.run_check()
        run = str(path.relative_to(self.root))
        validation.verify_runs(self.root, self.profile, self.task, [run])
        output = self.root / record['results'][0]['artifacts'][0]['path']
        for value in ('fabricated', ''):
            output.write_text(value)
            with self.subTest(value=value), self.assertRaises(Invalid):
                validation.verify_runs(self.root, self.profile, self.task, [run])

    def test_malformed_or_missing_execution_cannot_verify(self):
        self.check("import app; assert app.add(1,2)==3")
        path, _ = self.run_check()
        with self.assertRaisesRegex(Invalid, 'Required execution missing'):
            validation.verify_runs(self.root, self.profile, self.task, [])
        write(path, [])
        with self.assertRaisesRegex(Invalid, 'Invalid execution record'):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])


if __name__ == '__main__':
    unittest.main()
