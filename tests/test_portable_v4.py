"""Portable v4 execution from real commands and provider-bound original archives."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile

import test_workflow as fixtures
from common import Invalid, artifact, now, read, write
import delivery
import designs
import github_read
import knowledge
import portable
import portable_v4
import validation


class PortableCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs

    def prepare(self, xml=None, **options):
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.profile['schema_version'] = 4
        self.task.update(schema_version=4, design_id='addition', section_ids=['T1'])
        self.configure_check(xml, **options)

    def configure_check(self, xml=None, **options):
        xml = xml if xml is not None else '<testsuite tests="1"><testcase classname="Arithmetic" name="adds"/></testsuite>'
        code = 'import app,sys; from pathlib import Path; assert app.add(1,2)==3; Path(sys.argv[1]).write_text(' + repr(xml) + ')'
        row = self.check(code, format='junit', report='{output}/junit.xml',
                         environment={'kind': 'stateless'}, **options)
        row['argv'].append('{output}/junit.xml')
        row['required_cases'] = ['Arithmetic::adds']

    def capture(self, provider=True):
        self.directory = self.root / '.team-workflow/ci' / uuid.uuid4().hex
        context = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'example/project',
                   'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'test'} if provider else {'GITHUB_ACTIONS': 'false'}
        with patch.dict(os.environ, context):
            before = portable.source_state(self.root, self.profile)
            start = now()
            row = validation.capture(self.root, self.profile, 'unit', self.directory)
            finish = now()
            after = portable.source_state(self.root, self.profile)
            manifest = portable_v4.capture(self.directory, self.profile, row, before, after, start, finish)
        self.archive_manifest = manifest
        self.pack()
        return manifest

    def pack(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zipped:
            for path in self.directory.rglob('*'):
                if path.is_file():
                    zipped.write(path, path.relative_to(self.directory).as_posix())
        self.archive = archive.getvalue()
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        finish = datetime.now(timezone.utc) + timedelta(minutes=1)
        self.locator = {'kind': 'github-actions', 'repository': 'example/project', 'run_id': 17,
                        'attempt': 2, 'job_id': 21, 'artifact_id': 22}
        self.run = {'run_attempt': 2, 'head_sha': self.task['base'], 'status': 'completed', 'conclusion': 'success'}
        self.job = {'run_id': 17, 'run_attempt': 2, 'name': 'test (3.13)', 'status': 'completed', 'conclusion': 'success',
                    'started_at': start.isoformat(), 'completed_at': finish.isoformat()}
        self.artifact_info = {'expired': False, 'created_at': now(),
                              'digest': 'sha256:' + hashlib.sha256(self.archive).hexdigest(),
                              'workflow_run': {'id': 17, 'head_sha': self.task['base']}}

    def api(self, endpoint, **kwargs):
        if endpoint.endswith('/actions/runs/17'):
            return copy.deepcopy(self.run)
        if endpoint.endswith('/actions/jobs/21'):
            return copy.deepcopy(self.job)
        if endpoint.endswith('/actions/artifacts/22'):
            return copy.deepcopy(self.artifact_info)
        if endpoint.endswith('/actions/artifacts/22/zip'):
            return self.archive
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Unexpected provider endpoint: ' + endpoint)

    def import_result(self):
        with patch.object(github_read, 'api', side_effect=self.api):
            return portable_v4.import_result(self.root, self.profile, self.locator)

    def test_capture_and_import_redecode_original_case_with_portable_paths(self):
        self.prepare()
        manifest = self.capture()
        self.assertNotIn(str(self.directory), json.dumps(manifest))
        path, record = self.import_result()
        with patch.object(github_read, 'api', side_effect=self.api):
            result, original = portable_v4.validate_import(self.root, self.profile, read(path))
        self.assertEqual(record['kind'], 'imported-execution')
        self.assertEqual(result['cases'], {'Arithmetic::adds': 'passed'})
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(original['source_before']['repositories']['example/project']['commit'], self.task['base'])
        self.assertTrue(all(not Path(row['path']).is_absolute() for row in result['artifacts']))
        self.assertEqual(record['started_at'], original['started_at'])

    def test_imported_bundle_survives_checkout_relocation(self):
        self.prepare()
        self.capture()
        path, record = self.import_result()
        self.assertNotIn(str(self.root), json.dumps(record))
        with tempfile.TemporaryDirectory() as temporary:
            relocated = Path(temporary) / 'relocated'
            shutil.copytree(self.root, relocated)
            with patch.object(github_read, 'api', side_effect=self.api):
                result, _ = portable_v4.validate_import(relocated, self.profile, read(relocated / path.relative_to(self.root)))
            self.assertEqual(result['cases'], {'Arithmetic::adds': 'passed'})

    def test_same_content_new_commit_preserves_actually_tested_commit(self):
        self.prepare()
        self.capture()
        tested = self.task['base']
        self.git('commit', '--allow-empty', '-qm', 'metadata only')
        current = self.git('rev-parse', 'HEAD').strip()
        self.assertNotEqual(tested, current)
        _, imported = self.import_result()
        self.assertEqual(imported['tested_source']['repositories']['example/project']['commit'], tested)
        self.assertEqual(imported['import_source']['repositories']['example/project']['commit'], current)

    def test_revision_sensitive_execution_rejects_a_different_commit(self):
        self.prepare(revision_sensitive=True)
        self.capture()
        self.git('commit', '--allow-empty', '-qm', 'metadata only')
        with self.assertRaisesRegex(Invalid, 'source changed'):
            self.import_result()

    def test_changed_source_and_newer_provider_attempt_are_rejected(self):
        self.prepare()
        self.capture()
        (self.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'unshared changes'):
            self.import_result()
        self.git('restore', 'app.py')
        self.run['run_attempt'] = 3
        with self.assertRaisesRegex(Invalid, 'newer run attempt'):
            self.import_result()

    def test_original_outputs_cannot_be_replaced_with_a_success_summary(self):
        self.prepare('<testsuite tests="0"/>')
        self.capture()
        manifest_path = self.directory / 'result.json'
        manifest = read(manifest_path)
        manifest['execution'].update(status='passed', cases={'Arithmetic::adds': 'passed'})
        write(manifest_path, manifest)
        self.pack()
        with self.assertRaisesRegex(Invalid, 'Original reports do not confirm'):
            self.import_result()

    def test_required_skipped_case_and_absent_provider_context_cannot_pass(self):
        self.prepare('<testsuite tests="1"><testcase classname="Arithmetic" name="adds"><skipped/></testcase></testsuite>')
        self.capture()
        with self.assertRaisesRegex(Invalid, 'did not pass'):
            self.import_result()
        self.configure_check()
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'outer/runner',
                                     'GITHUB_RUN_ID': '999', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'validate'}):
            self.capture(provider=False)
        self.assertIsNone(self.archive_manifest['run_context'])
        with self.assertRaisesRegex(Invalid, 'provider context'):
            self.import_result()

    def test_changed_fixture_identity_requires_fresh_validation(self):
        self.prepare()
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture',
            'identity': [sys.executable, '-c', 'import os; print(os.environ["FIXTURE_VERSION"])']}
        with patch.dict(os.environ, {'FIXTURE_VERSION': 'database-1'}):
            self.capture()
        with patch.dict(os.environ, {'FIXTURE_VERSION': 'database-2'}):
            with self.assertRaisesRegex(Invalid, 'environment changed'):
                self.import_result()

    def test_declared_frontend_repository_is_executed_and_captured(self):
        self.prepare()
        frontend = self.root / '.team-workflow/frontend'
        frontend.mkdir(parents=True)
        for argv in [('init', '-q'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'user.name', 'Fixture'), ('config', 'commit.gpgsign', 'false'),
                     ('remote', 'add', 'origin', 'https://github.com/example/frontend.git')]:
            subprocess.check_call(['git', '-C', str(frontend), *argv])
        (frontend / 'app.py').write_text('def frontend_behavior(): return "frontend-only"\n')
        (frontend / '.gitignore').write_text('__pycache__/\n')
        subprocess.check_call(['git', '-C', str(frontend), 'add', '.'])
        subprocess.check_call(['git', '-C', str(frontend), 'commit', '-qm', 'frontend fixture'])
        write(self.root / '.team-workflow/local.json', {'repositories': {'example/frontend': str(frontend)}})
        self.profile['external_inputs'] = {'web': {'kind': 'repository', 'repository': 'example/frontend', 'role': 'modified'}}
        check = self.profile['checks']['unit']
        check['repository'] = 'example/frontend'
        check['argv'][2] = check['argv'][2].replace('assert app.add(1,2)==3', 'assert app.frontend_behavior()=="frontend-only"')
        manifest = self.capture()
        _, imported = self.import_result()
        self.assertEqual(imported['result']['repository'], 'example/frontend')
        self.assertEqual(set(manifest['source_before']['repositories']), {'example/project', 'example/frontend'})
        self.assertEqual(imported['result']['cases'], {'Arithmetic::adds': 'passed'})

    def test_provider_head_and_download_digest_must_match_original_execution(self):
        self.prepare()
        self.capture()
        self.run['head_sha'] = '1' * 40
        self.artifact_info['workflow_run']['head_sha'] = '1' * 40
        with self.assertRaisesRegex(Invalid, 'actually tested checkout'):
            self.import_result()
        self.run['head_sha'] = self.task['base']
        self.artifact_info['workflow_run']['head_sha'] = self.task['base']
        self.archive += b'altered after provider digest'
        with self.assertRaisesRegex(Invalid, 'provider digest'):
            self.import_result()

    def test_source_mutated_during_execution_and_missing_environment_are_not_proof(self):
        self.prepare()
        self.profile['checks']['unit']['argv'][2] += '; Path("app.py").write_text("changed = True\\n")'
        self.capture()
        self.git('restore', 'app.py')
        with self.assertRaisesRegex(Invalid, 'unshared changes|changed during'):
            self.import_result()
        self.configure_check()
        self.capture()
        path = self.directory / 'result.json'
        value = read(path)
        del value['execution']['binding']['environment']
        write(path, value)
        self.pack()
        with self.assertRaisesRegex(Invalid, 'environment'):
            self.import_result()

    def test_explicit_ci_target_allows_a_different_local_host_without_inference(self):
        self.prepare()
        self.profile['environment_versions']['python'] = [sys.executable, '--version']
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture',
            'identity': [sys.executable, '-c', 'print("fixture-v1")']}
        target = validation.environment(self.root, self.profile, self.profile['checks']['unit'])
        target['runtime'].update(platform='Linux', machine='x86_64')
        self.profile['checks']['unit']['environment']['target'] = target
        # Only public OS metadata is a boundary fixture. The command, source
        # capture and original JUnit report are still executed normally.
        with patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'):
            self.capture()
        _, imported = self.import_result()
        self.assertEqual(imported['result']['binding']['environment'], target)
        self.assertEqual(target['versions']['python']['command'], [sys.executable, '--version'])
        self.assertEqual(target['fixture']['identity'], 'fixture-v1')
        with self.assertRaisesRegex(Invalid, 'environment|target'):
            validation.capture(self.root, self.profile, 'unit', self.root / '.team-workflow/local-incompatible')

    def test_remote_target_must_match_complete_recorded_environment(self):
        self.prepare()
        target = validation.environment(self.root, self.profile, self.profile['checks']['unit'])
        target['runtime'].update(platform='Linux', machine='x86_64')
        self.profile['checks']['unit']['environment']['target'] = target
        with patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'):
            self.capture()
        path = self.directory / 'result.json'
        manifest = read(path)
        del manifest['execution']['binding']['environment']['runtime']['machine']
        write(path, manifest)
        self.pack()
        with self.assertRaisesRegex(Invalid, 'environment'):
            self.import_result()


class AggregateCases(unittest.TestCase):
    """Actual local execution, review and CS protocol responses across three repos."""

    def setUp(self):
        self.fixtures, self.roots = {}, {}
        for name in ('core', 'gateway', 'common'):
            fixture = fixtures.WorkflowCases()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.git('remote', 'add', 'origin', 'https://github.com/example/' + name + '.git')
            fixture.profile.update(schema_version=4, project=name)
            fixture.task.update(schema_version=4, id='TASK-' + name, parent='JOINT-fixture',
                                design_id='design-' + name, section_ids=['T1'], paths=['app.py'])
            fixture.check('import app; assert app.add(1,2)==3', environment={'kind': 'stateless'})
            fixture.skill = fixture.fake_cs()
            self.fixtures[name] = fixture
            self.roots['example/' + name] = fixture.root
        core = self.fixtures['core']
        self.root = core.root
        self.skill = core.skill
        core.task['risks'] = ['cross-service']
        core.profile['risk_checks'] = {'cross-service': ['unit']}
        core.profile['external_inputs'] = {
            'gateway': {'kind': 'repository', 'repository': 'example/gateway', 'role': 'joint'},
            'common': {'kind': 'repository', 'repository': 'example/common', 'role': 'build'}}
        write(core.root / '.team-workflow/local.json', {'repositories': {
            key: str(value) for key, value in self.roots.items() if key != 'example/core'}})
        core.profile['checks']['unit']['argv'][2] = (
            'import app, json, importlib.util; from pathlib import Path; assert app.add(1,2)==3; '
            'locations=json.loads(Path(".team-workflow/local.json").read_text())["repositories"]; '
            '\nfor repo in ("example/gateway","example/common"):\n'
            ' spec=importlib.util.spec_from_file_location("dependency", str(Path(locations[repo])/"app.py")); '
            'module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); assert module.add(1,2)==3\n'
            'print("joint public arithmetic behavior passed")')
        # A real CS installation accepts --root for every project. The process
        # fixture returns each project's note identity from that actual root.
        script = self.skill / 'scripts/cs_knowledge.py'
        script.write_text('import json,sys\nfrom pathlib import Path\n'
            'root=Path(sys.argv[sys.argv.index("--root")+1])\n'
            'task=(root/".codestable/wiki/task.md").read_text().splitlines()[0]\n'
            'print(json.dumps({"ok":True,"kind":"receipt-check","read_only":True,"query_state":{},'
            '"changed":[],"receipt":{"query_state":{}},"task_status":"completed",'
            '"canonical_task_id":"CS-T","task_revision":1,"files":[".codestable/wiki/task.md"],'
            '"records":[{"id":"CS-T","path":".codestable/wiki/task.md","relations":["task-note"]}],'
            '"external_refs":[{"system":"team-workflow","id":task}]}))\n')
        self.manifest = {'schema_version': 4, 'task_id': 'JOINT-fixture', 'joint': 'example/core',
            'participants': [{'repository': 'example/' + name, 'commit': fixture.task['base'],
                'profile': '.team-workflow/profile.json', 'task': '.team-workflow/task.json',
                'report': '.team-workflow/report.json'}
                for name, fixture in self.fixtures.items() if name != 'common'],
            'dependencies': [{'repository': 'example/common', 'commit': self.fixtures['common'].task['base']}]}
        for name in ('core', 'gateway'):
            self.complete(self.fixtures[name], portable_run=name == 'core')

    def complete(self, fixture, portable_run=False):
        root, profile, task = fixture.root, fixture.profile, fixture.task
        design = {'schema_version': 4, 'kind': 'design', 'id': task['design_id'], 'revision': 1,
            'task_id': task['id'], 'assessment': {'complexity': 'medium', 'risks': list(task['risks']),
                'effort': 'one hour', 'drivers': ['arithmetic behavior'], 'uncertainties': [], 'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Scope', 'body': task['goal'], 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Result', 'body': task['acceptance'][0]['expectation'],
                 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Work', 'body': 'Check public behavior',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []}, 'depends_on': []}]}
        def save(name, value):
            write(root / '.team-workflow' / (name + '.json'), value)
            return '.team-workflow/' + name + '.json'
        save('profile', profile)
        save('task', task)
        brief = save('brief', knowledge.brief(root, task, self.skill, [], []))
        run, _ = validation.run_batch(root, profile, [task], portable=portable_run)
        approval = designs.approval_draft(design, 'carol', 'Confirmed scope and testable acceptance')
        report = {'schema_version': 4, 'task_id': task['id'], 'design': save('design', design),
            'approvals': [save('approval', approval)], 'brief': brief, 'runs': [run.relative_to(root).as_posix()],
            'review': '.team-workflow/review.json'}
        review = delivery.review_template(root, profile, task, report)
        ref = artifact(root, run)
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read actual public behavior and executed results', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Observed the declared arithmetic result', 'evidence': [ref]}]
        save('review', review)
        accepted = delivery.verify(root, profile, task, report, self.skill, 'acceptance')
        save('acceptance', accepted)
        completion = knowledge.finish_v4(root, profile, task, self.skill, 'CS-T', root / brief,
            'none', 'Existing requirement remains sufficient', root / '.team-workflow/acceptance.json')
        report['knowledge'] = save('knowledge', completion)
        save('report', report)

    def api(self, endpoint, **kwargs):
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Unexpected aggregate provider call: ' + endpoint)

    def aggregate(self, manifest=None):
        with patch.object(github_read, 'api', side_effect=self.api):
            return portable_v4.aggregate(self.root, manifest or self.manifest, self.roots, self.skill)

    def test_joint_execution_covers_both_deliveries_and_build_dependency(self):
        result = self.aggregate()
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])
        self.assertEqual(set(result['versions']), {'example/core', 'example/gateway', 'example/common'})
        self.assertEqual(len(result['participants']), 2)
        self.assertEqual(set(result['tested_versions'][0]['repositories']), set(result['versions']))

    def test_omitted_build_input_or_missing_joint_source_capture_is_rejected(self):
        missing = copy.deepcopy(self.manifest)
        missing['dependencies'] = []
        with self.assertRaisesRegex(Invalid, 'omits or mismatches'):
            self.aggregate(missing)
        self.complete(self.fixtures['core'], portable_run=False)
        with self.assertRaisesRegex(Invalid, 'not captured during execution'):
            self.aggregate()

    def test_joint_execution_must_capture_every_declared_repository(self):
        core = self.fixtures['core']
        del core.profile['external_inputs']['common']
        self.complete(core, portable_run=True)
        with self.assertRaisesRegex(Invalid, 'execution omits'):
            self.aggregate()

    def test_modified_repository_cannot_hide_as_an_unreviewed_build_dependency(self):
        core = self.fixtures['core']
        core.profile['external_inputs']['common']['role'] = 'modified'
        write(core.root / '.team-workflow/profile.json', core.profile)
        with self.assertRaisesRegex(Invalid, 'no verified participant delivery'):
            self.aggregate()

    def test_dirty_dependency_and_unaccepted_participant_cannot_deliver(self):
        common = self.fixtures['common']
        (common.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'unshared changes'):
            self.aggregate()
        common.git('restore', 'app.py')
        gateway = self.fixtures['gateway']
        review_path = gateway.root / '.team-workflow/review.json'
        review = read(review_path)
        review['spec']['status'] = 'pending'
        write(review_path, review)
        with self.assertRaisesRegex(Invalid, 'has not passed'):
            self.aggregate()

    def test_wrong_parent_or_missing_checkout_is_not_a_joint_delivery(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['task_id'] = 'unrelated-work'
        with self.assertRaisesRegex(Invalid, 'another parent'):
            self.aggregate(manifest)
        del self.roots['example/common']
        with self.assertRaisesRegex(Invalid, 'checkout mapping'):
            self.aggregate()

    def test_joint_reuse_reports_original_commits_after_metadata_only_changes(self):
        common = self.fixtures['common']
        tested = common.task['base']
        common.git('commit', '--allow-empty', '-qm', 'new commit without source changes')
        current = common.git('rev-parse', 'HEAD').strip()
        self.manifest['dependencies'][0]['commit'] = current
        result = self.aggregate()
        self.assertEqual(result['versions']['example/common'], current)
        self.assertEqual(result['tested_versions'][0]['repositories']['example/common'], tested)


if __name__ == '__main__':
    unittest.main()
