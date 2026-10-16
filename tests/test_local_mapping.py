"""A1/A2: shared checkout defaults through real CLI calls and Git worktrees."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from tw_fixtures import Case, SCRIPTS, commit, entry, git, make_repo, tree_state, write
from tw_runtime.project import Project

sys.path.insert(0, str(SCRIPTS / "tw_runtime/team"))
from common import Invalid, LOCATIONS, external_path, location_settings


class LocalMapping(Case):
    def setUp(self):
        super().setUp()
        self.xdg = self.base / 'config-home'
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.xdg)})
        environment.start()
        self.addCleanup(environment.stop)
        self.initialize()
        self.config = json.loads((self.root / '.tw/config.json').read_text())
        self.project_id = self.config['project']['id']
        self.user_file = self.xdg / 'tw/repositories.json'

    def configure(self, **values):
        self.config.update(values)
        write(self.root, '.tw/config.json', json.dumps(self.config))

    def user_mapping(self, values):
        write(self.xdg, 'tw/repositories.json', json.dumps({'projects': {self.project_id: values}}))

    def command(self, root, *args):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'tw.py'), '--root', str(root), *args],
                                text=True, capture_output=True,
                                env={**os.environ, 'TEAM_WORKFLOW_ALLOW_MODIFIED_TOOL': '1'})
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_a1_worktrees_resolve_defaults_and_keep_task_materials_separate(self):
        shared = {}
        for name in ('X', 'Y'):
            target = make_repo(self.base, name, 'https://github.com/acme/common.git')
            write(target, 'README.md', '# Common\n')
            commit(target)
            self.initialize(root=target)
            write(target, '.tw/rules/selected.md', entry(
                f'共享仓 {name}', f'本规则来自检出目录 {name}。', scope=['self:README.md'], source=['s']))
            commit(target)
            shared[name] = target
        self.configure(shared={'common': {'id': 'github.com/acme/common'}},
                       checks={'unit': {'argv': [sys.executable, '-c', 'from pathlib import Path; assert Path("README.md").is_file()'],
                                        'cwd': '.', 'timeout': 5, 'purpose': 'README exists', 'format': 'command',
                                        'required_cases': [], 'required_env': [], 'environment': {'kind': 'stateless'}}},
                       required_checks={'code': [], 'docs': []}, risk_checks={},
                       inputs=[], external_inputs={}, environment_versions={}, accounts=[])
        commit(self.root, 'shared configuration')
        worktrees = [self.base / name for name in ('A', 'B')]
        for checkout in worktrees:
            git(self.root, 'worktree', 'add', '-q', '-b', checkout.name, str(checkout))
        a, b = worktrees
        self.user_mapping({'repositories': {'common': str(shared['X'])}})
        local = write(a, '.tw/local/repositories.json', json.dumps({'repositories': {'common': str(shared['Y'])}}))
        mapping_bytes = self.user_file.read_bytes(), local.read_bytes()
        for checkout, expected, other in ((a, 'Y', 'X'), (b, 'X', 'Y')):
            code, brief = self.command(checkout, 'brief', '--task', '共享仓',
                                       '--entry', 'common:rules/selected.md', '--format', 'json')
            self.assertEqual(code, 0, brief)
            self.assertIn(f'共享仓 {expected}', brief['markdown'])
            self.assertNotIn(f'共享仓 {other}', brief['markdown'])
            self.assertIn(str(shared[expected]), brief['repositories']['common']['description'])
        task = {'data_version': 1, 'id': 'TASK-worktree-A', 'base': git(a, 'rev-parse', 'HEAD'),
                'goal': '说明共享仓', 'non_goals': [], 'kind': 'docs', 'risks': [],
                'acceptance': [{'id': 'A1'}],
                'design_id': 'D-worktrees', 'section_ids': ['T1'], 'acceptance_scope': 'requirement',
                'paths': ['README.md']}
        from plan_fixtures import plan
        design = plan({'data_version': 1, 'kind': 'design', 'id': 'D-worktrees', 'revision': 1,
                       'task_id': task['id'], 'assessment': {'complexity': 'simple', 'risks': [],
                       'effort': 'one hour', 'drivers': ['documentation'], 'uncertainties': [], 'required_skills': []},
                       'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
                       'sections': [
                           {'id': 'scope-global', 'type': 'global-scope', 'title': '说明', 'body': task['goal'],
                            'data': {}, 'depends_on': []},
                           {'id': 'A1', 'type': 'acceptance', 'title': '说明', 'body': '说明共享仓',
                            'data': {'checks': ['unit']}, 'depends_on': []},
                           {'id': 'T1', 'type': 'task', 'title': '说明', 'body': '说明共享仓',
                            'data': {'acceptance': ['A1'], 'scope': ['README.md'], 'blocked_by': []}, 'depends_on': []}]})
        from plan_fixtures import write_design
        for checkout in worktrees:
            write(checkout, '.tw/local/imports/task.json', json.dumps(task))
            write_design(checkout / '.tw/local/imports/design.md', design)
        inputs = ('--task', '.tw/local/imports/task.json', '--design', '.tw/local/imports/design.md')
        code, started = self.command(a, 'team', 'start', *inputs)
        self.assertEqual(code, 0, started)
        self.assertTrue(started['implementation_ready'])
        saved_brief = json.loads((a / started['brief']['path']).read_text())
        self.assertIn(str(shared['Y']), saved_brief['brief']['repositories']['common']['description'])
        self.assertTrue((a / started['context']['path']).is_file())
        code, status = self.command(b, 'team', 'status', *inputs)
        self.assertEqual(code, 0, status)
        self.assertEqual(status['next_step']['id'], 'prepare')
        self.assertNotIn(started['context']['path'], json.dumps(status))
        self.assertFalse((b / started['context']['path']).exists())
        self.assertEqual((self.user_file.read_bytes(), local.read_bytes()), mapping_bytes)
        self.assertFalse((b / '.tw/local/repositories.json').exists())

    def test_a2_missing_mapping_names_both_locations(self):
        self.configure(shared={'common': {'id': 'github.com/acme/common'}})
        code, brief = self.command(self.root, 'brief', '--task', '共享仓', '--format', 'json')
        self.assertEqual(code, 0, brief)
        description = brief['repositories']['common']['description']
        self.assertIn('.tw/local/repositories.json', description)
        self.assertIn(str(self.user_file), description)
        before = tree_state(self.root)
        with self.assertRaises(Invalid) as caught:
            external_path(self.root, 'common', {'kind': 'repository', 'repository': 'github.com/acme/common'})
        self.assertIn('.tw/local/repositories.json', str(caught.exception))
        self.assertIn(str(self.user_file), str(caught.exception))
        self.assertEqual(tree_state(self.root), before)
        self.assertFalse(self.user_file.exists())

    def test_a2_layers_merge_each_key_and_keep_repository_and_input_meanings(self):
        identity = 'github.com/acme/common'
        user = {'repositories': {'common': '../user-common', identity: '../user-identity',
                                 'user-only': '../user-only'},
                'inputs': {'settings': '../user-settings', 'user-only': '../user-input'}}
        self.user_mapping(user)
        local = {'repositories': {'common': '../local-common', identity: '../local-identity',
                                  'local-only': '../local-only'},
                 'inputs': {'settings': '../local-settings', 'local-only': '../local-input'}}
        write(self.root, '.tw/local/repositories.json', json.dumps(local))
        before = tree_state(self.root), tree_state(self.xdg)
        resolved = Project(self.root, ['common=' + str(self.base / 'cli-common')]).mapping()
        self.assertEqual(resolved, {'common': self.base / 'cli-common', identity: self.base / 'local-identity',
                                   'user-only': self.base / 'user-only', 'local-only': self.base / 'local-only'})
        cli = {'repositories': {identity: '../cli-identity'}, 'inputs': {'settings': '../cli-settings'}}
        token = LOCATIONS.set(cli)
        try:
            self.assertEqual(location_settings(self.root), {
                'repositories': {'common': '../local-common', identity: '../cli-identity',
                                 'user-only': '../user-only', 'local-only': '../local-only'},
                'inputs': {'settings': '../cli-settings', 'user-only': '../user-input', 'local-only': '../local-input'}})
        finally:
            LOCATIONS.reset(token)
        self.assertEqual((tree_state(self.root), tree_state(self.xdg)), before)
        (self.root / '.tw/local/repositories.json').unlink()
        self.assertEqual(Project(self.root).mapping()['common'], self.base / 'user-common')

    def test_a2_user_mapping_is_scoped_to_project_id_and_expands_home(self):
        write(self.xdg, 'tw/repositories.json', json.dumps({'projects': {
            'local:another': {'repositories': {'other': '/unused'}},
            self.project_id: {'repositories': {'common': '~/src/common'}}}}))
        self.assertEqual(Project(self.root).mapping(), {'common': Path('~/src/common').expanduser().resolve()})

    def test_a2_bad_user_mapping_reports_its_path_without_writing(self):
        cases = ['{', '[]', '{}', '{"projects": []}',
                 json.dumps({'projects': {self.project_id: []}}),
                 json.dumps({'projects': {self.project_id: {'repositories': []}}}),
                 json.dumps({'projects': {self.project_id: {'repositories': {'common': ''}}}})]
        for raw in cases:
            with self.subTest(raw=raw):
                write(self.xdg, 'tw/repositories.json', raw)
                before = tree_state(self.root), tree_state(self.xdg)
                code, _, err = self.tw('brief', '--task', '共享仓')
                self.assertEqual(code, 2, err)
                self.assertIn(str(self.user_file), err)
                with self.assertRaisesRegex(Invalid, 'repositories.json'):
                    location_settings(self.root)
                self.assertEqual((tree_state(self.root), tree_state(self.xdg)), before)
