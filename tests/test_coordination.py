"""Version 4 team coordination at the GitHub and CS process boundaries."""
import copy
import json
import subprocess
import unittest
from unittest.mock import patch

import test_workflow as fixtures
import plan_fixtures as plans
from common import Invalid, write
import coordination
import github_read


class CoordinationCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs

    def prepare(self, complexity='medium'):
        self.url = 'https://github.com/example/project/issues/1'
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.check('import app; assert app.add(1, 2) == 3')
        self.task.update(id=self.url, design_id='addition')
        self.design = {
            'schema_version': 5, 'kind': 'design', 'id': 'addition', 'revision': 1, 'task_id': self.url,
            'assessment': {'complexity': complexity, 'risks': [], 'effort': 'one day',
                           'drivers': ['One arithmetic operation'], 'uncertainties': [],
                           'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Addition',
                 'body': 'Addition works', 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Addition result',
                 'body': '1 + 2 is 3', 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Implement addition', 'body': 'Change add',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []},
                 'depends_on': []}]}
        plans.plan(self.design)
        self.issue = {'html_url': self.url, 'state': 'open', 'updated_at': '2026-10-12T01:00:00Z',
                      'body': self.body(), 'assignees': [{'login': 'bob'}], 'comments_data': []}
        self.skill = self.fake_cs()
        self.gets = []

    def body(self):
        return 'Add two inputs.\n\n```team-workflow-task\n' + json.dumps(
            {'schema_version': 5, 'parent': None, 'task': self.task}) + '\n```\n'

    def github(self, endpoint, paginate=False, binary=False):
        self.gets.append(endpoint)
        if endpoint == 'repos/example/project/issues/1':
            return copy.deepcopy(self.issue)
        if endpoint.startswith('repos/example/project/issues/1/comments'):
            return copy.deepcopy(self.issue['comments_data'])
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Fixture cannot resolve ' + endpoint)

    def publish_fixture(self, draft, author, number=None):
        """Represent an independently published GitHub comment in the API fixture."""
        number = number or len(self.issue['comments_data']) + 1
        self.issue['comments_data'].append({
            'html_url': self.url + '#issuecomment-' + str(number),
            'body': draft['markdown'], 'user': {'login': author}})

    def establish_design(self, approved=True):
        plans.plan(self.design)
        draft = coordination.draft_design(self.url, self.design)
        self.publish_fixture(draft, 'alice')
        if approved:
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol',
                'confirmation': 'Reviewed addition scope and acceptance; approved.'})
            self.publish_fixture(approval, 'carol')

    def handoff(self, **changes):
        return {'creator': 'alice', 'owner': 'bob', 'done': ['Design and acceptance ready'],
                'verified': [], 'remaining': ['Implement addition'], 'questions': [],
                'next': 'Implement the approved addition requirement.', **changes}

    def test_reads_named_approval_without_publishing_or_claiming_delivery(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            draft = coordination.draft_design(self.url, self.design)
            self.assertEqual(self.issue['comments_data'], [])
            self.publish_fixture(draft, 'alice')
            missing = coordination.load(self.url)
            self.assertEqual(missing['approvals'], [])
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol',
                'confirmation': 'I approve all current design sections.'})
            self.publish_fixture(approval, 'carol')
            current = coordination.load(self.url)
        self.assertEqual(current['design'], self.design)
        self.assertEqual(current['roles']['implementation_owner'], 'bob')
        self.assertEqual(current['approvals'][0]['reviewer'], 'carol')
        self.assertEqual(current['delivery'], 'not-evaluated')
        self.assertEqual(current['gaps'], [])

    def test_designer_hands_approved_work_to_another_implementer(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.assertTrue(draft['ok'], draft)
            self.assertEqual(draft['record']['creator'], 'alice')
            self.assertEqual(draft['record']['owner'], 'bob')
            self.assertEqual(draft['record']['roles'], self.design['roles'])
            self.assertIn('T1', draft['record']['approved_sections'])
            self.publish_fixture(draft, 'alice')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertTrue(resumed['ok'], resumed)
        self.assertTrue(resumed['ready_to_implement'])
        self.assertEqual(resumed['current']['remaining'], ['Implement addition'])
        self.assertEqual(resumed['knowledge']['paths'], ['app.py'])
        self.assertEqual(resumed['delivery'], 'not-evaluated')
        self.assertFalse(resumed['closable'])

    def test_medium_task_needs_approval_but_simple_task_can_start(self):
        for complexity, expected in [('medium', False), ('simple', True)]:
            with self.subTest(complexity=complexity):
                self.prepare(complexity)
                with patch.object(github_read, 'api', side_effect=self.github):
                    self.establish_design(approved=False)
                    result = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
                    self.assertEqual(result['ok'], expected, result)
                    self.publish_fixture(result, 'alice')
                    resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
                self.assertEqual(resumed['ready_to_implement'], expected, resumed)
                self.assertEqual(resumed['delivery'], 'not-evaluated')
                self.git('remote', 'remove', 'origin')
                # The Git and CS fixtures belong to the next independent subcase.
                import shutil
                shutil.rmtree(self.root / '.team-workflow')
                shutil.rmtree(self.root / '.codestable')

    def test_record_posted_for_someone_else_keeps_the_named_approver_and_actual_recorder(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            plans.plan(self.design)
            self.publish_fixture(coordination.draft_design(self.url, self.design), 'bob')
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.assertEqual(approval['record']['approval']['confirmation'], '')
            self.publish_fixture(approval, 'bob')
            loaded = coordination.load(self.url)
            self.assertEqual(loaded['gaps'], [])
            self.assertEqual(len(loaded['approvals']), 1)
            self.assertEqual(loaded['approval_records'][0]['reviewer'], 'carol')
            self.assertEqual(loaded['approval_records'][0]['recorded_by'], 'bob')
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.publish_fixture(draft, 'bob')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertNotIn('comment author', str(resumed['gaps']))
        self.assertEqual(resumed['current']['creator'], 'alice')

    def test_approval_still_needs_a_named_reviewer(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            plans.plan(self.design)
            self.publish_fixture(coordination.draft_design(self.url, self.design), 'alice')
            for value in ({}, {'reviewer': ''}, {'reviewer': 'carol', 'confirmation': None}):
                with self.subTest(value=value), self.assertRaises(Invalid):
                    coordination.draft_approval(self.url, value)

    def test_changed_requirements_and_source_never_look_ready(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design'), 'alice')
            self.assertTrue(coordination.resume(self.root, self.profile, self.url, self.skill)['ok'])
            self.issue['body'] += '\nReject negative values too.\n'
            requirements = coordination.resume(self.root, self.profile, self.url, self.skill)
            self.assertFalse(requirements['ready_to_implement'])
            self.assertIn('Requirements changed', str(requirements['gaps']))
            self.issue['body'] = self.body()
            (self.root / 'app.py').write_text('def add(a, b): return 0\n')
            source = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(source['ok'])
        self.assertIn('Source content changed', str(source['gaps']))
        self.assertEqual(source['delivery'], 'not-evaluated')

    def test_parallel_handoffs_need_explicit_reconciliation_and_preserve_history(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            first = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.publish_fixture(first, 'alice')
            self.publish_fixture(first, 'alice')
            conflict = coordination.load(self.url)
            self.assertIn('concurrent', str(conflict['gaps']))
            with self.assertRaisesRegex(Invalid, 'explicit resolution'):
                coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            progress = self.handoff(resolution={'history_digest': conflict['history_digest'],
                'reason': 'Read both comments; same design, retain implementation as remaining.'})
            reconciled = coordination.draft(self.root, self.profile, self.url, progress, self.skill, kind='design')
            self.assertTrue(reconciled['ok'], reconciled)
            self.publish_fixture(reconciled, 'alice')
            self.assertTrue(coordination.resume(self.root, self.profile, self.url, self.skill)['ok'])
            self.assertEqual(len(self.issue['comments_data']), 5)
            self.issue['comments_data'][2]['body'] += '\nEarlier comment was changed.\n'
            altered = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(altered['ok'])
        self.assertIn('history changed', str(altered['gaps']))

    def test_new_progress_cannot_silently_disappear_from_handoff(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design'), 'alice')
            progress = coordination.progress_draft(self.root, self.profile, self.url,
                {'author': 'bob', 'done': ['Checked addition behavior'], 'verified': [],
                 'remaining': ['Need overflow decision'], 'questions': []}, 'bob-check-1')
            self.publish_fixture(progress, 'bob')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
            self.assertEqual(len(resumed['pending_progress']), 1)
            self.assertFalse(resumed['ok'])
            ignored = coordination.draft(self.root, self.profile, self.url,
                self.handoff(creator='bob'), self.skill)
            self.assertFalse(ignored['ok'])
            contribution = resumed['pending_progress'][0]
            confirmed = self.handoff(creator='bob',
                included_progress=[{'id': contribution['id'], 'digest': contribution['digest']}],
                remaining=['Need overflow decision'])
            draft = coordination.draft(self.root, self.profile, self.url, confirmed, self.skill)
            self.assertTrue(draft['ok'], draft)
            self.publish_fixture(draft, 'bob')
            self.assertTrue(coordination.resume(self.root, self.profile, self.url, self.skill)['ok'])
            self.issue['comments_data'][-2]['body'] = progress['markdown'].replace('Need overflow decision', 'Changed earlier progress')
            altered = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(altered['ok'])
        self.assertIn('history changed', str(altered['gaps']))

    def test_reused_progress_identifier_with_different_content_is_a_conflict(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            progress = {'author': 'bob', 'done': ['Read code'], 'verified': [], 'remaining': [], 'questions': []}
            draft = coordination.progress_draft(self.root, self.profile, self.url, progress, 'once')
            self.publish_fixture(draft, 'bob')
            self.publish_fixture(draft, 'bob')
            self.assertEqual(len(coordination.load(self.url)['progress']), 1)
            progress['done'] = ['Changed claim']
            with self.assertRaisesRegex(Invalid, 'different content'):
                coordination.progress_draft(self.root, self.profile, self.url, progress, 'once')

    def dependency(self, role):
        directory = self.root / '.team-workflow/library'
        directory.mkdir(parents=True)
        for argv in [('init', '-q'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'user.name', 'Fixture'), ('config', 'commit.gpgsign', 'false'),
                     ('remote', 'add', 'origin', 'https://github.com/example/library.git')]:
            subprocess.check_call(['git', '-C', str(directory), *argv])
        (directory / 'library.py').write_text('VALUE = 3\n')
        subprocess.check_call(['git', '-C', str(directory), 'add', '.'])
        subprocess.check_call(['git', '-C', str(directory), 'commit', '-qm', 'library'])
        self.profile['external_inputs'] = {'library': {'kind': 'repository', 'repository': 'example/library', 'role': role}}
        write(self.root / '.team-workflow/local.json', {'repositories': {'example/library': str(directory)}})
        return directory

    def test_build_dependency_is_pinned_without_inventing_collaborators(self):
        self.prepare()
        self.dependency('build')
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.assertTrue(draft['ok'], draft)
            self.assertEqual(draft['record']['participants'], [])
            self.assertEqual({row['repository'] for row in draft['record']['versions']}, {'example/project', 'example/library'})
            self.assertEqual(draft['record']['dependencies'][0]['role'], 'build')
            omitted = coordination.draft(self.root, self.profile, self.url, self.handoff(dependencies=[]), self.skill, kind='design')
        self.assertFalse(omitted['ok'])
        self.assertIn('Declared dependency missing', str(omitted['gaps']))

    def test_local_only_files_in_a_build_dependency_are_named_and_excludable(self):
        self.prepare()
        library = self.dependency('build')
        (library / '.DS_Store').write_bytes(b'finder')
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            dirty = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.assertFalse(dirty['ok'])
            self.assertIn('Unshared working changes: example/library: .DS_Store', str(dirty['gaps']))
            self.assertIn('.git/info/exclude', str(dirty['gaps']))
            (library / '.git/info/exclude').write_text('.DS_Store\n')
            clean = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
        self.assertTrue(clean['ok'], clean['gaps'])

    def test_modified_dependency_requires_its_actual_responsibility(self):
        self.prepare()
        self.dependency('modified')
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
        self.assertFalse(draft['ok'])
        self.assertIn('responsibility', str(draft['gaps']))
        self.assertIn('example/library', str(draft['gaps']))

    def test_updated_requirements_can_be_reviewed_before_replacing_old_handoff(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design'), 'alice')
            self.issue['body'] += '\nAddition applies to integer inputs.\n'
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][0]['body'] = 'Addition works for integers'
            self.publish_fixture(coordination.draft_design(self.url, revised), 'alice')
            self.publish_fixture(coordination.draft_approval(self.url,
                {'reviewer': 'carol', 'confirmation': 'Approved integer scope.'}), 'carol')
            refreshed = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.assertTrue(refreshed['ok'], refreshed)
            self.publish_fixture(refreshed, 'alice')
            self.assertTrue(coordination.resume(self.root, self.profile, self.url, self.skill)['ok'])

    def test_parallel_approvals_can_be_reconciled_without_deleting_history(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design(approved=False)
            value = {'reviewer': 'carol', 'confirmation': 'I approve the listed sections.'}
            approval = coordination.draft_approval(self.url, value)
            self.publish_fixture(approval, 'carol')
            self.publish_fixture(approval, 'carol')
            state = coordination.load(self.url)
            value['resolution'] = {'history_digest': state['history_digest'],
                'reason': 'Both approval comments refer to the same reviewed content; confirm it now.'}
            reconciled = coordination.draft_approval(self.url, value)
            self.publish_fixture(reconciled, 'carol')
            current = coordination.load(self.url)
        self.assertEqual(current['gaps'], [])
        self.assertEqual(len(self.issue['comments_data']), 4)

    def test_no_handoff_prevents_resume_but_does_not_prevent_design_review(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.assertEqual(coordination.load(self.url)['gaps'], [])
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(resumed['ok'])
        self.assertIn('No confirmed handoff', str(resumed['gaps']))

    def test_shared_parent_design_can_prepare_a_child_without_copying_history(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
        child_url = 'https://github.com/example/project/issues/2'
        child_task = {**self.task, 'id': child_url, 'parent': self.url, 'acceptance_scope': 'task'}
        child = {'html_url': child_url, 'state': 'open', 'assignees': [{'login': 'bob'}],
                 'body': '```team-workflow-task\n' + json.dumps(
                     {'schema_version': 5, 'parent': self.url, 'task': child_task}) + '\n```\n',
                 'comments_data': []}

        def transport(endpoint, **kwargs):
            if endpoint == 'repos/example/project/issues/2':
                return copy.deepcopy(child)
            if endpoint.startswith('repos/example/project/issues/2/comments'):
                return copy.deepcopy(child['comments_data'])
            return self.github(endpoint, **kwargs)

        with patch.object(github_read, 'api', side_effect=transport):
            state = coordination.load(child_url)
            self.assertEqual(state['design_issue'], self.url)
            self.assertEqual(state['approvals'][0]['reviewer'], 'carol')
            draft = coordination.draft(self.root, self.profile, child_url, self.handoff(), self.skill, kind='design')
            self.assertTrue(draft['ok'], draft)
            child['comments_data'].append({'html_url': child_url + '#issuecomment-8',
                'body': draft['markdown'], 'user': {'login': 'alice'}})
            resumed = coordination.resume(self.root, self.profile, child_url, self.skill)
        self.assertTrue(resumed['ok'], resumed)
        self.assertEqual(resumed['task']['id'], child_url)
        self.assertEqual(resumed['design']['task_id'], self.url)

    def test_assignment_or_progress_change_during_resume_is_visible(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design'), 'alice')
        reads = 0

        def transport(endpoint, **kwargs):
            nonlocal reads
            if endpoint == 'repos/example/project/issues/1':
                reads += 1
                if reads == 2:
                    self.issue['assignees'] = [{'login': 'carol'}]
            return self.github(endpoint, **kwargs)

        with patch.object(github_read, 'api', side_effect=transport):
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(resumed['ok'])
        self.assertIn('Platform changed while reading', str(resumed['gaps']))

    def test_platform_edit_metadata_rejects_a_changed_last_handoff(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.publish_fixture(draft, 'alice')
            self.issue['comments_data'][-1].update(created_at='2026-10-12T01:00:00Z', updated_at='2026-10-12T02:00:00Z')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertFalse(resumed['ok'])
        self.assertIn('edited platform record', str(resumed['gaps']))

    def test_unrelated_section_change_preserves_this_tasks_approved_handoff(self):
        self.prepare()
        self.design['sections'] += [
            {'id': 'A2', 'type': 'acceptance', 'title': 'Another feature', 'body': 'Other behavior',
             'data': {'checks': ['unit']}, 'depends_on': []},
            {'id': 'T2', 'type': 'task', 'title': 'Other implementation', 'body': 'Implement another feature',
             'data': {'acceptance': ['A2'], 'scope': ['other.py'], 'blocked_by': []}, 'depends_on': []}]
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.publish_fixture(draft, 'alice')
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][-1]['body'] = 'Changed independent implementation requirements'
            self.publish_fixture(coordination.draft_design(self.url, revised), 'alice')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill)
        self.assertTrue(resumed['ok'], resumed)
        self.assertEqual(resumed['approval_status']['tasks']['T2']['state'], 'needs-review')
        self.assertEqual(resumed['approval_status']['tasks']['T1']['state'], 'ready')

    def test_changed_acceptance_preserves_other_sections_approval_on_platform(self):
        self.prepare()
        self.design['sections'] += [
            {'id': 'A2', 'type': 'acceptance', 'title': 'Another feature', 'body': 'Other behavior',
             'data': {'checks': ['unit']}, 'depends_on': []},
            {'id': 'T2', 'type': 'task', 'title': 'Other work', 'body': 'Independent feature',
             'data': {'acceptance': ['A2'], 'scope': ['other.py'], 'blocked_by': []}, 'depends_on': []}]
        self.task['section_ids'] = ['T1', 'T2']
        self.task['acceptance'].append({'id': 'A2', 'expectation': 'Other behavior', 'checks': ['unit']})
        self.issue['body'] = self.body()
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            self.task['acceptance'][0]['expectation'] = 'Updated first requirement'
            self.issue['body'] = self.body()
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][1]['body'] = 'Updated first requirement'
            self.publish_fixture(coordination.draft_design(self.url, revised), 'alice')
            state = coordination.load(self.url)
        import designs
        status = designs.approval_status(state['design'], state['approvals'], history=state['history'], changed_paths=[])
        self.assertEqual(status['tasks']['T2']['state'], 'ready')
        self.assertEqual(status['tasks']['T1']['state'], 'needs-review')

    def test_verified_predecessor_can_be_carried_through_handoff_and_resume(self):
        self.prepare()
        predecessor = copy.deepcopy(self.design['sections'][-1])
        predecessor['id'] = 'T0'
        self.design['sections'].append(predecessor)
        self.design['sections'][2]['data']['blocked_by'] = ['T0']
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            missing = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill, kind='design')
            self.assertFalse(missing['ok'])
            draft = coordination.draft(self.root, self.profile, self.url, self.handoff(), self.skill,
                                       kind='design', completed_tasks=['T0'])
            self.assertTrue(draft['ok'], draft)
            self.publish_fixture(draft, 'alice')
            resumed = coordination.resume(self.root, self.profile, self.url, self.skill, completed_tasks=['T0'])
        self.assertTrue(resumed['ready_to_implement'], resumed)


    def test_completed_implementation_handoff_reads_original_verification_records(self):
        self.prepare()
        import validation
        from common import artifact
        run, _ = validation.run_batch(self.root, self.profile, [self.task])
        finished = {'creator': 'bob', 'owner': 'carol', 'done': ['Implemented addition'], 'remaining': [],
                    'questions': [], 'next': 'Carol accepts the addition result.'}
        self.issue['assignees'].append({'login': 'carol'})
        with patch.object(github_read, 'api', side_effect=self.github):
            self.establish_design()
            cases = [([artifact(self.root, run)], None),
                     ([artifact(self.root, self.root / 'app.py')], 'Handoff needs original execution/acceptance records'),
                     ([], 'Completed handoff needs original verification records')]
            for verified, gap in cases:
                with self.subTest(gap=gap):
                    draft = coordination.draft(self.root, self.profile, self.url, dict(finished, verified=verified),
                                               self.skill, kind='implementation')
                    if gap is None:
                        self.assertTrue(draft['ok'], draft)
                    else:
                        self.assertFalse(draft['ok'])
                        self.assertTrue(any(gap in item for item in draft['gaps']), draft['gaps'])


class ReadClient(unittest.TestCase):
    def test_read_client_rejects_other_hosts_and_prs(self):
        with self.assertRaises(Invalid):
            github_read.issue_ref('https://other.invalid/example/repo/issues/1')
        with patch.object(github_read, 'api', return_value={'pull_request': {}}):
            with self.assertRaises(Invalid):
                github_read.issue('https://github.com/example/project/issues/1')


if __name__ == '__main__':
    unittest.main()
