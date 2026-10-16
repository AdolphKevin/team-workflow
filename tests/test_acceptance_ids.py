"""Written tasks contain IDs; every entry expands against the selected design."""
import copy
import unittest
from unittest.mock import patch

import test_four_command_delivery as four
import test_coordination as shared
from common import Invalid, read, write
import coordination
import issue_draft
import records
import plan_fixtures as plans
from platform_fixtures import transport
from tw_runtime.team import platform_script


def written(task):
    return {**copy.deepcopy(task), 'acceptance': [{'id': row['id']} for row in task['acceptance']]}


class LocalAcceptanceIDs(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, command = base.setUp, base.git, base.check, base.configure, base.command

    def test_direct_local_drafts_expand_ids_before_validation(self):
        self.configure('medium')
        write(self.root / '.tw/local/task.json', written(self.task))
        for name, extra in [('design-draft', []), ('approval-draft', ['--reviewer', 'carol'])]:
            with self.subTest(command=name):
                code, result = self.command(name, '--task', '.tw/local/task.json',
                    '--design', '.tw/local/design.md', *extra)
                self.assertEqual(code, 0, result)
        code, result = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / result['task']['path'])['acceptance'],
                         [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': ['unit']}])

    def test_written_local_rows_reject_expectation_and_checks(self):
        self.configure('medium')
        for extra in [{'expectation': '1 + 2 is 3'}, {'checks': ['unit']}]:
            task = written(self.task)
            task['acceptance'][0].update(extra)
            write(self.root / '.tw/local/task.json', task)
            code, result = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
            self.assertEqual(code, 1, result)
            self.assertIn('验收项只写编号，内容以方案为准', result['problem'])

    def test_explicit_run_expands_each_written_task_before_check_selection(self):
        self.configure('medium')
        self.profile['required_checks']['code'] = []
        import test_workflow as fixtures
        fixtures.write_config(self.root, self.profile)
        write(self.root / '.tw/local/task.json', written(self.task))
        child = {**written(self.task), 'id': 'TASK-second', 'acceptance_scope': 'task', 'parent': self.task['id']}
        write(self.root / '.tw/local/second.json', child)
        code, result = self.command('run', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                                    '--with-task', '.tw/local/second.json')
        self.assertEqual(code, 0, result)
        self.assertEqual([row['id'] for row in result['checks']], ['unit'])


class PlatformAcceptanceIDs(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def test_platform_ids_expand_from_parent_and_design_text_keeps_requirements(self):
        self.prepare()
        self.task = written(self.task)
        self.issue['body'] = plans.task_body(self.task)
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            before = coordination.load(self.url)
            self.assertEqual(before['task']['acceptance'],
                             [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': ['unit']}])
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][1]['body'] = 'The result is three'
            self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
            after = coordination.load(self.url)
            self.assertEqual(after['requirements'], before['requirements'])
            self.assertEqual(coordination.requirements_signature(after['source']),
                             coordination.requirements_signature(before['source']))
            self.assertEqual(after['task']['acceptance'][0]['expectation'], 'The result is three')
            child_url = 'https://github.com/example/project/issues/2'
            child = {**written(self.task), 'id': child_url, 'parent': self.url, 'acceptance_scope': 'task'}
            state = coordination.load(child_url, issue={'html_url': child_url,
                'body': plans.task_body(child, self.url), 'comments_data': [], 'assignees': []})
            self.assertEqual(state['task']['acceptance'], after['task']['acceptance'])

    def test_issue_draft_visible_titles_and_hidden_ids(self):
        self.prepare()
        self.task = written(self.task)
        self.design['sections'][1]['title'] = 'The addition result'
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            result = issue_draft.draft(self.root, self.profile, self.task, self.design,
                                      design_path=plans.design_source(self.root, self.design))
        body = result['issues'][0]['body']
        self.assertIn('- A1 The addition result', body)
        self.assertEqual(coordination.task_source({'html_url': self.url, 'body': body})['task']['acceptance'], [{'id': 'A1'}])
        self.assertIn('- A1\n', issue_draft.body({}, self.task, None))
        for extra in [{'expectation': 'old text'}, {'checks': ['unit']}]:
            bad = written(self.task)
            bad['acceptance'][0].update(extra)
            with self.assertRaisesRegex(Invalid, '验收项只写编号，内容以方案为准'):
                coordination.task_source({'html_url': self.url, 'body': records.comment(
                    {'data_version': 1, 'parent': None, 'task': bad})})

    def test_new_acceptance_ids_can_publish_the_selected_revision(self):
        self.prepare()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            self.task['acceptance'] = [{'id': 'A2'}]
            self.issue['body'] = plans.task_body(self.task)
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][1]['id'] = 'A2'
            revised['sections'][0]['data']['requirement_acceptance'] = ['A2']
            revised['sections'][0]['data']['impact'][0]['acceptance'] = ['A2']
            revised['sections'][-1]['data']['acceptance'] = ['A2']
            draft = plans.draft_design(self.root, self.url, revised)
            self.publish_fixture(draft, 'alice')
            self.assertEqual(coordination.load(self.url)['task']['acceptance'][0]['id'], 'A2')
