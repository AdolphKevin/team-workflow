"""Executable v2 contract scenarios in isolated real Git repositories."""
import copy
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
from common import Invalid, artifact, binding, digest, profile_valid, read, snapshot, task_valid, write
import execution
import knowledge
import verification
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
        self.profile = {'schema_version': 2, 'project': 'sample', 'context': ['AGENTS.md'],
                        'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
                        'checks': {}, 'required_checks': {'code': [], 'docs': []},
                        'risk_checks': {}, 'inputs': [], 'environment_versions': {}}
        self.task = {'schema_version': 2, 'id': 'TASK-fixture', 'base': self.git('rev-parse', 'HEAD').strip(),
                     'goal': 'Addition works', 'non_goals': [], 'kind': 'code', 'risks': [],
                     'acceptance': [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': []}]}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def check(self, code, format='command', **kw):
        row = {'argv': [sys.executable, '-c', code], 'cwd': '.', 'timeout': 5, 'purpose': 'Actual behavior',
               'format': format, 'required_cases': [], 'required_env': [], **kw}
        self.profile['checks']['unit'] = row
        self.profile['required_checks']['code'] = ['unit']
        self.task['acceptance'][0]['checks'] = ['unit']
        return row

    def run_check(self):
        profile_valid(self.profile, self.root)
        return execution.run(self.root, self.profile, self.task)

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
        (skill / 'scripts/bootstrap.py').write_text('import json\nprint(json.dumps({"ok":True,"skill_version":"2.1.0"}))')
        reply = {'ok': True, 'state': '0'*64, 'receipt': {'document_state': '0'*64}, 'task_status': 'completed', 'canonical_task_id': 'CS-T', 'task_revision': 1,
                 'files': ['.codestable/wiki/task.md'],
                 'records': [{'id': 'CS-T', 'path': '.codestable/wiki/task.md', 'relations': ['task-note']} ]}
        (skill / 'scripts/cs_knowledge.py').write_text('import json\nprint(' + repr(json.dumps(reply)) + ')')
        return skill

    def complete(self):
        self.check("import app; assert app.add(1,2)==3")
        skill = self.fake_cs()
        brief = self.root / '.team-workflow/brief.json'
        write(brief, knowledge.brief(self.root, self.task, skill, [], []))
        run_path, record = self.run_check()
        completion = self.root / '.team-workflow/knowledge.json'
        write(completion, knowledge.finish(self.root, self.task, skill, 'CS-T', brief, 'none', 'No stable new rule'))
        review_path = self.root / '.team-workflow/review.json'
        review = verification.review_template(self.root, self.profile, self.task, brief, completion)
        evidence = [artifact(self.root, self.root / 'app.py')]
        review.update(reviewer='test-evaluator', knowledge_conflicts_resolved=True)
        for key in ('standards', 'spec'):
            review[key] = {'status': 'passed', 'summary': 'Inspected final public function and outcome', 'evidence': evidence}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Executed assertion and inspected source', 'evidence': [artifact(self.root, run_path)]}]
        write(review_path, review)
        report = {'schema_version': 2, 'task_id': self.task['id'], 'runs': [run_path.relative_to(self.root).as_posix()],
                  'review': review_path.relative_to(self.root).as_posix(), 'knowledge': completion.relative_to(self.root).as_posix()}
        return skill, report, record

    def verify(self, skill, report):
        return verification.verify(self.root, self.profile, self.task, report, skill)

    def test_complete_uncommitted_task_and_empty_cards(self):
        (self.root / 'new.py').write_text('# existing uncommitted user work\n')
        skill, report, _ = self.complete()
        before = self.git('status', '--porcelain')
        self.assertTrue(self.verify(skill, report)['ok'])
        self.assertEqual(before, self.git('status', '--porcelain'))
        self.assertIn('?? new.py', before)

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
        self.assertIn('2.1.0', result['cs']['reason'])

    def test_source_change_invalidates_execution(self):
        skill, report, _ = self.complete()
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'stale'):
            self.verify(skill, report)

    def test_index_only_change_invalidates_review_and_run(self):
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        skill, report, _ = self.complete()
        self.git('add', 'app.py')
        with self.assertRaisesRegex(Invalid, 'stale'):
            self.verify(skill, report)

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

    def test_profile_and_acceptance_changes_expire_records(self):
        skill, report, _ = self.complete()
        self.task['acceptance'][0]['expectation'] = 'New requirement'
        with self.assertRaisesRegex(Invalid, 'stale'):
            self.verify(skill, report)
        self.task['acceptance'][0]['expectation'] = '1 + 2 is 3'
        self.profile['checks']['unit']['timeout'] = 6
        with self.assertRaisesRegex(Invalid, 'stale'):
            self.verify(skill, report)

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

    def test_manually_claimed_pass_without_run_blocked(self):
        skill, report, _ = self.complete()
        report['runs'] = []
        with self.assertRaisesRegex(Invalid, 'Required execution missing'):
            self.verify(skill, report)

    def test_artifact_edits_and_empty_artifacts_block(self):
        skill, report, record = self.complete()
        output = self.root / record['results'][0]['artifacts'][0]['path']
        for value in ('fabricated', ''):
            output.write_text(value)
            with self.assertRaises(Invalid):
                self.verify(skill, report)

    def test_review_must_cover_acceptance_and_knowledge(self):
        skill, report, _ = self.complete()
        path = self.root / report['review']
        old = read(path)
        for field, value in [('acceptance', []), ('knowledge_conflicts_resolved', False), ('knowledge', {})]:
            current = copy.deepcopy(old)
            current[field] = value
            write(path, current)
            with self.assertRaises(Invalid):
                self.verify(skill, report)

    def test_cs_unavailable_or_changed_blocks(self):
        skill, report, _ = self.complete()
        with self.assertRaises(Invalid):
            self.verify(self.root / 'missing', report)
        (self.root / '.codestable/wiki/task.md').write_text('changed')
        with self.assertRaisesRegex(Invalid, 'Knowledge changed'):
            self.verify(skill, report)

    def test_cs_note_must_reference_the_same_task(self):
        skill = self.fake_cs()
        brief = self.root / '.team-workflow/brief.json'
        write(brief, knowledge.brief(self.root, self.task, skill, [], []))
        (self.root / '.codestable/wiki/task.md').write_text('Another task')
        with self.assertRaisesRegex(Invalid, 'reference this workflow task'):
            knowledge.finish(self.root, self.task, skill, 'CS-T', brief, 'none', 'Nothing new')

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

    def test_v1_report_is_never_accepted_as_execution(self):
        skill, report, _ = self.complete()
        report['schema_version'] = 1
        with self.assertRaisesRegex(Invalid, 'material-only'):
            self.verify(skill, report)

    def test_joint_record_binds_all_participating_sources(self):
        skill, report, record = self.complete()
        # A second independent repository with its own final evidence.
        other = WorkflowCases(methodName='test_complete_uncommitted_task_and_empty_cards')
        other.setUp()
        self.addCleanup(other.doCleanups)
        other.profile['project'] = 'second'
        other_skill, other_report, _ = other.complete()
        entries = []
        for fixture, rep in ((self, report), (other, other_report)):
            write(fixture.root / '.team-workflow/profile.json', fixture.profile)
            write(fixture.root / '.team-workflow/task.json', fixture.task)
            write(fixture.root / '.team-workflow/delivery.json', rep)
            entries.append({'root': str(fixture.root), 'profile': '.team-workflow/profile.json',
                            'task': '.team-workflow/task.json', 'report': '.team-workflow/delivery.json'})
        manifest = {'schema_version': 2, 'task_id': self.task['id'], 'participants': entries, 'joint': 'sample'}
        before = verification.participant_binding(manifest)
        (other.root / 'app.py').write_text('changed')
        self.assertNotEqual(before, verification.participant_binding(manifest))
        with self.assertRaises(Invalid):
            verification.aggregate(manifest, skill)

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
            verification.scenario_review(self.root, out, check, captures)
        report = {'schema_version': 1, 'reviewer': 'codex', 'run_id': 'scenario-1',
                  'status': 'PASS', 'scenario_run_status': 'COMPLETED', 'summary': 'Reviewed full fixture',
                  'findings': [], 'reviewed_artifacts': {Path(k).name: 'sha256:' + v for k, v in captures.items()}}
        write(out / 'codex-review.json', report)
        verification.scenario_review(self.root, out, check, captures)
        report['run_id'] = 'old-run'
        write(out / 'codex-review.json', report)
        with self.assertRaises(Invalid):
            verification.scenario_review(self.root, out, check, captures)
        report['run_id'] = 'scenario-1'
        write(out / 'codex-review.json', report)
        write(out / 'suite-transcript.json', {'actual': 'changed'})
        with self.assertRaises(Invalid):
            verification.scenario_review(self.root, out, check, captures)

    def test_joint_success_requires_real_joint_run_binding(self):
        self.task['risks'] = ['cross-service']
        self.profile['risk_checks'] = {'cross-service': ['unit']}
        skill, report, record = self.complete()
        other = WorkflowCases(methodName='test_complete_uncommitted_task_and_empty_cards')
        other.setUp()
        self.addCleanup(other.doCleanups)
        other.profile['project'] = 'second'
        _, other_report, _ = other.complete()
        entries = []
        for fixture, rep in ((self, report), (other, other_report)):
            write(fixture.root / '.team-workflow/profile.json', fixture.profile)
            write(fixture.root / '.team-workflow/task.json', fixture.task)
            write(fixture.root / '.team-workflow/delivery.json', rep)
            entries.append({'root': str(fixture.root), 'profile': '.team-workflow/profile.json',
                            'task': '.team-workflow/task.json', 'report': '.team-workflow/delivery.json'})
        manifest = {'schema_version': 2, 'task_id': self.task['id'], 'participants': entries, 'joint': 'sample'}
        with self.assertRaisesRegex(Invalid, 'Joint evidence'):
            verification.aggregate(manifest, skill)
        run_path = self.root / report['runs'][0]
        record['participants'] = verification.participant_binding(manifest)
        record['participants_unchanged'] = True
        write(run_path, record)
        review_path = self.root / report['review']
        review = read(review_path)
        review['acceptance'][0]['evidence'] = [artifact(self.root, run_path)]
        write(review_path, review)
        self.assertTrue(verification.aggregate(manifest, skill)['ok'])
        (other.root / 'new-change.txt').write_text('changed after joint run')
        with self.assertRaises(Invalid):
            verification.aggregate(manifest, skill)

    def test_stale_tool_and_missing_native_artifact_rejected(self):
        skill, report, record = self.complete()
        record['tools']['version'] = 'old'
        write(self.root / report['runs'][0], record)
        with self.assertRaisesRegex(Invalid, 'tools changed'):
            self.verify(skill, report)

    def test_project_rejects_unknown_format_and_output_escape(self):
        self.check('print(1)')
        self.profile['checks']['unit']['format'] = 'invented'
        with self.assertRaises(Invalid):
            profile_valid(self.profile, self.root)
        with self.assertRaises(Invalid):
            execution.output_path(self.root, self.root / '.team-workflow', '{output}/../escape')

    def test_migration_does_not_write_or_upgrade_evidence(self):
        wiki = self.root / '.codestable/wiki'
        wiki.mkdir(parents=True)
        (wiki / 'INDEX.md').write_text('Knowledge')
        old = {'schema_version': 1, 'project': 'old', 'context': ['AGENTS.md'],
               'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
               'checks': {'unit': {'argv': ['python3', '-m', 'unittest'], 'purpose': 'Run tests'}},
               'required_checks': ['unit'], 'risk_checks': {}}
        write(self.root / '.team-workflow.json', old)
        before = (self.root / '.team-workflow.json').read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(workflow.main(['migrate', '--root', str(self.root)]), 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result['requires_review'])
        self.assertEqual(result['profile']['checks']['unit']['format'], 'command')
        self.assertEqual(before, (self.root / '.team-workflow.json').read_bytes())

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

    def test_failure_reports_unexamined_layers_honestly(self):
        skill, report, _ = self.complete()
        (self.root / 'app.py').write_text('changed')
        try:
            self.verify(skill, report)
            self.fail('Expected stale evidence to block')
        except verification.Incomplete as exc:
            self.assertEqual(exc.layers['execution'], 'incomplete')
            self.assertEqual(exc.layers['review'], 'not-evaluated')
            self.assertEqual(exc.layers['knowledge'], 'not-evaluated')

    def test_external_workspace_input_changes_evidence(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        path = Path(outside.name) / 'go.work'
        path.write_text('workspace A')
        self.profile['external_inputs'] = {'workspace': {'kind': 'file', 'path': str(path)}}
        profile_valid(self.profile, self.root)
        before = snapshot(self.root, self.profile)
        path.write_text('workspace B')
        self.assertNotEqual(before, snapshot(self.root, self.profile))

    def test_malformed_execution_record_is_incomplete_not_traceback(self):
        skill, report, _ = self.complete()
        write(self.root / report['runs'][0], [])
        with self.assertRaisesRegex(verification.Incomplete, 'Invalid execution record'):
            self.verify(skill, report)


if __name__ == '__main__':
    unittest.main()
