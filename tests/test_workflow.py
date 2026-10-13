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

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-workflow/scripts'
sys.path.insert(0, str(SCRIPTS))
from common import Invalid, artifact, profile_valid, snapshot, task_valid, write
import execution
import validation
import workflow


class WorkflowCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / '.gitignore').write_text('.team-workflow/\n__pycache__/\n')
        (self.root / 'AGENTS.md').write_text('Respect the public behavior.\n')
        (self.root / 'app.py').write_text('def add(a, b):\n    return a+b\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.profile = {'schema_version': 5, 'project': 'sample', 'context': ['AGENTS.md'],
                        'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
                        'checks': {}, 'required_checks': {'code': [], 'docs': []},
                        'risk_checks': {}, 'inputs': [], 'environment_versions': {}}
        self.task = {'schema_version': 5, 'id': 'TASK-fixture', 'base': self.git('rev-parse', 'HEAD').strip(),
                     'goal': 'Addition works', 'non_goals': [], 'kind': 'code', 'risks': [],
                     'acceptance': [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': []}],
                     'design_id': 'D-add', 'section_ids': ['T1'], 'acceptance_scope': 'requirement', 'paths': ['app.py']}

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

    def fake_cs(self):
        """Contract stub, not evidence of CS production compatibility."""
        skill = self.root / '.team-workflow/cs-fixture'
        (skill / 'scripts').mkdir(parents=True)
        (skill / 'SKILL.md').write_text('CS protocol fixture')
        wiki = self.root / '.codestable/wiki'
        wiki.mkdir(parents=True)
        (wiki / 'INDEX.md').write_text('Project knowledge')
        (wiki / 'task.md').write_text(self.task['id'] + '\ncompleted')
        write(self.root / '.codestable/config.json', {'version': '2.1.0'})
        (skill / 'scripts/bootstrap.py').write_text('import json\nprint(json.dumps({"ok":True,"skill_version":"2.1.0","capabilities":["documents","receipt-check","task-files","task-external-refs","exclusive-plan-file","review-actions"]}))')
        reply = {'ok': True, 'state': '0'*64, 'kind': 'receipt-check', 'read_only': True, 'query_state': {}, 'changed': [], 'receipt': {'query_state': {}}, 'task_status': 'completed', 'canonical_task_id': 'CS-T', 'task_revision': 1,
                 'files': ['.codestable/wiki/task.md'],
                 'records': [{'id': 'CS-T', 'path': '.codestable/wiki/task.md', 'relations': ['task-note']} ]}
        reply['scopes'] = self.task.get('scopes') or [{'repository': 'self', 'path': p} for p in self.task.get('paths', ['app.py'])]
        reply['external_refs'] = [{'system': 'github' if self.task['id'].startswith('https://github.com/') else 'team-workflow', 'id': self.task['id']}]
        (skill / 'scripts/cs_knowledge.py').write_text(
            'import json,sys,hashlib\nfrom pathlib import Path\n'
            + 'reply=' + repr(reply) + '\n'
            + 'root=Path(sys.argv[sys.argv.index("--root")+1])\n'
            + 'if "template" in sys.argv:\n'
            + ' p=root/".team-workflow/acceptance.json"\n'
            + ' source={"workflow_acceptance":{"path":str(p.relative_to(root)),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}} if p.exists() else {}\n'
            + ' reply={"ok":True,"task":{"source":source,"status":"completed","summary":"fixture","result":"fixture","scopes":reply["scopes"]},"items":[]}\n'
            + 'print(json.dumps(reply))\n')
        return skill

    def test_project_rejects_unsupported_cs_before_work_starts(self):
        skill = self.fake_cs()
        (skill / 'scripts/bootstrap.py').write_text('print(\'{"ok":true,"skill_version":"2.0.0"}\')')
        write(self.root / '.team-workflow.json', self.profile)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = workflow.main(['project', '--root', str(self.root), '--cs-skill', str(skill)])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertFalse(result['ok'])
        self.assertEqual(result['cs']['status'], 'incomplete')
        self.assertIn('receipt-check', result['cs']['reason'])

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
        self.fake_cs()
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
        (self.root / '.gitignore').write_text('.team-workflow/\nsecret-config.json\n')
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
        write(self.root / '.team-workflow.json', self.profile)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(workflow.main(['project', '--root', str(self.root)]), 1)  # CS absent
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_scenario_requires_fresh_bound_review(self):
        out = self.root / '.team-workflow/scenario'
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
            execution.output_path(self.root, self.root / '.team-workflow', '{output}/../escape')

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
        write(self.root / '.team-workflow/local.json', {'inputs': {'workspace': str(path)}})
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
