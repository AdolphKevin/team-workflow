"""Project script contract exercised through a real child process, without network access."""
import json
import copy
import base64
import contextlib
import hashlib
import io
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from datetime import timedelta
import zipfile

import test_workflow as fixtures
from common import Invalid, read, write
from tw_runtime.project import config_problems
from tw_runtime.team import platform_script as platform_read

FIXTURE = Path(__file__).with_name('platform_fixture.py')


class PlatformContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / '.tw').mkdir()
        (self.root / '.tw/.gitignore').write_text('local/\n')
        self.config = {'format': 'channelwill/team-workflow', 'data_version': 1,
                       'project': {'id': 'code.example/group/project', 'name': 'fixture'},
                       'platform': {'argv': [sys.executable, str(FIXTURE)],
                                    'operations': ['task', 'commit', 'reference', 'ci-result']}}
        write(self.root / '.tw/config.json', self.config)
        self.log = self.root / 'calls.jsonl'
        self.responses = {'reference': {'reachable': True, 'kind': 'task'}}
        self.environment = patch.dict(os.environ, {'TW_PLATFORM_LOG': str(self.log),
            'TW_PLATFORM_RESPONSES': json.dumps(self.responses)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        platform_read.clear_cache()

    def test_configuration_and_single_process_call_cache(self):
        self.assertEqual(config_problems(self.config), [])
        arguments = ('--url', 'https://code.example/group/project/issues/12')
        self.assertEqual(platform_read.call(self.root, 'reference', *arguments), self.responses['reference'])
        self.assertEqual(platform_read.call(self.root, 'reference', *arguments), self.responses['reference'])
        self.assertEqual([json.loads(row) for row in self.log.read_text().splitlines()], [
            {'operation': 'reference', 'arguments': list(arguments), 'cwd': str(self.root)}])

    def response(self, operation, value):
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps({operation: value})
        platform_read.clear_cache()

    def task_response(self):
        identity = 'https://code.example/group/sub/project/issues/12'
        return {'id': identity, 'url': identity, 'repository': 'code.example/group/sub/project', 'state': 'open', 'owners': ['alice'],
                'items': [{'url': identity, 'author': 'alice', 'created_at': '2026-10-15T01:00:00Z',
                           'updated_at': '2026-10-15T01:00:00Z', 'body': '原文\r\n', 'kind': 'task'}],
                'raw': {'original': ['未经核查', {'secret': 'fixture-only'}]}}

    def test_task_contract_and_raw_archive(self):
        value = self.task_response()
        self.response('task', value)
        self.assertEqual(platform_read.task(self.root, value['id']), value)
        from artifacts import directory
        saved = list((directory(self.root, value['id']).parent.parent / 'platform').glob('task-*.json'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(read(saved[0]), value['raw'])

    def test_rejects_task_fields_identity_time_and_item_order(self):
        original = self.task_response()
        cases = []
        for key in original:
            value = copy.deepcopy(original)
            del value[key]
            cases.append(value)
        for key in original['items'][0]:
            value = copy.deepcopy(original)
            del value['items'][0][key]
            cases.append(value)
        for change in ({'id': original['id'] + '/redirect'}, {'state': 'unknown'}, {'owners': 'alice'},
                       {'items': []}):
            cases.append({**original, **change})
        for change in ({'created_at': '2026-10-15'}, {'updated_at': '2026-10-15T00:00:00'},
                       {'body': None}, {'kind': 'issue'}):
            value = copy.deepcopy(original)
            value['items'][0].update(change)
            cases.append(value)
        comment = {**original['items'][0], 'kind': 'comment', 'url': original['url'] + '#b'}
        cases += [{**original, 'items': [comment, original['items'][0]]},
                  {**original, 'items': original['items'] * 2},
                  {**original, 'items': [original['items'][0], comment, {**comment, 'url': original['url'] + '#a'}]}]
        for value in cases:
            with self.subTest(value=value):
                self.response('task', value)
                with self.assertRaises(Invalid):
                    platform_read.call(self.root, 'task', '--id', original['id'])

    def test_commit_and_reference_contracts(self):
        revision = 'a' * 40
        commit = {'exists': True, 'revision': revision, 'author': 'Fixture <test@example.invalid>',
                  'time': '2026-10-15T01:00:00Z'}
        self.response('commit', commit)
        self.assertEqual(platform_read.commit(self.root, 'code.example/group/project', revision), commit)
        for key in commit:
            bad = dict(commit)
            del bad[key]
            self.response('commit', bad)
            with self.subTest(key=key), self.assertRaises(Invalid):
                platform_read.call(self.root, 'commit', '--repo', 'code.example/group/project', '--revision', revision)
        for change in ({'revision': 'b' * 40}, {'revision': 'abc'}, {'exists': 1}, {'time': '2026-10-15'}):
            self.response('commit', {**commit, **change})
            with self.subTest(change=change), self.assertRaises(Invalid):
                platform_read.call(self.root, 'commit', '--repo', 'code.example/group/project', '--revision', revision)
        for kind in ('commit', 'file', 'task', 'change', 'comment'):
            reference = {'reachable': True, 'kind': kind, 'revision': 'b' * 64}
            self.response('reference', reference)
            self.assertEqual(platform_read.reference(self.root, 'https://code.example/link'), reference)
        for value in ({'kind': 'file'}, {'reachable': True}, {'reachable': 1, 'kind': 'task'},
                      {'reachable': True, 'kind': 'other'}, {'reachable': True, 'kind': 'file', 'revision': 'abc'}):
            self.response('reference', value)
            with self.subTest(value=value), self.assertRaises(Invalid):
                platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')

    def test_transport_errors_and_configuration(self):
        for stdout in ('[]', '{} {}', 'log\n{}', '{"x":NaN}'):
            with self.subTest(stdout=stdout), patch.dict(os.environ, {'TW_PLATFORM_STDOUT': stdout}):
                platform_read.clear_cache()
                with self.assertRaises(Invalid):
                    platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')
        with patch.dict(os.environ, {'TW_PLATFORM_EXIT': '2', 'TW_PLATFORM_STDERR': 'first reason\ncredential diagnostic'}):
            platform_read.clear_cache()
            with self.assertRaises(Invalid) as failure:
                platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')
            self.assertIn('first reason', str(failure.exception))
            self.assertNotIn('credential diagnostic', str(failure.exception))
        self.config['platform']['operations'] = ['task']
        write(self.root / '.tw/config.json', self.config)
        with self.assertRaisesRegex(Invalid, 'reference.*platform.operations'):
            platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')
        for change in ({'argv': []}, {'argv': ['']}, {'argv': [7]}, {'timeout': True}, {'timeout': 0},
                       {'operations': ['reference']}, {'operations': ['task', 'write']}):
            with self.subTest(change=change):
                self.assertTrue(config_problems({**self.config, 'platform': {**self.config['platform'], **change}}))

    def test_script_timeout(self):
        self.config['platform']['timeout'] = 1
        write(self.root / '.tw/config.json', self.config)
        with patch.dict(os.environ, {'TW_PLATFORM_DELAY': '2'}), self.assertRaisesRegex(Invalid, '超时'):
            platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')

    def test_coordination_uses_ordered_platform_bodies_and_owners(self):
        import coordination
        value = self.task_response()
        task = {'data_version': 1, 'id': value['id']}
        value['items'][0]['body'] = '```team-workflow-task\n' + json.dumps(
            {'data_version': 1, 'parent': None, 'task': task}) + '\n```\n'
        self.response('task', value)
        result = coordination.load(value['id'], root=self.root)
        self.assertEqual(result['task'], task)
        self.assertEqual(result['owners'], ['alice'])

    def test_platform_identity_and_host_independent_repository(self):
        import portable
        from artifacts import task_directory
        self.assertTrue(platform_read.is_task(self.root, 'http://code.example/group/project/-/issues/12'))
        self.assertFalse(platform_read.is_task(self.root, 'TASK-12'))
        subprocess.run(['git', '-C', str(self.root), 'remote', 'add', 'origin',
                        'ssh://git@code.example:2222/group/sub/project.git'], check=True)
        self.assertEqual(portable.repository_id(self.root), 'code.example/group/sub/project')
        self.assertEqual(task_directory('https://code.example/group/sub/project/issues/12').rsplit('-', 1)[0],
                         'group-sub-project-issues-12')
        # Existing issue directories keep their complete old readable prefix and hash.
        self.assertEqual(task_directory('https://github.com/owner/repo/issues/12'), 'owner-repo-12-7e664a0f')
        del self.config['platform']
        write(self.root / '.tw/config.json', self.config)
        with self.assertRaisesRegex(Invalid, '初始化时生成平台脚本'):
            platform_read.is_task(self.root, 'https://code.example/group/project/issues/12')

    def ci_response(self):
        return {'provenance': {'repository': 'code.example/group/sub/project', 'revision': 'a' * 40,
            'run': {'id': 'run-17', 'attempt': 2, 'latest_attempt': 2, 'succeeded': True,
                    'url': 'https://code.example/builds/run-17'},
            'job': {'id': 'job-21', 'name': 'test (3.13)', 'run_id': 'run-17', 'attempt': 2,
                    'started_at': '2026-10-15T01:00:00Z', 'finished_at': '2026-10-15T01:02:00Z', 'succeeded': True},
            'artifact': {'id': 'artifact-22', 'run_id': 'run-17', 'revision': 'a' * 40,
                         'digest': 'sha256:' + hashlib.sha256(b'archive bytes').hexdigest(),
                         'created_at': '2026-10-15T01:01:00Z', 'expired': False}}, 'archive': 'result.zip'}

    def ci_call(self, value):
        self.response('ci-result', value)
        output = self.root / 'downloads' / str(len(list(self.root.glob('downloads/*'))))
        output.mkdir(parents=True)
        os.environ['TW_PLATFORM_ARCHIVE'] = base64.b64encode(b'archive bytes').decode()
        return platform_read.ci_result(self.root, {'opaque': ['input', 17]}, output)

    def test_ci_result_contract_and_opaque_locator(self):
        value = self.ci_response()
        self.assertEqual(self.ci_call(value), value)
        invocation = json.loads(self.log.read_text().splitlines()[-1])
        self.assertEqual(json.loads(invocation['arguments'][1]), {'opaque': ['input', 17]})
        for section in ('run', 'job', 'artifact'):
            for key in value['provenance'][section]:
                bad = copy.deepcopy(value)
                del bad['provenance'][section][key]
                with self.subTest(section=section, key=key), self.assertRaises(Invalid):
                    self.ci_call(bad)
        for key in ('repository', 'revision'):
            bad = copy.deepcopy(value)
            del bad['provenance'][key]
            with self.subTest(key=key), self.assertRaises(Invalid):
                self.ci_call(bad)

    def test_ci_archive_cannot_escape_output_or_disagree_with_digest(self):
        value = self.ci_response()
        for archive in ('../outside.zip', '/tmp/outside.zip', 'missing.zip'):
            with self.subTest(archive=archive), self.assertRaises(Invalid):
                self.ci_call({**value, 'archive': archive})
        bad = copy.deepcopy(value)
        bad['provenance']['artifact']['digest'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(Invalid, 'provider digest'):
            self.ci_call(bad)

    def test_consistency_command_reports_all_operations_without_platform_bodies(self):
        import workflow
        subprocess.run(['git', '-C', str(self.root), 'remote', 'add', 'origin',
                        'https://code.example/group/sub/project.git'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.tw'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'known local commit'], check=True)
        revision, author, timestamp = subprocess.check_output(['git', '-C', str(self.root), 'show', '-s',
            '--format=%H%n%an <%ae>%n%aI', 'HEAD'], text=True).splitlines()
        task = self.task_response()
        ci = self.ci_response()
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps({'task': task,
            'commit': {'exists': True, 'revision': revision, 'author': author, 'time': timestamp},
            'reference': {'reachable': True, 'kind': 'task'}, 'ci-result': ci})
        os.environ['TW_PLATFORM_ARCHIVE'] = base64.b64encode(b'archive bytes').decode()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = workflow.main(['platform', '--root', str(self.root), '--check', '--id', task['id'],
                                    '--commit', revision, '--reference', task['url'], '--locator', '{"opaque":17}'])
        result = json.loads(stream.getvalue())
        self.assertEqual(status, 0, result)
        self.assertEqual([row['operation'] for row in result['checks']], ['task', 'commit', 'reference', 'ci-result'])
        self.assertTrue(all(row['ok'] and row['seconds'] >= 0 for row in result['checks']))
        self.assertNotIn(task['items'][0]['body'], stream.getvalue())
        self.assertNotIn('fixture-only', stream.getvalue())
        responses = json.loads(os.environ['TW_PLATFORM_RESPONSES'])
        responses['commit']['author'] = 'Another author'
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps(responses)
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            status = workflow.main(['platform', '--root', str(self.root), '--check', '--id', task['id'],
                                    '--commit', revision, '--locator', '{"opaque":17}'])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(stream.getvalue())['checks'][1]['ok'])

    def test_contract_document_and_release_budget(self):
        import importlib.util
        repository = Path(__file__).resolve().parents[1]
        path = repository / 'skills/team-workflow/references/platform.md'
        self.assertTrue(path.is_file())
        body = path.read_text()
        self.assertLessEqual(len(body), 3000)
        for term in ('state', 'owners', 'updated_at', 'ci-result', 'provenance', 'raw', 'TW_RUN_CONTEXT'):
            self.assertIn(term, body)
        spec = importlib.util.spec_from_file_location('platform_release_check', repository / 'scripts/check_release.py')
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        self.assertEqual(release.TEAM_BUDGETS['references/platform.md'], 3000)

    def test_registered_platform_script_is_not_a_knowledge_entry(self):
        from tw_runtime.project import Project
        self.config['platform']['argv'] = [sys.executable, '.tw/platform.py']
        write(self.root / '.tw/config.json', self.config)
        (self.root / '.tw/platform.py').write_text('print("fixture")\n')
        project = Project(self.root)
        project.entries()
        self.assertNotIn('.tw/platform.py', project.strays)

    def test_failed_calls_and_ci_downloads_are_cached(self):
        with patch.dict(os.environ, {'TW_PLATFORM_EXIT': '2', 'TW_PLATFORM_STDERR': 'failed\nprivate diagnostic'}):
            for _ in range(2):
                with self.assertRaises(Invalid):
                    platform_read.call(self.root, 'reference', '--url', 'https://code.example/link')
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.log.unlink()
        value = self.ci_response()
        self.response('ci-result', value)
        output = self.root / 'download'
        output.mkdir()
        os.environ['TW_PLATFORM_ARCHIVE'] = base64.b64encode(b'archive bytes').decode()
        for _ in range(2):
            self.assertEqual(platform_read.ci_result(self.root, {'opaque': 17}, output), value)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)

    def test_missing_platform_on_url_task_reports_a_normal_cli_failure(self):
        import workflow
        del self.config['platform']
        write(self.root / '.tw/config.json', self.config)
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            status = workflow.main(['start', '--root', str(self.root), '--task', self.task_response()['id']])
        self.assertEqual(status, 1)
        result = json.loads(stream.getvalue())
        self.assertIn('初始化时生成平台脚本', result['problem'])
        self.assertNotEqual(result['error_code'], 'tool-defect')

    def test_runtime_has_no_bundled_platform_reader(self):
        repository = Path(__file__).resolve().parents[1]
        runtime = repository / 'skills/team-knowledge/scripts/tw_runtime/team'
        self.assertFalse((runtime / 'github_read.py').exists())
        self.assertFalse((runtime / 'platform.py').exists())
        self.assertTrue((runtime / 'platform_script.py').is_file())

    def test_equal_instants_in_different_timezones_do_not_invent_history_edits(self):
        import coordination
        from test_coordination import CoordinationCases
        from platform_fixtures import task_data, transport
        fixture = CoordinationCases()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        with patch.object(platform_read, 'call', side_effect=transport(fixture.github)):
            fixture.publish_fixture(coordination.draft_design(fixture.url, fixture.design), 'alice')
        value = task_data(fixture.issue)
        value['items'][1].update(created_at='2026-10-15T08:01:00Z', updated_at='2026-10-15T10:01:00+02:00')
        self.response('task', value)
        result = coordination.load(value['id'], root=self.root)
        self.assertEqual(result['gaps'], [])
        value['items'][1]['updated_at'] = '2026-10-15T10:02:00+02:00'
        self.response('task', value)
        self.assertTrue(any('edited platform record' in gap for gap in coordination.load(value['id'], root=self.root)['gaps']))

    def test_ipv6_remote_identity_is_accepted_without_renormalizing_it(self):
        import portable
        subprocess.run(['git', '-C', str(self.root), 'remote', 'add', 'origin',
                        'ssh://git@[2001:db8::1]:2222/group/sub/project.git'], check=True)
        self.assertEqual(portable.repository_id(self.root), '2001:db8::1/group/sub/project')
        self.response('commit', {'exists': True, 'revision': 'a' * 40, 'author': 'Fixture <test@example.invalid>',
                                 'time': '2026-10-15T01:00:00Z'})
        platform_read.commit(self.root, portable.repository_id(self.root), 'a' * 40)
        self.assertEqual(json.loads(self.log.read_text())['arguments'][1], '2001:db8::1/group/sub/project')


class PlatformImportContract(unittest.TestCase):
    """Real command capture and two script downloads at the user-facing import entry."""
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def setUp(self):
        fixtures.WorkflowCases.setUp(self)
        self.git('remote', 'add', 'origin', 'ssh://git@code.example:2222/group/sub/project.git')
        self.profile['platform'] = {'argv': [sys.executable, str(FIXTURE)],
                                    'operations': ['task', 'commit', 'ci-result']}
        self.check('import app; assert app.add(1,2)==3; print("actual command passed")')
        fixtures.write_config(self.root, self.profile)
        self.git('add', '.tw/config.json')
        self.git('commit', '-qm', 'register platform fixture and command')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        write(self.root / '.tw/local/task.json', self.task)
        self.tw = FIXTURE.parents[1] / 'skills/team-knowledge/scripts/tw.py'
        self.environment = patch.dict(os.environ, {'TW_RUN_CONTEXT': json.dumps({
            'repository': 'code.example/group/sub/project', 'run_id': 'R17', 'attempt': '2', 'job': 'tests'}),
            'TW_PLATFORM_LOG': str(self.root / '.tw/local/calls.jsonl')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        captured = self.command('run', '--task', '.tw/local/task.json', '--portable')
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        record = read(self.root / json.loads(captured.stdout)['artifact']['path'])
        manifest_path = self.root / record['results'][0]['portable']['path']
        self.manifest = read(manifest_path)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as stream:
            for path in manifest_path.parent.rglob('*'):
                if path.is_file():
                    stream.write(path, path.relative_to(manifest_path.parent).as_posix())
        self.archive = archive.getvalue()
        started = platform_read.timestamp(self.manifest['started_at']) - timedelta(minutes=1)
        finished = platform_read.timestamp(self.manifest['finished_at']) + timedelta(minutes=1)
        self.locator = {'opaque': {'selected': ['run-17', 2], 'interpreted_by_tool': False}}
        write(self.root / '.tw/local/locator.json', self.locator)
        self.receipt = {'repository': 'code.example/group/sub/project', 'revision': self.task['base'],
            'run': {'id': 'R17', 'attempt': 2, 'latest_attempt': 2, 'succeeded': True, 'url': 'https://code.example/runs/17'},
            'job': {'id': 'J21', 'name': 'tests (3.13)', 'run_id': 'R17', 'attempt': 2,
                    'started_at': started.isoformat(), 'finished_at': finished.isoformat(), 'succeeded': True},
            'artifact': {'id': 'A22', 'run_id': 'R17', 'revision': self.task['base'], 'expired': False,
                         'created_at': self.manifest['finished_at'],
                         'digest': 'sha256:' + hashlib.sha256(self.archive).hexdigest()}}
        _, author, timestamp = self.git('show', '-s', '--format=%H%n%an <%ae>%n%aI', 'HEAD').splitlines()
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps({'ci-result': {'provenance': self.receipt, 'archive': 'result.zip'},
            'commit': {'exists': True, 'revision': self.task['base'], 'author': author, 'time': timestamp}})
        os.environ['TW_PLATFORM_ARCHIVE'] = base64.b64encode(self.archive).decode()

    def command(self, *arguments):
        return subprocess.run([sys.executable, str(self.tw), 'team', *arguments, '--root', str(self.root)],
                              capture_output=True, text=True, timeout=30)

    def imported(self):
        return self.command('import-result', '--result', '.tw/local/locator.json')

    def test_real_entry_keeps_locator_and_downloads_twice(self):
        result = self.imported()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = read(self.root / json.loads(result.stdout)['artifact']['path'])
        self.assertEqual(record['locator'], self.locator)
        self.assertEqual(record['provenance'], self.receipt)
        self.assertEqual(record['tested_source'], self.manifest['source_before'])
        calls = [json.loads(line) for line in (self.root / '.tw/local/calls.jsonl').read_text().splitlines()]
        downloads = [row for row in calls if row['operation'] == 'ci-result']
        self.assertEqual(len(downloads), 2)
        self.assertNotEqual(downloads[0]['arguments'][-1], downloads[1]['arguments'][-1])
        self.assertEqual(json.loads(downloads[0]['arguments'][1]), self.locator)

    def test_real_entry_rejects_changed_provenance_on_second_download(self):
        changed = copy.deepcopy(self.receipt)
        changed['artifact']['id'] = 'A23'
        os.environ['TW_PLATFORM_SEQUENCE'] = json.dumps({'ci-result': [
            {'provenance': self.receipt, 'archive': 'result.zip'}, {'provenance': changed, 'archive': 'result.zip'}]})
        result = self.imported()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('changed during import', json.loads(result.stdout)['problem'])
        self.assertFalse(any((self.root / '.tw/local/tasks').rglob('import.json')))


if __name__ == '__main__':
    unittest.main()
