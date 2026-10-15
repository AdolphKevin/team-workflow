"""Portable execution from real commands and provider-bound original archives."""
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
import plan_fixtures as plans
from common import Invalid, artifact, now, read, write
import delivery
import designs
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import knowledge
import portable
import validation


class PortableCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def prepare(self, xml=None, **options):
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.profile['platform'] = copy.deepcopy(PLATFORM_CONFIG)
        fixtures.write_config(self.root, self.profile)
        self.git('add', '.tw/config.json')
        self.git('commit', '-qm', 'platform fixture configuration')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.task['design_id'] = 'addition'
        self.configure_check(xml, **options)

    def configure_check(self, xml=None, **options):
        xml = xml if xml is not None else '<testsuite tests="1"><testcase classname="Arithmetic" name="adds"/></testsuite>'
        code = 'import app,sys; from pathlib import Path; assert app.add(1,2)==3; Path(sys.argv[1]).write_text(' + repr(xml) + ')'
        row = self.check(code, format='junit', report='{output}/junit.xml',
                         environment={'kind': 'stateless'}, **options)
        row['argv'].append('{output}/junit.xml')
        row['required_cases'] = ['Arithmetic::adds']

    def capture(self, provider=True):
        self.directory = self.root / '.tw/local/ci' / uuid.uuid4().hex
        context = {'TW_RUN_CONTEXT': json.dumps({'repository': 'github.com/example/project',
                   'run_id': '17', 'attempt': '2', 'job': 'test'}) if provider else ''}
        with patch.dict(os.environ, context):
            before = portable.source_state(self.root, self.profile)
            start = now()
            row = validation.capture(self.root, self.profile, 'unit', self.directory)
            finish = now()
            after = portable.source_state(self.root, self.profile)
            manifest = portable.capture(self.directory, self.profile, row, before, after, start, finish)
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
        self.locator = {'kind': 'github-actions', 'repository': 'github.com/example/project', 'run_id': 17,
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
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.api)):
            return portable.import_result(self.root, self.profile, self.locator)

    def test_capture_and_import_redecode_original_case_with_portable_paths(self):
        self.prepare()
        manifest = self.capture()
        self.assertNotIn(str(self.directory), json.dumps(manifest))
        path, record = self.import_result()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.api)):
            result, original = portable.validate_import(self.root, self.profile, read(path))
        self.assertEqual(record['kind'], 'imported-execution')
        self.assertEqual(result['cases'], {'Arithmetic::adds': 'passed'})
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(original['source_before']['repositories']['github.com/example/project']['commit'], self.task['base'])
        self.assertTrue(all(not Path(row['path']).is_absolute() for row in result['artifacts']))
        self.assertEqual(record['started_at'], original['started_at'])

    def test_shared_import_reevaluates_portable_command_paths(self):
        self.prepare()
        self.profile['checks']['unit']['required_cases'] = ['adds']
        self.capture()
        self.assertEqual(self.archive_manifest['execution']['status'], 'incomplete')
        self.profile['checks']['unit']['required_cases'] = ['Arithmetic::adds']
        _, record = self.import_result()
        self.assertIn('{output}/junit.xml', record['result']['argv'])
        self.assertEqual(validation.inspect_record(self.root, self.profile, record), {'unit'})
        self.profile['checks']['unit']['required_cases'] = ['Arithmetic::missing']
        with self.assertRaisesRegex(Invalid, 'Arithmetic::missing'):
            validation.inspect_record(self.root, self.profile, record)

    def test_imported_bundle_survives_checkout_relocation(self):
        self.prepare()
        self.capture()
        path, record = self.import_result()
        self.assertNotIn(str(self.root), json.dumps(record))
        with tempfile.TemporaryDirectory() as temporary:
            relocated = Path(temporary) / 'relocated'
            shutil.copytree(self.root, relocated)
            with patch.object(platform_read, 'call', side_effect=platform_transport(self.api)):
                result, _ = portable.validate_import(relocated, self.profile, read(relocated / path.relative_to(self.root)))
            self.assertEqual(result['cases'], {'Arithmetic::adds': 'passed'})

    def test_portable_batch_templates_stay_current_after_move(self):
        self.prepare()
        path, record = validation.run_batch(self.root, self.profile, [self.task], portable=True)
        row = record['results'][0]
        self.assertEqual(row['status'], 'passed', row)
        self.assertEqual(row['argv'], self.profile['checks']['unit']['argv'])
        original = self.root
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary).resolve() / 'moved'
            shutil.move(original, self.root)
            names = [path.relative_to(original).as_posix()]
            result = validation.verify_runs(self.root, self.profile, self.task, names)
            self.assertEqual(result['results']['unit']['cases'], {'Arithmetic::adds': 'passed'})
            manifest_path = self.root / row['portable']['path']
            normalized = portable.validate_result(self.root, self.profile, read(manifest_path), manifest_path.parent)
            self.assertEqual(normalized, {key: value for key, value in row.items() if key != 'portable'})

    def test_same_content_new_commit_preserves_actually_tested_commit(self):
        self.prepare()
        self.capture()
        tested = self.task['base']
        self.git('commit', '--allow-empty', '-qm', 'metadata only')
        current = self.git('rev-parse', 'HEAD').strip()
        self.assertNotEqual(tested, current)
        _, imported = self.import_result()
        self.assertEqual(imported['tested_source']['repositories']['github.com/example/project']['commit'], tested)
        self.assertEqual(imported['import_source']['repositories']['github.com/example/project']['commit'], current)

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
        with self.assertRaisesRegex(Invalid, 'Required case missing or not passed: Arithmetic::adds'):
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

    def test_imported_execution_reuses_recorded_environment_offline(self):
        self.prepare()
        marker = self.root / '.tw/local/fixture-id.txt'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('isolated-database-1')
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture',
            'identity': [sys.executable, '-c',
                "from pathlib import Path; print(Path('.tw/local/fixture-id.txt').read_text())"]}
        self.capture()
        path, _ = self.import_result()
        names = [path.relative_to(self.root).as_posix()]
        marker.unlink()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.api)):
            result = validation.verify_runs(self.root, self.profile, self.task, names, live=False)
            self.assertEqual(result['results']['unit']['cases'], {'Arithmetic::adds': 'passed'})
            self.assertEqual(result['results']['unit']['binding']['environment']['fixture']['identity'],
                             'isolated-database-1')
            with self.assertRaisesRegex(Invalid, 'Cannot confirm environment identity'):
                validation.verify_runs(self.root, self.profile, self.task, names)
            self.run['run_attempt'] = 3
            with self.assertRaisesRegex(Invalid, 'newer run attempt'):
                validation.verify_runs(self.root, self.profile, self.task, names, live=False)
            self.run['run_attempt'] = 2
            (self.root / 'app.py').write_text('def add(a,b): return 0\n')
            with self.assertRaisesRegex(Invalid, '[Ss]ource|unshared changes'):
                validation.verify_runs(self.root, self.profile, self.task, names, live=False)

    def test_declared_frontend_repository_is_executed_and_captured(self):
        self.prepare()
        frontend = self.root / '.tw/local/frontend'
        frontend.mkdir(parents=True)
        for argv in [('init', '-q'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'user.name', 'Fixture'), ('config', 'commit.gpgsign', 'false'),
                     ('remote', 'add', 'origin', 'https://github.com/example/frontend.git')]:
            subprocess.check_call(['git', '-C', str(frontend), *argv])
        (frontend / 'app.py').write_text('def frontend_behavior(): return "frontend-only"\n')
        (frontend / '.gitignore').write_text('__pycache__/\n')
        subprocess.check_call(['git', '-C', str(frontend), 'add', '.'])
        subprocess.check_call(['git', '-C', str(frontend), 'commit', '-qm', 'frontend fixture'])
        write(self.root / '.tw/local/repositories.json', {'repositories': {'github.com/example/frontend': str(frontend)}})
        self.profile['external_inputs'] = {'web': {'kind': 'repository', 'repository': 'github.com/example/frontend', 'role': 'modified'}}
        check = self.profile['checks']['unit']
        check['repository'] = 'github.com/example/frontend'
        check['argv'][2] = check['argv'][2].replace('assert app.add(1,2)==3', 'assert app.frontend_behavior()=="frontend-only"')
        manifest = self.capture()
        _, imported = self.import_result()
        self.assertEqual(imported['result']['repository'], 'github.com/example/frontend')
        self.assertEqual(set(manifest['source_before']['repositories']), {'github.com/example/project', 'github.com/example/frontend'})
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
        with patch('platform.system', return_value='Darwin'), patch('platform.machine', return_value='arm64'):
            with self.assertRaisesRegex(Invalid, 'environment|target'):
                validation.capture(self.root, self.profile, 'unit', self.root / '.tw/local/local-incompatible')

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
    """Actual local execution and review across three repositories."""

    def setUp(self):
        self.fixtures, self.roots = {}, {}
        for name in ('core', 'gateway', 'common'):
            fixture = fixtures.WorkflowCases()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.git('remote', 'add', 'origin', 'https://github.com/example/' + name + '.git')
            fixture.profile['project'] = name
            fixture.task.update(id='TASK-' + name, parent='JOINT-fixture',
                                design_id='design-' + name, section_ids=['T1'], paths=['app.py'], acceptance_scope='task')
            fixture.check('import app; assert app.add(1,2)==3')
            self.fixtures[name] = fixture
            self.roots['github.com/example/' + name] = fixture.root
        core = self.fixtures['core']
        self.root = core.root
        core.task['risks'] = ['cross-service']
        core.profile['risk_checks'] = {'cross-service': ['unit']}
        core.profile['external_inputs'] = {
            'gateway': {'kind': 'repository', 'repository': 'github.com/example/gateway', 'role': 'joint'},
            'common': {'kind': 'repository', 'repository': 'github.com/example/common', 'role': 'build'}}
        write(core.root / '.tw/local/repositories.json', {'repositories': {
            key: str(value) for key, value in self.roots.items() if key != 'github.com/example/core'}})
        core.profile['checks']['unit']['argv'][2] = (
            'import app, json, importlib.util; from pathlib import Path; assert app.add(1,2)==3; '
            'locations=json.loads(Path(".tw/local/repositories.json").read_text())["repositories"]; '
            '\nfor repo in ("github.com/example/gateway","github.com/example/common"):\n'
            ' spec=importlib.util.spec_from_file_location("dependency", str(Path(locations[repo])/"app.py")); '
            'module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); assert module.add(1,2)==3\n'
            'print("joint public arithmetic behavior passed")')
        for fixture in self.fixtures.values():
            fixtures.write_config(fixture.root, fixture.profile)
            fixture.git('add', '.tw/config.json')
            fixture.git('commit', '-qm', 'configure participant checks')
            fixture.task['base'] = fixture.git('rev-parse', 'HEAD').strip()
        self.manifest = {'data_version': 1, 'task_id': 'JOINT-fixture', 'joint': 'github.com/example/core',
            'participants': [{'repository': 'github.com/example/' + name, 'commit': fixture.task['base'],
                'profile': '.tw/config.json', 'task': '.tw/local/task.json',
                'report': '.tw/local/report.json'}
                for name, fixture in self.fixtures.items() if name != 'common'],
            'dependencies': [{'repository': 'github.com/example/common', 'commit': self.fixtures['common'].task['base']}]}
        for name in ('core', 'gateway'):
            self.complete(self.fixtures[name], portable_run=name == 'core')
        from types import SimpleNamespace
        parent_task = {**self.fixtures['core'].task, 'id': 'JOINT-fixture', 'design_id': 'joint-requirement', 'acceptance_scope': 'requirement'}
        parent_task.pop('parent', None)
        self.parent_fixture = SimpleNamespace(root=self.root, profile=self.fixtures['core'].profile, task=parent_task)
        self.complete(self.parent_fixture, prefix='parent-', knowledge_complete=False)
        self.manifest['requirement'] = {'repository': 'github.com/example/core', 'task': '.tw/local/parent-task.json', 'report': '.tw/local/parent-report.json'}

    def complete(self, fixture, portable_run=False, prefix='', knowledge_complete=True):
        root, profile, task = fixture.root, fixture.profile, fixture.task
        design = {'data_version': 1, 'kind': 'design', 'id': task['design_id'], 'revision': 1,
            'task_id': task.get('parent') or task['id'], 'assessment': {'complexity': 'medium', 'risks': list(task['risks']),
                'effort': 'one hour', 'drivers': ['arithmetic behavior'], 'uncertainties': [], 'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Scope', 'body': task['goal'], 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Result', 'body': task['acceptance'][0]['expectation'],
                 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Work', 'body': 'Check public behavior',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []}, 'depends_on': []}]}
        plans.plan(design)
        def save(name, value):
            write(root / '.tw/local' / (prefix + name + '.json'), value)
            return '.tw/local/' + prefix + name + '.json'
        fixtures.write_config(root, profile)
        from common import git
        git(root, 'add', '.tw/config.json')
        if git(root, 'diff', '--cached', '--name-only'):
            git(root, 'commit', '-qm', 'update participant configuration')
            for participant in self.manifest['participants']:
                if self.roots[participant['repository']] == root:
                    participant['commit'] = git(root, 'rev-parse', 'HEAD').decode().strip()
        save('task', task)
        brief = save('brief', knowledge.brief(root, task, [], []))
        run, _ = validation.run_batch(root, profile, [task], portable=portable_run)
        approval = designs.approval_draft(design, 'carol', 'Confirmed scope and testable acceptance')
        report = {'data_version': 1, 'task_id': task['id'], 'design': save('design', design),
            'approvals': [save('approval', approval)], 'brief': brief, 'runs': [run.relative_to(root).as_posix()],
            'review': '.tw/local/' + prefix + 'review.json'}
        review = delivery.review_template(root, profile, task, report)
        ref = artifact(root, run)
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read actual public behavior and executed results', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Observed the declared arithmetic result', 'evidence': [ref], 'observations': [plans.observation(ref)]}]
        save('review', review)
        accepted = delivery.verify(root, profile, task, report, 'acceptance')
        acceptance = save('acceptance', accepted)
        if not knowledge_complete:
            save('report', report)
            return
        report['acceptance'] = acceptance
        report['knowledge'] = {'files': [], 'reason': 'Existing requirement remains sufficient'}
        save('report', report)
        if fixture is self.fixtures['core'] and hasattr(self, 'parent_fixture'):
            self.complete(self.parent_fixture, prefix='parent-', knowledge_complete=False)

    def api(self, endpoint, **kwargs):
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Unexpected aggregate provider call: ' + endpoint)

    def aggregate(self, manifest=None):
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.api)):
            return portable.aggregate(self.root, manifest or self.manifest, self.roots)

    def test_joint_execution_covers_both_deliveries_and_build_dependency(self):
        result = self.aggregate()
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])
        self.assertEqual(set(result['versions']), {'github.com/example/core', 'github.com/example/gateway', 'github.com/example/common'})
        self.assertEqual(len(result['participants']), 2)
        self.assertEqual(set(result['tested_versions'][0]['repositories']), set(result['versions']))

    def test_complete_children_do_not_replace_parent_business_acceptance(self):
        missing = copy.deepcopy(self.manifest)
        missing.pop('requirement')
        with self.assertRaisesRegex(Invalid, 'requirement'):
            self.aggregate(missing)
        path = self.root / '.tw/local/parent-review.json'
        review = read(path)
        review['acceptance'][0]['observations'] = []
        write(path, review)
        with self.assertRaisesRegex(Invalid, 'actual execution'):
            self.aggregate()

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
        fixtures.write_config(core.root, core.profile)
        core.git('add', '.tw/config.json')
        core.git('commit', '-qm', 'declare modified dependency')
        self.manifest['participants'][0]['commit'] = core.git('rev-parse', 'HEAD').strip()
        with self.assertRaisesRegex(Invalid, 'no verified participant delivery'):
            self.aggregate()

    def test_dirty_dependency_and_unaccepted_participant_cannot_deliver(self):
        common = self.fixtures['common']
        (common.root / 'app.py').write_text('def add(a,b): return 0\n')
        with self.assertRaisesRegex(Invalid, 'unshared changes'):
            self.aggregate()
        common.git('restore', 'app.py')
        gateway = self.fixtures['gateway']
        review_path = gateway.root / '.tw/local/review.json'
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
        del self.roots['github.com/example/common']
        with self.assertRaisesRegex(Invalid, 'checkout mapping'):
            self.aggregate()

    def test_joint_reuse_reports_original_commits_after_metadata_only_changes(self):
        common = self.fixtures['common']
        tested = common.task['base']
        common.git('commit', '--allow-empty', '-qm', 'new commit without source changes')
        current = common.git('rev-parse', 'HEAD').strip()
        self.manifest['dependencies'][0]['commit'] = current
        result = self.aggregate()
        self.assertEqual(result['versions']['github.com/example/common'], current)
        self.assertEqual(result['tested_versions'][0]['repositories']['github.com/example/common'], tested)


class PortableHelpers(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

    def test_moving_workspace_preserves_portable_source_identity(self):
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        before = portable.source_state(self.root, self.profile)
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            destination = Path(temp) / 'different-directory'
            shutil.copytree(self.root, destination)
            self.assertEqual(before, portable.source_state(destination, self.profile))

    def test_archive_cannot_write_outside_import_directory(self):
        for name in ('../escaped', '/absolute', 'a/../../escaped'):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr(name, 'bad')
            with self.assertRaises(Invalid):
                portable.unpack(output.getvalue(), self.root / '.tw/local/imports/test')


if __name__ == '__main__':
    unittest.main()
