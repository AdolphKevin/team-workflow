"""A single-person task closes with one reviewed note instead of a separate implementation handoff."""
import copy
import json
import unittest
import test_workflow as fixtures
from unittest.mock import patch

import test_delivery
from common import Invalid, artifact
import coordination
import delivery
import github_read
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
        self.setup_task(task_id=URL)
        self.git('add', '.tw')
        self.git('commit', '-qm', 'project configuration and knowledge')
        self.issue = {'html_url': URL, 'state': 'open', 'assignees': [{'login': 'bob'}], 'comments_data': [],
                      'body': 'Fix buyer credential.\n\n```team-workflow-task\n'
                              + json.dumps({'data_version': 1, 'parent': None, 'task': self.task}) + '\n```\n'}
        self.patch = patch.object(github_read, 'api', side_effect=self.github)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.publish(coordination.draft_design(URL, self.design), 'alice')
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
        self.assertTrue(result['closable'])
        note = result['close_note']
        record = note['record']
        self.assertEqual((record['handoff_kind'], record['creator'], record['owner'], record['remaining']),
                         ('close', 'bob', 'bob', []))
        self.assertEqual(record['close']['acceptance'], artifact(self.root, self.root / self.name('acceptance')))
        self.assertEqual(record['close']['knowledge'], self.report['knowledge'])
        self.assertIn('无需修改知识', record['close']['summary'])
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
        self.assertNotIn('close_note', again)

    def test_close_note_without_authorization_completes_delivery_but_not_closing(self):
        self.accept_and_record_knowledge()
        result = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(result['delivery_complete'])
        self.assertFalse(result['closable'])
        self.assertNotIn('close_authorization', result['close_note']['record']['close'])

    def test_shared_work_still_needs_an_implementation_handoff(self):
        self.accept_and_record_knowledge()
        self.issue['assignees'].append({'login': 'dave'})
        with self.assertRaisesRegex(Invalid, 'Delivery handoff incomplete.*single assignee'):
            delivery.verify(self.root, self.profile, self.task, self.report)

    def test_close_record_must_name_the_implementer_as_both_sides_with_nothing_left(self):
        self.accept_and_record_knowledge()
        note = delivery.verify(self.root, self.profile, self.task, self.report)['close_note']['record']
        for change, message in [({'owner': 'carol'}, 'Close note'), ({'remaining': ['Write docs']}, 'Close note'),
                                ({'creator': 'alice', 'owner': 'alice'}, 'creator must confirm')]:
            with self.subTest(change=change):
                with self.assertRaisesRegex(Invalid, message):
                    coordination._validate_handoff({**note, **change})


if __name__ == '__main__':
    unittest.main()
