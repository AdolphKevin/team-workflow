"""Unified runtime contracts through project files, real Git and the public command entry."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_delivery
import test_workflow as fixtures
from common import Invalid, LOCATIONS, artifact, load_profile, read, snapshot, write
from tw_fixtures import entry
from tw_runtime import cli, install
from tw_runtime.project import Project
import artifacts
import delivery
import knowledge
import validation
import workflow

TW = fixtures.SCRIPTS.parents[1] / 'tw.py'


class UnifiedTeam(unittest.TestCase):
    base = test_delivery.DeliveryCases
    setUp, git, check, setup_task, write, name = (base.setUp, base.git, base.check,
                                               base.setup_task, base.write, base.name)

    def rule(self, name='addition', title='加法规则'):
        path = self.root / f'.tw/rules/{name}.md'
        path.parent.mkdir(exist_ok=True)
        path.write_text(entry(title, '公开加法入口必须返回正确结果。', scope=['self:app.py'],
                              source=['self:AGENTS.md'], verified={'self': {
                                  'commit': self.git('rev-parse', 'HEAD').strip(), 'date': '2026-10-14'}}))
        return path

    def command(self, *args):
        value = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', *args],
                               capture_output=True, text=True)
        return value.returncode, json.loads(value.stdout)

    def test_start_reads_tw_brief_and_records_files_and_markdown(self):
        self.setup_task()
        path = self.rule()
        code, result = self.command('start', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, result)
        brief = read(self.root / result['brief']['path'])
        self.assertEqual(brief['kind'], 'knowledge-brief')
        self.assertIn('加法规则', brief['markdown'])
        self.assertEqual(brief['entries'][0]['label'], 'rules/addition.md')
        self.assertEqual(brief['files']['.tw/rules/addition.md'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result['request_directory'].split('/')[3], artifacts.task_directory(self.task['id']))
        self.assertNotIn('receipt', brief)

    def test_delivery_template_fills_changed_files_or_a_required_reason(self):
        self.setup_task()
        args = ('delivery-template', '--task', self.name('task'), '--design', self.name('design'),
                '--brief', self.name('brief'), '--review', self.name('review'))
        code, result = self.command(*args)
        self.assertEqual(code, 0, result)
        report = read(self.root / result['artifact']['path'])
        self.assertEqual(report['knowledge'], {'files': [], 'reason': '__REPLACE__'})
        self.rule()
        code, result = self.command(*args)
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / result['artifact']['path'])['knowledge']['files'], ['.tw/rules/addition.md'])

    def test_cli_final_delivery_cites_the_acceptance_written_by_accept(self):
        self.setup_task()
        home = ('--home', str(self.root / '.tw/local/empty-home'))
        code, accepted = self.command('accept', '--task', self.name('task'), '--report', self.name('report'),
                                      '--out', self.name('acceptance'), *home)
        self.assertEqual(code, 0, accepted)
        args = ('delivery-template', '--task', self.name('task'), '--design', self.name('design'),
                '--brief', self.name('brief'), '--review', self.name('review'), '--approval', self.name('approval'),
                '--run', self.runs[0])
        code, drafted = self.command(*args)
        self.assertEqual(code, 0, drafted)
        report = read(self.root / drafted['artifact']['path'])
        self.assertEqual(report.pop('acceptance'), self.name('acceptance'))
        report['knowledge'] = {'files': [], 'reason': '现有规则已覆盖本任务'}
        self.write('final', report)
        code, refused = self.command('verify', '--task', self.name('task'), '--report', self.name('final'), *home)
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['error_code'], 'acceptance-record-missing')
        self.assertIn('tw team accept', refused['next_action'])
        code, drafted = self.command(*args, '--acceptance', self.name('acceptance'))
        self.assertEqual(code, 0, drafted)
        report = read(self.root / drafted['artifact']['path'])
        self.assertEqual(report['acceptance'], self.name('acceptance'))
        report['knowledge'] = {'files': [], 'reason': '现有规则已覆盖本任务'}
        self.write('final', report)
        code, delivered = self.command('verify', '--task', self.name('task'), '--report', self.name('final'), *home)
        self.assertEqual(code, 0, delivered)
        record = read(self.root / delivered['artifact']['path'])
        self.assertTrue(record['delivery_complete'])
        self.assertIn(artifact(self.root, self.root / self.name('acceptance')), record['materials'])

    def test_start_continuation_saves_brief_and_retries_without_overwriting_it(self):
        self.setup_task()
        self.rule()
        code, prepared = self.command('start', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, prepared)
        args = ('start', '--task', self.name('task'), '--request-id', 'continue')
        code, result = self.command(*args)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['continued'])
        path = self.root / result['brief']['path']
        before = path.read_bytes()
        self.assertIn('加法规则', read(path)['markdown'])
        again_code, again = self.command(*args)
        self.assertEqual((again_code, again), (code, result))
        self.assertEqual(path.read_bytes(), before)

    def accept(self):
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.write('acceptance', accepted)
        self.report['acceptance'] = self.name('acceptance')
        self.write('report', self.report)

    def test_delivery_requires_disposition_and_a_clean_knowledge_check(self):
        self.setup_task()
        self.accept()
        for value, message in ((None, '知识处置.*二选一'), ({'files': []}, '知识处置.*二选一'),
                               ({'files': [], 'reason': '__REPLACE__'}, '知识处置.*二选一'),
                               ({'files': ['app.py']}, '知识正文'),
                               ({'files': ['.tw/rules/missing.md']}, '不是本任务删除的条目'),
                               ({'files': ['.tw/config.json']}, '知识正文')):
            report = {**self.report, 'knowledge': value}
            with self.subTest(value=value), self.assertRaisesRegex(Invalid, message):
                delivery.verify(self.root, self.profile, self.task, report)
        report = {**self.report, 'knowledge': {'files': [], 'reason': '现有规则已覆盖本任务'}}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, report)['delivery_complete'])
        path = self.rule()
        with self.assertRaisesRegex(Invalid, '没有列入 knowledge.files：.tw/rules/addition.md'):
            delivery.verify(self.root, self.profile, self.task, report)  # changed knowledge needs listing
        listed = {**self.report, 'knowledge': {'files': ['.tw/rules/addition.md']}}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, listed)['delivery_complete'])
        path.write_text('# 没有文件头的规则\n')
        with self.assertRaisesRegex(Invalid, 'tw check 有错误'):
            delivery.verify(self.root, self.profile, self.task, listed)

    def test_local_ignore_rules_are_not_knowledge(self):
        self.setup_task()
        self.accept()
        ignore = self.root / '.tw/.gitignore'
        ignore.write_text(ignore.read_text() + '# local evidence stays out of Git\n')
        self.assertNotIn('.tw/.gitignore', knowledge.changed_since(self.root, self.task['base']))
        with self.assertRaisesRegex(Invalid, '知识正文'):
            delivery.verify(self.root, self.profile, self.task, {**self.report, 'knowledge': {'files': ['.tw/.gitignore']}})
        report = {**self.report, 'knowledge': {'files': [], 'reason': '只调整了本地忽略规则'}}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, report)['delivery_complete'])

    def test_request_identity_covers_acceptance_and_knowledge_content(self):
        self.setup_task()
        home = ('--home', str(self.root / '.tw/local/empty-home'))
        code, accepted = self.command('accept', '--task', self.name('task'), '--report', self.name('report'),
                                      '--out', self.name('acceptance'), *home)
        self.assertEqual(code, 0, accepted)
        args = ('delivery-template', '--task', self.name('task'), '--design', self.name('design'),
                '--brief', self.name('brief'), '--review', self.name('review'), '--request-id', 'template')
        code, first = self.command(*args)
        self.assertEqual(code, 0, first)
        self.write('acceptance-copy', read(self.root / self.name('acceptance')))
        for extra in (('--acceptance', self.name('acceptance-copy')), ()):
            if not extra:
                self.rule()  # same arguments, different knowledge content
            with self.subTest(extra=extra):
                code, again = self.command(*args, *extra)
                self.assertEqual(code, 1, again)
                self.assertIn('Request ID already belongs to different inputs', again['problem'])

    def test_listed_knowledge_must_be_changed_by_this_task(self):
        self.rule()
        self.git('add', '.tw/rules/addition.md')
        self.git('commit', '-qm', 'knowledge from an earlier task')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.setup_task()
        self.accept()
        report = {**self.report, 'knowledge': {'files': ['.tw/rules/addition.md']}}
        with self.assertRaisesRegex(Invalid, '没有改动.*rules/addition.md'):
            delivery.verify(self.root, self.profile, self.task, report)

    def test_a_knowledge_entry_deleted_by_the_task_counts_as_its_disposition(self):
        path = self.rule()
        self.git('add', '.tw/rules/addition.md')
        self.git('commit', '-qm', 'establish knowledge')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.setup_task()
        self.accept()
        path.unlink()
        report = {**self.report, 'knowledge': {'files': ['.tw/rules/addition.md'], 'reason': '规则已撤销'}}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, report)['delivery_complete'])

    def test_knowledge_only_commit_preserves_execution_review_and_final_delivery(self):
        path = self.rule()
        self.git('add', '.tw/rules/addition.md')
        self.git('commit', '-qm', 'establish knowledge')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.setup_task()
        before = validation.source_digest(self.root, self.profile)
        path.write_text(path.read_text() + '\n说明改写，计算要求保持相同。\n')
        self.git('add', '.tw/rules/addition.md')
        self.git('commit', '-qm', 'knowledge only')
        self.assertEqual(validation.source_digest(self.root, self.profile), before)
        self.assertEqual(validation.changed_paths(self.root, self.task, self.profile), [])
        self.accept()
        self.report['knowledge'] = {'files': ['.tw/rules/addition.md']}
        self.write('report', self.report)
        code, result = self.command('verify', '--task', self.name('task'), '--report', self.name('report'),
                                    '--home', str(self.root / '.tw/local/empty-home'))
        self.assertEqual(code, 0, result)
        record = read(self.root / result['artifact']['path'])
        self.assertTrue(record['delivery_complete'])
        self.assertEqual(record['report']['runs'], self.runs)
        self.assertEqual(record['knowledge']['files'], ['.tw/rules/addition.md'])

    def test_explicit_knowledge_inputs_change_snapshot_binding_and_design_scope(self):
        path = self.rule()
        for inputs in ([], ['.tw/rules'], ['.tw/rules/addition.md']):
            self.profile['inputs'] = inputs
            before = validation.source_digest(self.root, self.profile)
            path.write_text(path.read_text() + '\n增补适用条件。\n')
            after = validation.source_digest(self.root, self.profile)
            with self.subTest(inputs=inputs):
                self.assertEqual(before == after, not inputs)
                self.assertEqual('.tw/rules/addition.md' in validation.changed_paths(self.root, self.task, self.profile), bool(inputs))

    def test_config_in_snapshot_and_bound_only_when_explicitly_declared(self):
        self.assertIn('.tw/config.json', snapshot(self.root, self.profile)['files'])
        before = validation.source_digest(self.root, self.profile)
        value = read(self.root / '.tw/config.json')
        value['documents'] = [{'id': 'sop', 'title': 'SOP', 'source': 'self:AGENTS.md'}]
        write(self.root / '.tw/config.json', value)
        self.assertEqual(validation.source_digest(self.root, self.profile), before)
        self.profile['inputs'] = ['.tw/config.json']
        before = validation.source_digest(self.root, self.profile)
        value['documents'][0]['title'] = '业务 SOP'
        write(self.root / '.tw/config.json', value)
        self.assertNotEqual(validation.source_digest(self.root, self.profile), before)

    def test_tracked_local_evidence_fails_before_new_material_is_written(self):
        self.write('task', self.task)
        self.git('add', '-f', self.name('task'))
        with self.assertRaisesRegex(Invalid, r'\.tw/local/.*Git'):
            snapshot(self.root, self.profile)
        code, result = self.command('task-export', '--task', self.name('task'))
        self.assertEqual(code, 1)
        self.assertIn('.tw/local/', result['problem'])
        self.assertFalse((self.root / '.tw/local/tasks').exists())

    def test_local_evidence_cannot_be_an_explicit_input(self):
        self.write('sample', {'captured': True})
        self.profile['inputs'] = [self.name('sample')]
        with self.assertRaisesRegex(Invalid, r'\.tw/local/.*inputs'):
            snapshot(self.root, self.profile)

    def test_local_writes_require_ignore_including_nested_exceptions(self):
        (self.root / '.tw/.gitignore').write_text('')
        with self.assertRaisesRegex(Invalid, '忽略'):
            self.write('sample', {'value': 1})
        self.assertFalse((self.root / self.name('sample')).exists())
        (self.root / '.tw/.gitignore').write_text('local/\n!local/\nlocal/*\n!local/sample.json\n')
        with self.assertRaisesRegex(Invalid, '忽略'):
            self.write('sample', {'value': 1})

    def test_external_inputs_and_accounts_are_optional(self):
        config = read(self.root / '.tw/config.json')
        for key in ('external_inputs', 'accounts'):
            config.pop(key, None)
        write(self.root / '.tw/config.json', config)
        profile = load_profile(self.root)
        self.assertEqual((profile['external_inputs'], profile['accounts']), ({}, []))

    def test_team_config_adapts_project_name_and_rejects_missing_or_old_fields(self):
        self.assertEqual(load_profile(self.root)['project'], 'sample')
        config = read(self.root / '.tw/config.json')
        for missing in ('checks', 'required_checks', 'risk_checks'):
            value = {k: v for k, v in config.items() if k != missing}
            write(self.root / '.tw/config.json', value)
            with self.subTest(missing=missing), self.assertRaisesRegex(Invalid, missing):
                load_profile(self.root)
        for changes, label in (({'data_version': 2}, 'data_version'),
                                ({'data_version': True}, 'data_version'),
                                ({'workflow_version': '99.0.0'}, 'workflow_version'),
                                ({'knowledge': {'provider': 'cs'}}, 'knowledge')):
            write(self.root / '.tw/config.json', {**config, **changes})
            with self.subTest(changes=changes), self.assertRaisesRegex(Invalid, label):
                load_profile(self.root)

    def test_project_checks_external_repository_identities_against_local_checkouts(self):
        # Real case: core's migrated config named external repositories as owner/repo, while
        # identities are host/path since the platform-neutral change. project reported ok and
        # start failed later with "Local checkout identity differs".
        import tempfile
        dependency = Path(tempfile.mkdtemp()) / 'common'
        dependency.mkdir()
        subprocess.run(['git', '-C', str(dependency), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(dependency), 'remote', 'add', 'origin',
                        'https://github.com/example/common.git'], check=True)
        config = json.loads((self.root / '.tw/config.json').read_text())
        home = str(self.root / '.tw/local/empty-home')
        for identity, mapped, ok in (('example/common', True, False), ('github.com/example/common', True, True),
                                     ('github.com/example/common', False, True)):
            with self.subTest(identity=identity, mapped=mapped):
                config['external_inputs'] = {'common': {'kind': 'repository', 'repository': identity, 'role': 'build'}}
                write(self.root / '.tw/config.json', config)
                write(self.root / '.tw/local/repositories.json',
                      {'repositories': {identity: str(dependency)} if mapped else {}})
                code, result = self.command('project', '--home', home)
                self.assertEqual(code == 0, ok, result)
                if not ok:
                    problem = ' '.join(result['config']['errors'])
                    self.assertIn('example/common', problem)
                    self.assertIn('github.com/example/common', problem)
                if not mapped:
                    self.assertIn('common', ' '.join(result['warnings']))

    def test_project_reports_config_check_errors_and_shared_installation(self):
        (self.root / '.tw/overview.md').write_text('# 缺少文件头\n')
        code, result = self.command('project', '--home', str(self.root / '.tw/local/empty-home'))
        self.assertEqual(code, 1)
        self.assertTrue(result['config']['ok'])
        self.assertGreater(result['knowledge']['errors'], 0)
        self.assertTrue(result['installation']['ok'], result['installation'])
        self.assertNotIn('cs', result)

    def test_original_documents_are_read_from_configuration(self):
        config = read(self.root / '.tw/config.json')
        config['documents'] = [{'id': 'sop', 'title': '加法原文', 'source': 'self:AGENTS.md'}]
        write(self.root / '.tw/config.json', config)
        doc = knowledge.documents(self.root)['documents'][0]
        self.assertEqual(doc['status'], 'current')
        self.assertEqual(doc['sha256'], artifact(self.root, self.root / 'AGENTS.md')['sha256'])

    def test_identity_and_alias_mappings_share_one_repository_object(self):
        (self.root / 'shared').mkdir()
        subprocess.run(['git', '-C', str(self.root / 'shared'), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(self.root / 'shared'), 'remote', 'add', 'origin', 'git@github.com:acme/common.git'], check=True)
        config = read(self.root / '.tw/config.json')
        config['shared'] = {'common': {'id': 'github.com/acme/common'}}
        write(self.root / '.tw/config.json', config)
        write(self.root / '.tw/local/repositories.json', {'repositories': {'acme/common': 'shared'}, 'inputs': {}})
        self.assertEqual(Project(self.root).shared()['common'].root, self.root / 'shared')
        token = LOCATIONS.set({'repositories': {'acme/common': 'shared'}, 'inputs': {}})
        try:
            self.assertEqual(knowledge.project(self.root).shared()['common'].root, self.root / 'shared')
        finally:
            LOCATIONS.reset(token)


class TaskDirectories(unittest.TestCase):
    def test_readable_stable_issue_and_other_identifiers(self):
        url = 'https://github.com/acme/orders/issues/149'
        self.assertEqual(artifacts.task_directory(url), 'acme-orders-149-' + hashlib.sha256(url.encode()).hexdigest()[:8])
        same_number = ['https://github.com/' + name + '/issues/1' for name in ('foo-bar/baz', 'foo/bar-baz', 'foo/bar.baz')]
        self.assertEqual(len({artifacts.task_directory(value) for value in same_number}), 3)
        self.assertNotEqual(artifacts.task_directory('https://github.com/other/orders/issues/149'),
                            artifacts.task_directory(url))
        for value, slug in (('TASK Readable Title', 'task-readable-title'), ('中文任务', 'task'),
                            ('A' * 100, 'a' * 40), ('../Unsafe / NAME', 'unsafe-name')):
            expected = slug + '-' + hashlib.sha256(value.encode()).hexdigest()[:8]
            with self.subTest(value=value):
                self.assertEqual(artifacts.task_directory(value), expected)
                self.assertEqual(artifacts.task_directory(value), artifacts.task_directory(value))
        self.assertNotEqual(artifacts.task_directory('Task'), artifacts.task_directory('task'))


class TeamRouting(unittest.TestCase):
    def test_root_is_forwarded_once_and_explicit_root_is_preserved(self):
        for options, expected in ((['schema'], ['schema', '--root', '/global']),
                                 (['schema', '--root', '/explicit'], ['schema', '--root', '/explicit']),
                                 (['schema', '--root=/explicit'], ['schema', '--root=/explicit'])):
            with self.subTest(options=options), patch.object(workflow, 'main', return_value=0) as routed:
                self.assertEqual(cli.main(['--root', '/global', 'team', *options]), 0)
                routed.assert_called_once_with(expected)

    def test_team_help_and_schema_use_the_sibling_skill(self):
        help_result = subprocess.run([sys.executable, str(TW), 'team', '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('start', help_result.stdout)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['team', 'schema']), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(Path(result['templates']['config']).parent.parent, install.SKILL.parent / 'team-workflow')
        self.assertEqual(result['data_version'], 1)
        self.assertNotIn('profile', result['templates'])

    def test_removed_commands_and_bridge_options_are_rejected(self):
        for arguments in (['knowledge'], ['knowledge-template'], ['adopt'],
                          *[['schema', name, 'old'] for name in ('--cs-skill', '--cs-task-id', '--disposition',
                                                               '--knowledge', '--final-brief', '--profile')]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli.main(['team', *arguments])


if __name__ == '__main__':
    unittest.main()
