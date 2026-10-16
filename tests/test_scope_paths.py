"""Regression for task prefixes, directory briefs and shared path normalization."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import test_four_command_delivery as four
import test_start_accept as start
import test_workflow as workflow_fixtures
import plan_fixtures as plans
from common import Invalid as TeamInvalid, read, write
import coordination
import designs
from platform_fixtures import transport
from tw_fixtures import Case, commit, entry, write as write_text
from tw_runtime import Invalid, brief, globs
from tw_runtime.project import Project
from tw_runtime.team import platform_script


class RepositoryPaths(Case):
    def test_normalization_and_query_absolute_paths(self):
        from tw_runtime import repo_paths
        cases = {'': '.', '.': '.', './': '.', '././': '.', './a': 'a',
                 'a/./b//': 'a/b', 'a//b.py': 'a/b.py', 'a/': 'a'}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(repo_paths.normalize(value), expected)
                self.assertEqual(brief.relative_paths(self.root, [value]), [expected])
        absolute = str(self.root / 'app.py')
        self.assertEqual(repo_paths.normalize(absolute, root=self.root), 'app.py')
        self.assertEqual(brief.relative_paths(self.root, [absolute]), ['app.py'])
        with self.assertRaises(Invalid):
            repo_paths.normalize(absolute)

    def test_unsafe_paths_rejected_before_collapsing_segments(self):
        for path in ['..', 'a/../b', '/outside.py', 'a\\b', 'a\0b', 'a/[ab].py']:
            with self.subTest(path=path):
                with self.assertRaises(Invalid):
                    brief.relative_paths(self.root, [path])
        from tw_runtime import repo_paths
        for path in ['../app.py', 'a/../app.py', '/app.py', 'a\\b', 'a\0b', '*']:
            with self.subTest(scope=path), self.assertRaises(Invalid):
                repo_paths.normalize(path, scope=True)

    def test_glob_overlap_boundaries(self):
        cases = [
            ('tests/test_*.py', 'tests', True),
            ('tests/test_*.py', 'tests/unit', False),
            ('**/test_?.py', 'tests/unit/deep', True),
            ('**/test_?.py', '.', True),
            ('src/**/api/*.py', 'src', True),
            ('src/**/api/*.py', 'src/x/api', True),
            ('src/**/api/*.py', 'src/x/api/deep', True),
            ('src/**', 'src/a/b', True),
            ('src/**', 'other', False),
            ('src/*/test_?.py', 'src/unit', True),
            ('src/*/test_?.py', 'src/unit/deep', False),
            ('s?c/unit*/test.py', 'src/unit-tests', True),
            ('s?c/unit*/test.py', 'source/unit-tests', False),
            ('s?c/unit*/test.py', 'src', True),
            ('tests/unit/test.py', 'tests', True),
            ('tests', 'tests/unit/deep', True),
            ('tests', 'tests_old', False),
            ('**/src/**/test?.py', 'deep/src/nested', True),
            ('src/*.py', 'src/nested', False),
        ]
        for pattern, directory, expected in cases:
            with self.subTest(pattern=pattern, directory=directory):
                self.assertEqual(globs.overlaps(pattern, directory), expected)


class DirectoryBrief(Case):
    def setUp(self):
        super().setUp()
        self.initialize()
        write_text(self.root, '.tw/rules/test-scope.md', entry(
            '测试隔离约束', '必须隔离。', scope=['self:tests/test_*.py'],
            source=['s'], verified=self.verified(), tags=['测试隔离'], symbols=['Test.run']))
        write_text(self.root, '.tw/rules/guard-only.md', entry(
            '回滚边界', '必须回滚。', scope=['self:app.py'], source=['s'],
            guards=['self:tests/test_orders.py#test_inventory_rollback']))
        self.change = commit(self.root, 'directory query evidence')[:7]

    def query(self, path, *extra, task='x'):
        code, result = self.tw_json('brief', '--task', task, '--path', path, *extra)
        self.assertEqual(code, 0, result)
        return result

    def test_cli_directory_reads_overlapping_scopes_without_guard_noise(self):
        result = self.query('tests')
        self.assertEqual([e['label'] for e in result['entries']], ['rules/test-scope.md'])
        self.assertIn('相关提交', result['markdown'])
        # A direct file remains an exact guard signal.
        result = self.query('tests/test_orders.py')
        self.assertIn('rules/guard-only.md', [e['label'] for e in result['entries']])

    def test_existing_wildcard_query_characters_remain_literal_paths(self):
        for path in ['tests/test_*.py', 'tests/test_?.py']:
            with self.subTest(path=path):
                result = self.query(path)
                self.assertEqual(result['paths'], [path])
                self.assertEqual([e['label'] for e in result['entries']], ['rules/test-scope.md'])

    def test_cli_root_has_no_path_hits_but_keeps_other_signals_and_budget(self):
        result = self.query('.')
        self.assertEqual(result['paths'], ['.'])
        self.assertEqual(result['entries'], [])
        self.assertIn('范围为整个仓库，未按路径筛选', result['markdown'])
        for extra, task in [((), '测试隔离'), (('--tag', '测试隔离'), 'x'),
                            (('--symbol', 'Test.run'), 'x')]:
            with self.subTest(extra=extra, task=task):
                result = self.query('././', *extra, task=task)
                self.assertIn('rules/test-scope.md', [e['label'] for e in result['entries']])
                self.assertFalse(any(reason.startswith('路径 ') for e in result['entries'] for reason in e['reasons']))
        result = self.query('.', '--budget', '1000', task='测试隔离' * 1000)
        self.assertLessEqual(result['chars'], 1000)
        self.assertIn('范围为整个仓库，未按路径筛选', result['markdown'])

    def test_trailing_slash_directory_survives_repeated_normalization(self):
        write_text(self.root, '.tw/rules/future.md', entry(
            '新目录约束', '必须隔离。', scope=['self:future/test_*.py'], source=['s']))
        paths = brief.relative_paths(self.root, ['future/'])
        self.assertEqual(paths, ['future'])
        result = brief.build(Project(self.root), 'x', paths=paths)
        self.assertIn('rules/future.md', [e['label'] for e in result['entries']])
        picks, *_ = brief.select(Project(self.root), 'x', ['future/'], [], [], [])
        self.assertIn('rules/future.md', [p.entry.label for p in picks])

    def test_directory_specificity_is_below_file_at_the_same_depth(self):
        write_text(self.root, '.tw/rules/a-directory.md', entry(
            '目录约束', '隔离。', scope=['self:tests/test_*.py'], source=['s']))
        write_text(self.root, '.tw/rules/z-file.md', entry(
            '文件约束', '隔离。', scope=['self:README.md'], source=['s']))
        result = brief.build(Project(self.root), 'x', paths=['tests', 'README.md'])
        self.assertEqual(result['entries'][0]['label'], 'rules/z-file.md')
        self.assertIn('rules/a-directory.md', [e['label'] for e in result['entries']])

    def test_replay_accepts_root_directory_and_absolute_queries(self):
        spec = importlib.util.spec_from_file_location('scope_replay', Path(__file__).parents[1] / 'scripts/replay_brief.py')
        replay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(replay)
        result = replay.replay(self.root, [
            {'id': 'root', 'task': 'x', 'paths': ['.'], 'expected': []},
            {'id': 'directory', 'task': 'x', 'paths': [str(self.root / 'tests')], 'expected': ['rules/test-scope.md']},
        ])
        self.assertEqual(result['recall_visible'], 1.0)
        self.assertEqual(result['rows'][0]['extra'], [])


class LocalScopeStart(unittest.TestCase):
    setUp, git, check, configure, command = (four.FourCommandDelivery.setUp,
        four.FourCommandDelivery.git, four.FourCommandDelivery.check,
        four.FourCommandDelivery.configure, four.FourCommandDelivery.command)

    def prepare_scope(self, scope, paths=()):
        self.configure()
        self.task['paths'] = list(paths)
        self.design['sections'][-1]['data']['scope'] = [scope]
        (self.root / 'src').mkdir(exist_ok=True)
        (self.root / 'tests').mkdir(exist_ok=True)
        write_text(self.root, '.tw/rules/tests.md', entry(
            '测试约束', '必须隔离。', scope=['self:tests/test_*.py'], source=['s']))
        write(self.root / '.tw/local/task.json', plans.written_task(self.task))
        plans.write_design(self.root / '.tw/local/design.md', self.design)

    def assert_start_and_continuation(self, scope):
        self.prepare_scope(scope, ['app.py'] if scope == './app.py' else [])
        code, first = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, first)
        self.assertFalse(first['continued'])
        code, again = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, again)
        self.assertTrue(again['continued'])
        for result in [first, again]:
            knowledge = read(self.root / result['brief']['path'])
            if scope == 'tests':
                self.assertIn('rules/tests.md', [e['label'] for e in knowledge['entries']])
            if scope == '.':
                self.assertIn('范围为整个仓库，未按路径筛选', knowledge['markdown'])
                self.assertFalse(any(e['tier'] == 1 for e in knowledge['entries']))

    def test_equivalent_task_paths_and_scope_share_prefix_semantics(self):
        self.prepare_scope('app.py', ['./app.py'])
        coordination.validate_task_design(self.task, self.design)
        self.design['sections'][-1]['data']['scope'] = ['./a//b/']
        coverage = designs.scope_coverage(self.design, ['a/b/./c.py'])
        self.assertEqual(coverage['mapped'], {'a/b/c.py': ['T1']})
        self.assertTrue(coverage['complete'])
        self.assertEqual(self.design['sections'][-1]['data']['scope'], ['./a//b/'])

    def test_outside_and_unsafe_task_paths_are_rejected(self):
        self.prepare_scope('app.py')
        for path in ['../app.py', str(self.root / 'app.py'), 'app.py/../other.py',
                     'app.py\\x', 'app.py\0', 'other.py', 'app.py_old']:
            with self.subTest(path=path):
                self.task['paths'] = [path]
                with self.assertRaises(Invalid):
                    coordination.validate_task_design(self.task, self.design)

    def test_request_identity_keeps_explicit_directory_intent(self):
        self.prepare_scope('.')
        write_text(self.root, '.tw/rules/future.md', entry(
            '新目录约束', '隔离。', scope=['self:future/test_*.py'], source=['s']))
        args = ('brief', '--task', '.tw/local/task.json', '--request-id', 'directory-hint')
        code, first = self.command(*args, '--path', 'future')
        self.assertEqual(code, 0, first)
        code, changed = self.command(*args, '--path', 'future/')
        self.assertEqual(code, 1, changed)
        self.assertIn('request', changed['problem'].lower())

    def test_invalid_task_path_keeps_the_team_error_contract(self):
        self.prepare_scope('app.py', ['app.py/../other.py'])
        with self.assertRaises(TeamInvalid):
            coordination.validate_task_design(self.task, self.design)

    def test_committed_task_paths_do_not_gain_query_absolute_path_permission(self):
        self.prepare_scope('.', [str(self.root / 'app.py')])
        code, result = self.command('brief', '--task', '.tw/local/task.json')
        self.assertEqual(code, 1, result)
        self.assertIn('相对路径', result['problem'])


class PlatformScopeStart(unittest.TestCase):
    base = start.StartPlatform
    setUp, git, check, prepare, body, github, publish_fixture, establish_design, handoff, command = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github,
        base.publish_fixture, base.establish_design, base.handoff, base.command)

    def assert_start_and_continuation(self, scope):
        self.prepare('simple')
        self.task['paths'] = ['app.py'] if scope == './app.py' else []
        self.design['sections'][-1]['data']['scope'] = [scope]
        (self.root / 'src').mkdir(exist_ok=True)
        write_text(self.root, 'tests/test_scope.py', 'def test_scope(): pass\n')
        write_text(self.root, '.tw/rules/tests.md', entry(
            '测试约束', '必须隔离。', scope=['self:tests/test_*.py'], source=['s']))
        workflow_fixtures.write_config(self.root, self.profile)
        self.git('add', '.')
        self.git('commit', '-qm', 'share scope fixtures')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        self.issue['body'] = self.body()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            self.establish_design(approved=False)
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), kind='design'), 'alice')
            code, first = self.command()
            self.assertEqual(code, 0, first)
            self.assertFalse(first['continued'])
            code, again = self.command()
            self.assertEqual(code, 0, again)
            self.assertTrue(again['continued'])
            resumed = coordination.resume(self.root, self.profile, self.url)
            self.assertTrue(resumed['ok'], resumed['gaps'])
        for result in [first, again]:
            knowledge = read(self.root / result['brief']['path'])
            if scope == 'tests':
                self.assertIn('rules/tests.md', [e['label'] for e in knowledge['entries']])
            if scope == '.':
                self.assertIn('范围为整个仓库，未按路径筛选', knowledge['markdown'])


def scope_case(scope):
    def test(self):
        self.assert_start_and_continuation(scope)
    return test


for group in [LocalScopeStart, PlatformScopeStart]:
    for name, scope in [('root', '.'), ('dot_file', './app.py'), ('slash_directory', 'src/'),
                        ('directory', 'tests'), ('repeated_slash', 'a//b.py')]:
        setattr(group, 'test_' + name + '_start_and_continuation', scope_case(scope))
del group


if __name__ == '__main__':
    unittest.main()
