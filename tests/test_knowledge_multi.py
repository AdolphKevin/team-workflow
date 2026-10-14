"""Several issues sharing one implementation share one CS task record; each keeps its own acceptance."""
import copy
import json
import unittest

import test_delivery
from common import Invalid, artifact, read, write
import delivery
import knowledge

FIRST = 'TASK-149'
SECOND = 'TASK-150'


class SharedKnowledgeRecord(unittest.TestCase):
    base = test_delivery.DeliveryCases
    git, check, fake_cs, setup_task, write = base.git, base.check, base.fake_cs, base.setup_task, base.write
    prefix = ''

    def name(self, name):
        return '.team-workflow/' + self.prefix + name + '.json'

    def accept(self, task_id, prefix):
        """Build one issue's real acceptance; both issues share the repository, check and source."""
        self.prefix = prefix
        if hasattr(self, 'skill'):
            self.fake_cs = lambda: self.skill
            self.task = copy.deepcopy(self.first_task)
            self.task['acceptance'][0]['checks'] = []
        self.setup_task(task_id=task_id)
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')
        self.write('acceptance', accepted)
        return copy.deepcopy(self.task), self.root / self.name('acceptance')

    def setUp(self):
        self.base.setUp(self)
        self.first_task = copy.deepcopy(self.task)
        self.task_a, self.accepted_a = self.accept(FIRST, 'a-')
        self.task_b, self.accepted_b = self.accept(SECOND, 'b-')
        # The CS fixture returns whatever record was last applied, like a real canonical task note.
        (self.skill / 'scripts/cs_knowledge.py').write_text(
            'import json,sys\nfrom pathlib import Path\n'
            'root=Path(sys.argv[sys.argv.index("--root")+1])\n'
            'stored=root/".team-workflow/cs-task.json"\n'
            'task=json.loads(stored.read_text()) if stored.exists() else {"source":{},"external_refs":[],'
            '"scopes":[{"repository":"self","path":"app.py"}],"status":"in-progress"}\n'
            'if "template" in sys.argv:\n'
            ' print(json.dumps({"ok":True,"task":task,"items":[]}))\n'
            'else:\n'
            ' print(json.dumps({"ok":True,"state":"0"*64,"kind":"receipt-check","read_only":True,"query_state":{},'
            '"changed":[],"receipt":{"query_state":{}},"task_status":task["status"],"canonical_task_id":"CS-T",'
            '"task_revision":1,"files":[".codestable/wiki/task.md"],"records":[{"id":"CS-T","path":".codestable/wiki/task.md",'
            '"relations":["task-note"]}],"scopes":task["scopes"],"external_refs":task["external_refs"]}))\n')

    def apply(self, payload):
        write(self.root / '.team-workflow/cs-task.json', payload['task'])

    def finish(self, task, accepted):
        prefix = 'a-' if task['id'] == FIRST else 'b-'
        return knowledge.finish(self.root, self.profile, task, self.skill, 'CS-T',
                                self.root / ('.team-workflow/' + prefix + 'brief.json'), 'none', 'Shared fix', accepted)

    def test_both_issues_complete_one_record_with_their_own_acceptance(self):
        payload = knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                                [self.accepted_b, self.accepted_a], siblings=[self.task_b])
        source = payload['task']['source']['workflow_acceptances']
        self.assertEqual([row['task_id'] for row in source], [FIRST, SECOND])
        self.assertEqual(source[0], {**artifact(self.root, self.accepted_a), 'task_id': FIRST})
        self.assertEqual(payload['task']['status'], 'completed')
        self.assertEqual(knowledge.pending_acceptance(payload, [self.task_a, self.task_b]), [])
        self.assertNotIn('pending_acceptance', payload)  # CS rejects unknown top-level fields
        self.assertEqual([ref['id'] for ref in payload['task']['external_refs']], [FIRST, SECOND])
        self.apply(payload)
        for task, accepted in ((self.task_a, self.accepted_a), (self.task_b, self.accepted_b)):
            with self.subTest(task=task['id']):
                completion = self.finish(task, accepted)
                self.assertEqual(completion['acceptance'], artifact(self.root, accepted))

    def test_github_entry_names_the_normalized_issue(self):
        issue = {'id': 'https://github.com/Example/Project/issues/149'}
        entry = knowledge.acceptance_entry(self.root, issue, self.accepted_a)
        self.assertEqual(entry['issue'], 'https://github.com/example/project/issues/149')
        self.assertEqual(entry['task_id'], issue['id'])

    def test_partial_acceptance_keeps_the_shared_record_in_progress(self):
        payload = knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                                [self.accepted_a], siblings=[self.task_b])
        self.assertEqual(payload['task']['status'], 'in-progress')
        self.assertEqual(knowledge.pending_acceptance(payload, [self.task_a, self.task_b]), [SECOND])
        self.apply(payload)
        with self.assertRaisesRegex(Invalid, 'must be completed'):
            self.finish(self.task_a, self.accepted_a)
        # The next day only #150 is accepted; #149's stored acceptance is re-validated and kept.
        later = knowledge.completion_template(self.root, self.profile, self.task_b, self.skill,
                                              [self.accepted_b], 'CS-T', siblings=[self.task_a])
        self.assertEqual(later['task']['status'], 'completed')
        self.assertEqual([row['task_id'] for row in later['task']['source']['workflow_acceptances']], [FIRST, SECOND])
        self.apply(later)
        self.finish(self.task_a, self.accepted_a)
        self.finish(self.task_b, self.accepted_b)

    def test_acceptance_must_belong_to_a_task_sharing_the_record(self):
        with self.assertRaisesRegex(Invalid, 'not sharing this knowledge record'):
            knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                          [self.accepted_a, self.accepted_b])
        with self.assertRaisesRegex(Invalid, 'Two acceptances'):
            knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                          [self.accepted_a, self.accepted_a], siblings=[self.task_b])

    def test_record_must_contain_this_issues_current_acceptance(self):
        payload = knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                                [self.accepted_a, self.accepted_b], siblings=[self.task_b])
        payload['task']['source']['workflow_acceptances'] = payload['task']['source']['workflow_acceptances'][:1]
        self.apply(payload)
        self.finish(self.task_a, self.accepted_a)
        with self.assertRaisesRegex(Invalid, 'reference the actual'):
            self.finish(self.task_b, self.accepted_b)

    def test_tampered_sibling_acceptance_is_rejected(self):
        tampered = read(self.accepted_b)
        tampered['observations'] = {'A1': []}
        write(self.accepted_b, tampered)
        with self.assertRaises(Invalid):
            knowledge.completion_template(self.root, self.profile, self.task_a, self.skill,
                                          [self.accepted_a, self.accepted_b], siblings=[self.task_b])


if __name__ == '__main__':
    unittest.main()
