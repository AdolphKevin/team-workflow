"""Sub-agent ledger: resumed sessions reuse completed results and never respawn them."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-knowledge/scripts/tw_runtime/team'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1]))
import test_workflow as fixtures
from common import Invalid, write
import agents
import workflow


class LedgerCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git

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
        self.assertTrue(all(i['output'].startswith('.tw/local/agents/audit/') for i in created['items']))
        code, again = self.cli('--plan', 'plan.json')
        self.assertEqual(code, 1)
        self.assertIn('reuse completed', again['problem'])

        code, early = self.cli('--mark', 'routing', '--status', 'completed')
        self.assertEqual(code, 1)
        self.assertIn('Write the agent output', early['problem'])
        (self.root / '.tw/local/agents/audit/routing.md').write_text('55 items audited\n')
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
        (self.root / '.tw/local/agents/audit/automation.md').write_text('21 items audited serially\n')
        code, recovered = self.cli('--mark', 'automation', '--status', 'completed')
        self.assertEqual(recovered['recovered'], ['automation'])
        history = next(i for i in recovered['items'] if i['id'] == 'automation')['history']
        self.assertIn('quota exhausted before start', [h['reason'] for h in history])

    def test_ledger_names_cannot_escape_the_runtime_directory(self):
        with self.assertRaises(Invalid):
            agents.ledger_path(self.root, '../outside')



if __name__ == '__main__':
    unittest.main()
