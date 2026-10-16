"""A single-person task closes with one reviewed note instead of a separate implementation handoff."""
import plan_fixtures as plans
import copy
import json
import unittest
import test_workflow as fixtures
from unittest.mock import patch

import test_delivery
from common import Invalid, artifact, read
import coordination
import delivery
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import knowledge
import validation

URL = 'https://github.com/example/project/issues/149'


class CloseNote(unittest.TestCase):
    base = test_delivery.DeliveryCases
    git, check, setup_task, write, name = (base.git, base.check, base.setup_task,
                                                    base.write, base.name)

    def setUp(self):
        self.base.setUp(self)
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.profile['platform'] = copy.deepcopy(PLATFORM_CONFIG)
        fixtures.write_config(self.root, self.profile)
        self.setup_task(task_id=URL)
        self.git('add', '.tw')
        self.git('commit', '-qm', 'project configuration and knowledge')
        self.issue = {'html_url': URL, 'state': 'open', 'assignees': [{'login': 'bob'}], 'comments_data': [],
                      'body': plans.task_body(self.task, prose='Fix buyer credential.')}
        self.patch = patch.object(platform_read, 'call', side_effect=platform_transport(self.github))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.publish(plans.draft_design(self.root, URL, self.design), 'alice')
        approval = coordination.draft_approval(URL, {'reviewer': 'carol', 'confirmation': 'Plan and code accepted',
            'code_digest': validation.source_digest(self.root, self.profile),
            'run_refs': [artifact(self.root, self.root / path) for path in self.runs]})
        self.publish(approval, 'carol')
        self.write('approval', approval['record']['approval'])

    def github(self, endpoint, paginate=False, binary=False):
        if endpoint == 'repos/example/project/issues/149':
            return copy.deepcopy(self.issue)
        if endpoint.startswith('repos/example/project/issues/149/comments'):
            return copy.deepcopy(self.issue['comments_data'])
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Fixture cannot resolve ' + endpoint)

    def publish(self, draft, author):
        number = len(self.issue['comments_data']) + 1
        self.issue['comments_data'].append({'html_url': f'{URL}#issuecomment-{number}', 'body': draft['markdown'],
                                            'user': {'login': author}})

    def accept_and_record_knowledge(self):
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.write('acceptance', accepted)
        self.report['acceptance'] = self.name('acceptance')
        self.report['knowledge'] = {'files': [], 'reason': 'Existing requirement owns the behavior'}

    def test_single_assignee_gets_a_close_note_and_closes_after_posting_it(self):
        self.accept_and_record_knowledge()
        self.report['close_authorization'] = {'confirmed_by': 'blur-yin', 'reference': 'Chat confirmation 2026-10-14'}
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])  # Authorization is recorded; the note has not been published yet.
        note = result['close_note']
        record = note['record']
        self.assertEqual((record['handoff_kind'], record['creator'], record['owner'], record['remaining']),
                         ('close', 'bob', 'bob', []))
        self.assertEqual(record['close']['acceptance'], artifact(self.root, self.root / self.name('acceptance')))
        self.assertEqual(record['close']['knowledge'], self.report['knowledge'])
        self.assertIn('无需修改知识', record['close']['summary'])
        self.assertIn('A1', record['close']['summary'])
        self.assertIn('未指明用例，证据为整项检查通过', record['close']['summary'])
        self.assertIn('未指明用例，证据为整项检查通过', result['summary_markdown'])
        self.assertEqual(record['close']['close_authorization']['confirmed_by'], 'blur-yin')
        self.assertIn('## 收尾说明', note['markdown'])
        self.assertIn('draft-only', note['publication'])
        self.assertEqual(self.issue['comments_data'][-1]['user']['login'], 'carol')  # nothing was posted
        self.publish(note, 'bob')
        continuation = coordination.resume(self.root, self.profile, URL)
        self.assertTrue(continuation['ok'], continuation['gaps'])
        self.assertTrue(continuation['closed'])
        again = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(again['delivery_complete'])
        self.assertTrue(again['closable'])
        self.assertNotIn('close_note', again)

    def test_superseded_failed_run_does_not_block_the_close_note(self):
        # Real case (Issue #5): unit failed before a fix and later passed; acceptance used the passing run,
        # but drafting the close note re-inspected every listed run and refused the superseded failure.
        app = self.root / 'app.py'
        original = app.read_text()
        app.write_text('def add(a, b):\n    return a-b\n')
        failed, _ = validation.run_batch(self.root, self.profile, [self.task])
        app.write_text(original)
        self.report['runs'] = [failed.relative_to(self.root).as_posix()] + self.runs
        self.accept_and_record_knowledge()
        superseded = read(self.root / self.name('acceptance'))['superseded_execution']
        self.assertIn(failed.relative_to(self.root).as_posix(), [row['path'] for row in superseded])
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'], result)
        self.assertEqual(result['close_note']['record']['handoff_kind'], 'close')

    def test_review_findings_are_carried_into_the_close_note(self):
        # Real case (Issue #5): the review recorded resolved issues Q1–Q3; delivery required the close note
        # to keep them, but the note was drafted only from platform records and refused "Known issue disappeared".
        review = read(self.root / self.name('review'))
        review['findings'] = [{'id': 'Q1', 'summary': 'Dependency identity format differed from the checkout',
                               'owner': 'bob', 'affects': ['A1'], 'blocks': ['acceptance'], 'state': 'resolved',
                               'resolution': {'reason': 'Configuration corrected and rechecked',
                                              'evidence': ['app.py']}}]
        self.write('review', review)
        self.accept_and_record_knowledge()
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'], result)
        self.assertEqual([row['id'] for row in result['close_note']['record']['questions']], ['Q1'])

    def test_close_note_without_authorization_completes_delivery_but_not_closing(self):
        self.accept_and_record_knowledge()
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])
        self.assertNotIn('close_authorization', result['close_note']['record']['close'])

    def test_single_platform_owner_can_receive_an_agent_implementers_close_note(self):
        self.design['roles']['implementation_owner'] = 'Codex'
        self.write('design', self.design)
        self.issue.update(assignees=[{'login': 'AdolphKevin'}], comments_data=[])
        self.publish(plans.draft_design(self.root, URL, self.design), 'alice')
        approval = coordination.draft_approval(URL, {'reviewer': 'carol',
            'code_digest': validation.source_digest(self.root, self.profile),
            'run_refs': [artifact(self.root, self.root / path) for path in self.runs]})
        self.publish(approval, 'carol')
        self.write('approval', approval['record']['approval'])
        self.accept_and_record_knowledge()
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'])
        note = result['close_note']
        self.assertEqual((note['record']['creator'], note['record']['owner']), ('Codex', 'AdolphKevin'))
        self.assertNotIn('AdolphKevin', note['record']['roles'].values())
        self.assertIn('负责人 AdolphKevin；实施 Codex', note['markdown'])
        self.publish(note, 'Codex')
        resumed = coordination.resume(self.root, self.profile, URL)
        self.assertTrue(resumed['ok'], resumed['gaps'])
        self.assertTrue(resumed['closed'])
        again = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(again['delivery_complete'])
        self.assertNotIn('close_note', again)

    def test_shared_work_still_needs_an_implementation_handoff(self):
        self.accept_and_record_knowledge()
        self.issue['assignees'].append({'login': 'dave'})
        with self.assertRaisesRegex(Invalid, '任务有多名负责人，请发布实施交接'):
            delivery.verify(self.root, self.profile, self.task, self.report)

    def test_no_platform_owner_requires_assigning_the_issue_to_one_person(self):
        self.accept_and_record_knowledge()
        self.issue['assignees'] = []
        with self.assertRaisesRegex(Invalid, '请先将 Issue 指派给一位负责人'):
            delivery.verify(self.root, self.profile, self.task, self.report)

    def test_shared_repository_responsibility_and_cross_service_risk_still_block_close_notes(self):
        state = coordination.load(URL, root=self.root)
        profile = copy.deepcopy(self.profile)
        dependency = {'kind': 'repository', 'repository': 'github.com/example/common', 'role': 'build'}
        profile['external_inputs'] = {'common': dependency}
        self.assertEqual(coordination.closable_alone(state, profile), [])
        for role in ('modified', 'joint'):
            with self.subTest(role=role):
                dependency['role'] = role
                self.assertIn('modified or joint repositories need their own responsibility: github.com/example/common',
                              coordination.closable_alone(state, profile))
        state['task']['risks'] = ['cross-service']
        self.assertIn('cross-service work needs a joint verification owner',
                      coordination.closable_alone(state, self.profile))

    def test_close_record_allows_a_receiver_outside_design_roles_and_keeps_creator_and_completion_checks(self):
        self.accept_and_record_knowledge()
        note = delivery.verify(self.root, self.profile, self.task, self.report)['close_note']['record']
        coordination._validate_handoff({**note, 'owner': 'AdolphKevin'})
        for change, message in [({'remaining': ['Write docs']}, '收尾说明必须没有剩余事项'),
                                ({'creator': 'alice', 'owner': 'alice'}, 'creator must confirm')]:
            with self.subTest(change=change):
                with self.assertRaisesRegex(Invalid, message):
                    coordination._validate_handoff({**note, **change})

    def test_close_note_receiver_must_be_the_single_platform_owner(self):
        self.accept_and_record_knowledge()
        note = delivery.verify(self.root, self.profile, self.task, self.report)['close_note']['record']
        progress = {key: note[key] for key in ('creator', 'owner', 'next', 'verified')}
        for receiver in ('carol', 'AdolphKevin'):
            with self.subTest(receiver=receiver):
                result = coordination.draft(self.root, self.profile, URL, {**progress, 'owner': receiver},
                                            kind='close', close=note['close'])
                self.assertFalse(result['ok'])
                self.assertIn('收尾说明的接收负责人必须是任务唯一的平台负责人', result['gaps'])

    def test_implementation_handoff_receiver_still_needs_a_role_and_platform_assignment(self):
        progress = {'creator': 'bob', 'owner': 'AdolphKevin', 'next': 'Continue implementation',
                    'remaining': ['Finish implementation']}
        with self.assertRaisesRegex(Invalid, 'receiver needs a declared responsibility'):
            coordination.draft(self.root, self.profile, URL, progress)
        result = coordination.draft(self.root, self.profile, URL, {**progress, 'owner': 'carol'})
        self.assertFalse(result['ok'])
        self.assertIn('Handoff receiver is not assigned to this task', result['gaps'])


if __name__ == '__main__':
    unittest.main()
