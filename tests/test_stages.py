"""Explicit stage flow, closure status and the sub-agent ledger against fixture issues."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-workflow/scripts'
sys.path.insert(0, str(SCRIPTS))
from common import Invalid, VERSION, digest, write
import github_read
import handoffs
import stages
import workflow

PARENT = 'https://github.com/example/core/issues/10'
CHILD = 'https://github.com/example/core/issues/11'
OTHER = 'https://github.com/example/front/issues/12'


def decision(identifier, affects, status='pending'):
    row = {'id': identifier, 'question': 'Block disconnecting the home store?', 'options': ['block', 'allow'],
           'recommended': 'allow', 'default_if_unconfirmed': 'keep current behavior', 'affects': affects,
           'status': status}
    if status == 'confirmed':
        row['answer'] = 'allow, confirmed by product'
    return row


class StageCases(unittest.TestCase):
    def setUp(self):
        self.issues = {
            PARENT: self.issue(PARENT, 'Parent plan without a structured task yet.'),
            CHILD: self.issue(CHILD, self.task_body(CHILD, ['A1', 'A2'])),
            OTHER: self.issue(OTHER, self.task_body(OTHER, ['B1'])),
        }
        self.comment_id = 0

    def issue(self, url, body):
        return {'html_url': url, 'updated_at': '2026-10-11T00:00:00Z', 'assignees': [{'login': 'alice'}],
                'body': body, 'comments_data': [], 'state': 'open'}

    def task_body(self, url, acceptance):
        task = {'schema_version': 2, 'id': url, 'base': '1' * 40, 'goal': 'Deliver one slice', 'non_goals': [],
                'kind': 'code', 'risks': [], 'acceptance': [{'id': a, 'expectation': 'works', 'checks': []} for a in acceptance]}
        return 'Spec.\n\n```team-workflow-task\n' + json.dumps({'schema_version': 3, 'parent': PARENT, 'task': task}) + '\n```\n'

    def github(self, endpoint, paginate=False, binary=False):
        for url, issue in self.issues.items():
            repo, number = github_read.issue_ref(url)
            if endpoint == f'repos/{repo}/issues/{number}':
                return copy.deepcopy(issue)
            if endpoint.startswith(f'repos/{repo}/issues/{number}/comments'):
                return copy.deepcopy(issue['comments_data'])
        raise Invalid('Fixture cannot resolve ' + endpoint)

    def post(self, url, markdown):
        self.comment_id += 1
        self.issues[url]['comments_data'].append({'html_url': f'{url}#issuecomment-{self.comment_id}', 'body': markdown})

    def advance(self, stage, **change):
        with patch.object(github_read, 'api', side_effect=self.github):
            result = stages.draft(PARENT, {'stage': stage, 'note': 'Advance to ' + stage, **change})
        self.post(PARENT, result['markdown'])
        return result

    def status(self):
        with patch.object(github_read, 'api', side_effect=self.github):
            return stages.status(PARENT)

    def handoff(self, url, remaining=(), questions=(), verified=('https://github.com/example/core/actions/runs/1',)):
        with patch.object(github_read, 'api', side_effect=self.github):
            source = handoffs.task_source(github_read.issue(url))
        row = {'schema_version': 3, 'kind': 'handoff', 'task': url, 'requirements': digest(source), 'previous': None,
               'owner': 'alice', 'done': ['Implemented'], 'verified': list(verified), 'remaining': list(remaining),
               'questions': list(questions), 'next': 'Close after review', 'versions': [], 'references': [],
               'participants': [], 'contracts': [], 'dependencies': [], 'joint_owner': '', 'workflow_version': VERSION}
        self.post(url, '## 工作交接\n\n```team-workflow-handoff\n' + json.dumps(row) + '\n```\n')

    def through_g1(self, decisions):
        self.advance('S0')
        self.advance('S1', decisions=decisions)
        self.advance('G1')
        return self.advance('S2', confirmation='https://github.com/example/core/issues/10#issuecomment-99',
                            children=[CHILD, OTHER])

    def test_stages_advance_one_step_and_gates_need_confirmation(self):
        self.advance('S0')
        with patch.object(github_read, 'api', side_effect=self.github):
            with self.assertRaisesRegex(Invalid, 'Cannot skip'):
                stages.draft(PARENT, {'stage': 'G1', 'note': 'skip'})
        self.advance('S1', decisions=[decision('R-01', [])])
        draft = self.advance('G1')
        self.assertIn('等你决定', draft['markdown'])
        self.assertIn('R-01', draft['markdown'])
        with patch.object(github_read, 'api', side_effect=self.github):
            with self.assertRaisesRegex(Invalid, 'confirmation'):
                stages.draft(PARENT, {'stage': 'S2', 'note': 'no confirmation'})
            with self.assertRaisesRegex(Invalid, 'block the whole plan'):
                stages.draft(PARENT, {'stage': 'S2', 'note': 'still pending', 'confirmation': 'approved in chat'})
            revised = stages.draft(PARENT, {'stage': 'S1', 'note': 'revise the plan after review'})
        self.assertEqual(revised['record']['stage'], 'S1')
        status = self.status()
        self.assertEqual(status['stage'], 'G1')
        self.assertIn('确认 G1', status['waiting_for_user'])
        self.assertFalse(status['closable'])

    def test_pending_decision_blocks_only_affected_children(self):
        self.through_g1([decision('R-08', ['A2'])])
        self.handoff(CHILD)
        self.handoff(OTHER)
        status = self.status()
        children = {c['issue']: c for c in status['children']}
        self.assertEqual(children[CHILD]['blocked_by'], ['R-08'])
        self.assertFalse(children[CHILD]['closable'])
        self.assertTrue(children[OTHER]['closable'], children[OTHER])
        self.assertIn('决策 R-08：Block disconnecting the home store?', status['waiting_for_user'])

    def test_child_closure_needs_complete_handoff_and_parent_needs_closed_children(self):
        self.through_g1([decision('R-01', [CHILD], 'confirmed')])
        self.handoff(CHILD, remaining=['Entry-level test'])
        self.handoff(OTHER, verified=())
        status = self.status()
        children = {c['issue']: c for c in status['children']}
        self.assertIn('仍有剩余工作', children[CHILD]['reasons'])
        self.assertIn('交接没有验证引用', children[OTHER]['reasons'])

        for url in (CHILD, OTHER):
            self.issues[url]['comments_data'] = []
            self.handoff(url)
        self.advance('S3')
        self.advance('G2')
        self.advance('S4')
        status = self.status()
        self.assertTrue(all(c['closable'] for c in status['children']), status['children'])
        self.assertFalse(status['closable'])
        self.assertTrue(any('尚未关闭' in r for r in status['reasons']))
        for url in (CHILD, OTHER):
            self.issues[url]['state'] = 'closed'
        self.assertTrue(self.status()['closable'], self.status()['reasons'])

        self.issues[CHILD]['body'] += '\nChanged acceptance prose.\n'
        stale = {c['issue']: c for c in self.status()['children']}[CHILD]
        self.assertIn('交接基于旧的需求正文，需重新交接', stale['reasons'])

    def test_closing_gate_requires_confirmed_decisions_and_invalid_records_are_gaps(self):
        self.through_g1([decision('R-12', [OTHER])])
        for stage in ('S3', 'G2', 'S4'):
            self.advance(stage)
        with patch.object(github_read, 'api', side_effect=self.github):
            with self.assertRaisesRegex(Invalid, 'every decision confirmed'):
                stages.draft(PARENT, {'stage': 'G3', 'note': 'close'})
        self.post(PARENT, '```team-workflow-stage\n{"schema_version": 1}\n```')
        status = self.status()
        self.assertFalse(status['ok'])
        self.assertTrue(any('Invalid stage record' in g for g in status['gaps']))
        with patch.object(github_read, 'api', side_effect=self.github):
            with self.assertRaisesRegex(Invalid, 'reconcile stage history'):
                stages.draft(PARENT, {'stage': 'G3', 'note': 'close'})


class LedgerCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = workflow.main(['agents', '--root', str(self.root), '--ledger', 'audit', *args])
        return code, json.loads(out.getvalue())

    def test_resumed_session_reuses_completed_agents_and_never_respawns(self):
        write(self.root / 'plan.json', [{'id': 'routing', 'purpose': 'Audit routing PRD'},
                                       {'id': 'automation', 'purpose': 'Audit automation PRD'}])
        code, created = self.cli('--plan', 'plan.json')
        self.assertEqual(code, 0, created)
        self.assertEqual(created['recover_serially'], ['routing', 'automation'])
        self.assertTrue(all(i['output'].startswith('.team-workflow/agents/audit/') for i in created['items']))
        code, again = self.cli('--plan', 'plan.json')
        self.assertEqual(code, 1)
        self.assertIn('reuse completed', again['problem'])

        code, early = self.cli('--mark', 'routing', '--status', 'completed')
        self.assertEqual(code, 1)
        self.assertIn('Write the agent output', early['problem'])
        (self.root / '.team-workflow/agents/audit/routing.md').write_text('55 items audited\n')
        code, done = self.cli('--mark', 'routing', '--status', 'completed')
        self.assertEqual(code, 0, done)
        code, failed = self.cli('--mark', 'automation', '--status', 'interrupted')
        self.assertEqual(code, 1)
        code, failed = self.cli('--mark', 'automation', '--status', 'interrupted', '--reason', 'quota exhausted before start')
        self.assertEqual(code, 0, failed)
        code, replaced = self.cli('--mark', 'routing', '--status', 'failed', '--reason', 'retry')
        self.assertEqual(code, 1)
        self.assertIn('reused, not replaced', replaced['problem'])

        code, resumed = self.cli()
        self.assertEqual(resumed['reuse'], ['routing'])
        self.assertEqual(resumed['recover_serially'], ['automation'])
        code, degraded = self.cli('--mark', 'automation', '--status', 'degraded', '--reason', 'spot-checked 5 of 21 items')
        self.assertEqual(degraded['degraded'], ['automation'])
        self.assertEqual(degraded['recover_serially'], [])
        (self.root / '.team-workflow/agents/audit/automation.md').write_text('21 items audited serially\n')
        code, recovered = self.cli('--mark', 'automation', '--status', 'completed')
        self.assertEqual(recovered['recovered'], ['automation'])
        history = next(i for i in recovered['items'] if i['id'] == 'automation')['history']
        self.assertIn('quota exhausted before start', [h['reason'] for h in history])

    def test_ledger_names_cannot_escape_the_runtime_directory(self):
        with self.assertRaises(Invalid):
            stages.ledger_path(self.root, '../outside')


if __name__ == '__main__':
    unittest.main()
