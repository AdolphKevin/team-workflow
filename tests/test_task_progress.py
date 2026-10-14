"""Login policy, step checklist with the next command, rule changes and local run statistics."""
import contextlib
import io
import json
import unittest
import test_workflow as fixtures
from unittest.mock import patch

import test_delivery
from common import Invalid, accounts, write
import common
import workflow


class TaskProgress(unittest.TestCase):
    base = test_delivery.DeliveryCases
    git, check, setup_task, write, name = (base.git, base.check, base.setup_task,
                                                    base.write, base.name)

    def setUp(self):
        self.base.setUp(self)
        self.setup_task()

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main([*args, '--root', str(self.root)])
        text = output.getvalue()
        return code, (json.loads(text) if text.startswith('{') else text)

    def declare_accounts(self):
        self.profile['accounts'] = [
            {'id': 'e2e-owner', 'kind': 'synthetic', 'environment': 'local acceptance (localhost:3010)',
             'login': 'agent-after-authorization', 'isolation': 'Disposable PostgreSQL and mail capture per run',
             'credential_env': ['E2E_OWNER_EMAIL']},
            {'id': 'shopify-partner', 'kind': 'real', 'environment': 'Shopify partner dashboard', 'login': 'user'}]
        fixtures.write_config(self.root, self.profile)

    def test_account_rules(self):
        good = {'id': 'a', 'kind': 'synthetic', 'environment': 'local', 'login': 'agent-after-authorization',
                'isolation': 'per-run database'}
        accounts([good])
        for change, message in [({'kind': 'real'}, 'always signed in by the user'),
                                ({'isolation': ''}, 'non-empty text'),
                                ({'credential_env': ['secret-value!']}, 'variable names'),
                                ({'login': 'headless'}, 'user or agent-after-authorization')]:
            with self.subTest(change=change):
                with self.assertRaisesRegex(Invalid, message):
                    accounts([{**good, **change}])

    def test_prepare_asks_before_agent_login_and_records_the_grant(self):
        self.declare_accounts()
        code, prepared = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, prepared)
        context = json.loads((self.root / prepared['artifact']['path']).read_text())
        self.assertEqual(context['login_policy']['agent_after_authorization'], ['e2e-owner'])
        self.assertIn('shopify-partner', context['login_policy']['user_signs_in'])
        self.assertEqual(context['authorizations_needed'][0]['accounts'], ['e2e-owner'])
        self.assertIn('真实账号仍由你本人', context['next_action'])
        code, refused = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'), '--grant', 'synthetic-login')
        self.assertEqual(code, 1)
        self.assertIn('--confirmed-by', refused['problem'])
        code, granted = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'),
                                 '--grant', 'synthetic-login', '--confirmed-by', 'blur-yin')
        context = json.loads((self.root / granted['artifact']['path']).read_text())
        self.assertEqual(context['authorizations'][0]['confirmed_by'], 'blur-yin')
        self.assertEqual(context['authorizations_needed'], [])
        code, status = self.cli('status', '--context', granted['artifact']['path'])
        self.assertEqual(status['authorizations'][0]['accounts'], ['e2e-owner'])

    def test_request_id_rejects_changed_tool_override_and_login_authorization(self):
        self.declare_accounts()
        cases = [
            ('tool-override', [], ['--allow-modified-tool']),
            ('login-grant', ['--confirmed-by', 'carol'],
             ['--confirmed-by', 'carol', '--grant', 'synthetic-login']),
            ('login-confirmer', ['--grant', 'synthetic-login', '--confirmed-by', 'carol'],
             ['--grant', 'synthetic-login', '--confirmed-by', 'alice']),
        ]
        for request_id, first_options, changed_options in cases:
            with self.subTest(option=request_id):
                args = ['prepare', '--task', self.name('task'), '--design', self.name('design'),
                        '--request-id', request_id]
                code, original = self.cli(*args, *first_options)
                self.assertEqual(code, 0, original)
                original_file = (self.root / original['artifact']['path']).read_bytes()
                code, cached = self.cli(*args, *first_options)
                self.assertEqual((code, cached), (0, original))
                code, changed = self.cli(*args, *changed_options)
                self.assertEqual(code, 1, changed)
                self.assertIn('Request ID already belongs to different inputs', changed['problem'])
                self.assertEqual((self.root / original['artifact']['path']).read_bytes(), original_file)

    def test_status_lists_steps_and_the_next_exact_command(self):
        code, prepared = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'))
        context = prepared['artifact']['path']
        code, status = self.cli('status', '--context', context)
        states = {row['id']: row['state'] for row in status['steps']}
        self.assertEqual((states['prepare'], states['run']), ('done', 'pending'))
        self.assertEqual(status['next_step']['id'], 'run')
        self.assertIn(f'run --root "$PROJECT" --context {context}', status['next_step']['next_command'])
        self.cli('run', '--context', context)
        code, accepted = self.cli('verify', '--context', context, '--report', self.name('report'), '--phase', 'acceptance')
        self.assertEqual(code, 0, accepted)
        code, text = self.cli('status', '--context', context, '--format', 'text')
        self.assertIn('[-] 生成并完成代码与验收评审（工具没有记录', text)
        self.assertIn('[x] 业务验收', text)
        self.assertIn('下一步：交付报告写明知识处置', text)
        self.assertIn('tw team delivery-template', text)
        self.assertIn('--acceptance ' + accepted['artifact']['path'], text)
        (self.root / 'app.py').write_text('def add(a, b):\n    return a + b  # changed\n')
        code, stale = self.cli('status', '--context', context)
        self.assertEqual({row['id']: row['state'] for row in stale['steps']}['acceptance'], 'stale')

    def test_run_names_checks_whose_inputs_changed_while_they_ran(self):
        self.check("from pathlib import Path; Path('app.py').write_text(Path('app.py').read_text() + '# touched')")
        fixtures.write_config(self.root, self.profile)
        code, result = self.cli('run', '--task', self.name('task'))
        self.assertEqual(code, 1, result)
        self.assertEqual(result['checks'][0]['status'], 'passed')
        self.assertIs(result['checks'][0]['source_unchanged'], False)
        self.assertIn('inputs of unit changed while the check ran', result['problem'])
        self.assertIn('--check unit', result['next_action'])

    def test_status_marks_execution_stale_after_source_changes(self):
        code, executed = self.cli('run', '--task', self.name('task'))
        self.assertEqual(code, 0, executed)
        record = json.loads((self.root / executed['artifact']['path']).read_text())
        self.assertNotIn('source_digest', record)
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['run'], 'done')
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['run'], 'stale')
        self.assertEqual(status['next_step']['id'], 'run')
        self.assertIn('run --root "$PROJECT" --task ' + self.name('task'), status['next_step']['next_command'])

    def test_status_marks_final_delivery_stale_after_source_changes(self):
        code, accepted = self.cli('verify', '--task', self.name('task'), '--report', self.name('report'),
                                  '--phase', 'acceptance', '--out', self.name('acceptance'))
        self.assertEqual(code, 0, accepted)
        self.report['acceptance'] = self.name('acceptance')
        self.report['knowledge'] = {'files': [], 'reason': 'No new reusable constraint'}
        self.write('report', self.report)
        code, completed = self.cli('verify', '--task', self.name('task'), '--report', self.name('report'))
        self.assertEqual(code, 0, completed)
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['delivery'], 'done')
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        states = {row['id']: row['state'] for row in status['steps']}
        self.assertEqual((states['acceptance'], states['delivery']), ('stale', 'stale'))
        self.assertEqual(status['next_step']['id'], 'acceptance')  # final delivery needs a current acceptance first

    def test_status_respects_revision_sensitive_execution_sources(self):
        self.profile['checks']['unit']['revision_sensitive'] = True
        fixtures.write_config(self.root, self.profile)
        code, executed = self.cli('run', '--task', self.name('task'))
        self.assertEqual(code, 0, executed)
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['run'], 'done')
        self.git('commit', '--allow-empty', '-qm', 'New revision, identical content')
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['run'], 'stale')

    def test_status_records_delivery_disposition_step(self):
        code, accepted = self.cli('verify', '--task', self.name('task'), '--report', self.name('report'),
                                  '--phase', 'acceptance', '--out', self.name('acceptance'))
        self.assertEqual(code, 0, accepted)
        code, drafted = self.cli('delivery-template', '--task', self.name('task'), '--design', self.name('design'),
                                 '--brief', self.name('brief'), '--review', self.name('review'))
        self.assertEqual(code, 0, drafted)
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['knowledge'], 'done')
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        code, status = self.cli('status', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, status)
        self.assertEqual({row['id']: row['state'] for row in status['steps']}['acceptance'], 'stale')

    def test_modified_installations_are_refused_with_tool_modified(self):
        import os
        from tw_runtime import install
        modified = {'ok': False, 'installed_ok': True, 'problems': ['scripts/tw_runtime/team/knowledge.py changed'],
                    'installation_problems': [], 'notes': []}
        with patch.dict(os.environ, {common.ALLOW_MODIFIED: ''}), patch.object(install, 'check_install', return_value=modified):
            code, result = self.cli('verify', '--task', self.name('task'), '--report', self.name('report'), '--phase', 'acceptance')
            self.assertEqual((code, result['error_code']), (1, 'tool-modified'))
            self.assertIn('scripts/tw_runtime/team/knowledge.py', result['problem'])
            self.assertIn('Reinstall', result['next_action'])
            code, project = self.cli('project')
            self.assertEqual((code, project['error_code']), (1, 'tool-modified'))

    def test_acceptance_output_explains_a_re_evaluated_registration(self):
        code, result = self.cli('verify', '--task', self.name('task'), '--report', self.name('report'), '--phase', 'acceptance')
        self.assertEqual(code, 0, result)
        self.assertIn('summary_markdown', result)  # shown directly, not only in the artifact
        self.assertEqual(result['re_evaluated'], [])

    def test_rule_changes_during_a_task_are_visible(self):
        code, prepared = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'))
        with patch.object(common, 'rules_digest', return_value='0' * 64):
            code, status = self.cli('status', '--context', prepared['artifact']['path'], '--format', 'text')
        self.assertIn('团队流程规则已更新', status)

    def test_metrics_count_requests_reruns_and_failures(self):
        code, prepared = self.cli('prepare', '--task', self.name('task'), '--design', self.name('design'))
        context = prepared['artifact']['path']
        for _ in range(2):
            self.cli('run', '--context', context)
        self.cli('verify', '--context', context, '--report', self.name('design'), '--phase', 'acceptance')
        code, result = self.cli('metrics', '--task', self.name('task'))
        self.assertEqual(code, 0, result)
        row = result['metrics'][0]
        self.assertEqual(row['commands']['run']['requests'], 2)
        self.assertEqual(row['checks']['unit'], {'runs': 2, 'passed': 2, 'reruns': 1})
        self.assertEqual(row['commands']['verify:acceptance'], {**row['commands']['verify:acceptance'], 'requests': 1, 'failed': 1})
        code, text = self.cli('metrics', '--task', self.name('task'), '--format', 'text')
        self.assertIn('检查 unit 运行 2 次（重跑 1 次）', text)


if __name__ == '__main__':
    unittest.main()
