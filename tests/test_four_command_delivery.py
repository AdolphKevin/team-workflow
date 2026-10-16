"""C1: four user commands, ordinary approval/acceptance records, resumable delivery."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixtures
import test_markdown_review as markdown
import test_unified_team
import plan_fixtures as plans
from common import artifact, artifact_valid, read, write
import artifacts
import commands
import designs
import workflow

TW = fixtures.SCRIPTS.parents[1] / 'tw.py'


class FourCommandDelivery(unittest.TestCase):
    setUp, git, check = (fixtures.WorkflowCases.setUp, fixtures.WorkflowCases.git, fixtures.WorkflowCases.check)
    field, completed = markdown.MarkdownReview.field, markdown.MarkdownReview.completed
    rule = test_unified_team.UnifiedTeam.rule

    def command(self, *args):
        self.invocations = getattr(self, 'invocations', []) + [args[0]]
        result = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', *args],
                                text=True, capture_output=True)
        return result.returncode, json.loads(result.stdout)

    def configure(self, complexity='simple', passed=True):
        assertion = 'assert app.add(1,2)==3' if passed else 'assert app.add(1,2)==4'
        self.check('import app; ' + assertion + "; print('sum=3')")
        self.design = {'data_version': 1, 'kind': 'design', 'id': 'D-add', 'revision': 1,
            'task_id': self.task['id'], 'assessment': {'complexity': complexity, 'risks': [],
                'effort': 'one hour', 'drivers': ['single function'], 'uncertainties': [], 'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Addition', 'body': self.task['goal'], 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Result', 'body': self.task['acceptance'][0]['expectation'], 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Implement', 'body': 'Implement addition',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []}, 'depends_on': []}]}
        plans.plan(self.design)
        fixtures.write_config(self.root, self.profile)
        write(self.root / '.tw/local/task.json', plans.written_task(self.task))
        plans.write_design(self.root / '.tw/local/design.md', self.design)

    def start(self, complexity='simple', passed=True):
        self.configure(complexity, passed)
        approval = []
        if complexity != 'simple':
            value = designs.approval_draft(self.design, 'carol', 'Confirmed the business plan', mode='design')
            write(self.root / '.tw/local/plan-approval.json', value)
            approval = ['--approval', '.tw/local/plan-approval.json']
        code, result = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md', *approval)
        self.assertEqual(code, 0, result)
        self.started = result
        return result

    def run_checks(self, *extra):
        plans.submit_scenarios(self.root, self.task)
        code, result = self.command('run', '--task', self.task['id'], *extra)
        self.assertEqual(code, 0, result)
        self.ran = result
        return result

    def current_path(self):
        return artifacts.directory(self.root, self.task['id']).parent.parent / 'current.json'

    def current(self):
        return read(self.current_path())

    def draft_path(self):
        return self.current_path().parent / 'review.md'

    def submit(self, approval='是', reviewer='carol', **options):
        path = self.draft_path()
        self.assertTrue(path.is_file(), 'run should generate review.md')
        source = self.completed(path.read_text())
        source = self.field(source, '## 评审信息', '评审人', reviewer)
        if '- 批准方案与代码：' in source:
            source = self.field(source, '## 评审信息', '批准方案与代码', approval)
            source = self.field(source, '## 评审信息', '批准说明', '已独立核对方案、当前代码及实际运行。')
        source = source.replace('- 复核：待复核', '- 复核：已复核')
        path.write_text(source)
        extra = ['--request-id', options['request_id']] if options.get('request_id') else []
        return self.command('review', '--task', self.task['id'], '--submit', *extra)

    def reviewed(self, complexity='simple', approval='是'):
        self.start(complexity)
        self.run_checks()
        code, result = self.submit(approval)
        self.assertEqual(code, 0, result)
        return result

    def accepted(self, complexity='simple'):
        self.reviewed(complexity)
        code, result = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        return result

    def test_successful_run_generates_review_and_gives_submit_command(self):
        self.start()
        result = self.run_checks()
        self.assertEqual(self.root / result['review_file'], self.draft_path())
        self.assertTrue(self.draft_path().is_file())
        self.assertIn('--submit', result['next_action'])
        self.assertIsNone(self.current()['review'])

    def assert_start_matches_status(self, complexity, next_id):
        self.configure(complexity)
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(started['next_step'], status['next_step'])
        self.assertEqual(started['steps'], status['steps'])
        self.assertIn('场景验收', [row['label'] for row in started['steps']])
        self.assertEqual(started['next_step']['id'], next_id)
        self.assertEqual(started['next_action'], status['next_action'])
        self.assertIn('--task ' + self.task['id'], started['next_action'])
        code, continued = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, continued)
        code, latest = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, latest)
        self.assertEqual(continued['steps'], latest['steps'])
        self.assertEqual(continued['next_step'], latest['next_step'])
        self.assertEqual(continued['next_action'], latest['next_action'])

    def test_simple_start_and_status_share_steps_and_next_command(self):
        self.assert_start_matches_status('simple', 'run')

    def test_medium_start_and_status_share_steps_and_next_command(self):
        self.assert_start_matches_status('medium', 'approval')

    def test_local_delivery_summary_states_ci_is_unverified(self):
        self.reviewed()
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['ci_verified_checks'], [])
        self.assertIn('检查只在本机运行，CI 未验证', result['summary_markdown'].split('**还没做或需要注意的**')[1].split('**状态**')[0])
        group = self.current()
        for key in ('acceptance', 'delivery_report', 'delivery'):
            record = read(artifact_valid(self.root, group[key]))
            self.assertEqual(record['task_id'], self.task['id'])
        self.assertEqual(read(artifact_valid(self.root, group['acceptance']))['kind'], 'acceptance')
        self.assertEqual(read(artifact_valid(self.root, group['delivery']))['kind'], 'delivery-verification')
        self.assertTrue(result['business_accepted'])
        self.assertTrue(result['delivery_complete'])
        self.assertIn('场景汇总：', result['summary_markdown'])
        self.assertIn('一次通过率：', result['summary_markdown'])

    def test_start_text_has_one_next_step(self):
        self.configure()
        result = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', 'start',
            '--task', '.tw/local/task.json', '--design', '.tw/local/design.md', '--format', 'text'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count('下一步：'), 1, result.stdout)

    def test_failed_run_does_not_create_review(self):
        self.start(passed=False)
        code, result = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1, result)
        self.assertFalse(self.draft_path().exists())
        self.assertNotIn('review_file', result)

    def test_partial_success_waits_for_all_required_checks_before_generating_review(self):
        self.configure()
        self.profile['checks']['extra'] = copy.deepcopy(self.profile['checks']['unit'])
        self.profile['required_checks']['code'].append('extra')
        fixtures.write_config(self.root, self.profile)
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        unit = self.run_checks('--check', 'unit')
        self.assertFalse(self.draft_path().exists())
        self.assertNotIn('review_file', unit)
        extra = self.run_checks('--check', 'extra')
        self.assertTrue(self.draft_path().is_file())
        self.assertEqual(extra['review_file'], str(self.draft_path().relative_to(self.root)))

    def test_auxiliary_run_does_not_overwrite_a_still_valid_unsubmitted_draft(self):
        self.start()
        self.profile['checks']['aux'] = copy.deepcopy(self.profile['checks']['unit'])
        fixtures.write_config(self.root, self.profile)
        self.run_checks()
        path = self.draft_path()
        self.assertTrue(path.is_file())
        path.write_text(self.field(path.read_text(), '## 评审信息', '评审人', 'carol'))
        before = path.read_bytes()
        result = self.run_checks('--check', 'aux')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(result['review_file'], str(path.relative_to(self.root)))

    def test_combined_approval_tracks_selected_required_runs_not_auxiliary_candidates(self):
        self.start()
        self.profile['checks']['aux'] = copy.deepcopy(self.profile['checks']['unit'])
        fixtures.write_config(self.root, self.profile)
        self.run_checks()
        code, submitted = self.submit()
        self.assertEqual(code, 0, submitted)
        approved = submitted['approval']
        source = self.draft_path().read_bytes()
        self.run_checks('--check', 'aux')
        self.assertEqual(self.draft_path().read_bytes(), source)
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertIn(approved, self.current()['approvals'])

    def test_yes_generates_combined_approval_and_accept_passes(self):
        submitted = self.reviewed()
        self.assertIn('approval', submitted)
        approved = read(artifact_valid(self.root, submitted['approval']))
        self.assertEqual((approved['mode'], approved['reviewer']), ('combined', 'carol'))
        self.assertEqual(approved['run_refs'], [self.ran['artifact']])
        self.assertIn(submitted['approval'], self.current()['approvals'])
        code, result = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'])

    def test_simple_task_does_not_approve_unrelated_medium_task_sections(self):
        self.configure()
        acceptance = copy.deepcopy(self.design['sections'][1])
        acceptance['id'] = 'A2'
        task = copy.deepcopy(self.design['sections'][2])
        task.update(id='T2', title='Other independent task')
        task['data'].update(acceptance=['A2'], scope=['unused.py'],
                            assessment={**self.design['assessment'], 'complexity': 'medium'})
        self.design['sections'] += [acceptance, task]
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        self.run_checks()
        code, submitted = self.submit()
        self.assertEqual(code, 0, submitted)
        approved = read(artifact_valid(self.root, submitted['approval']))
        self.assertEqual(set(approved['sections']), {'scope-global', 'A1', 'T1'})

    def test_no_or_empty_approval_leaves_accept_blocked(self):
        self.start()
        self.run_checks()
        for value in ('否', ''):
            with self.subTest(value=value):
                code, submitted = self.submit(value)
                self.assertEqual(code, 0, submitted)
                self.assertNotIn('approval', submitted)
                self.assertEqual(self.current()['approvals'], [])
                code, refused = self.command('accept', '--task', self.task['id'])
                self.assertEqual(code, 1, refused)
                self.assertIn('approval', refused['problem'].lower())

    def test_medium_task_does_not_offer_combined_approval_fields(self):
        self.start('medium')
        self.run_checks()
        self.assertTrue(self.draft_path().is_file())
        self.assertNotIn('批准方案与代码', self.draft_path().read_text())
        self.assertNotIn('批准说明', self.draft_path().read_text())

    def test_old_draft_cannot_approve_a_new_plan_assessment_with_explicit_old_runs(self):
        self.start()
        old_run = self.run_checks()['artifact']['path']
        old = self.completed(self.draft_path().read_text())
        old = self.field(old, '## 评审信息', '批准方案与代码', '是')
        saved = self.root / '.tw/local/old-plan-review.md'
        saved.write_text(old)
        self.draft_path().write_text(old)
        self.design['assessment']['effort'] = 'A different material group with the same task ID'
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        self.assertEqual(self.current()['runs'], [])
        code, refused = self.command('review', '--task', self.task['id'], '--context', self.current()['context']['path'],
                                     '--run', old_run, '--submit', '--file', str(saved))
        self.assertEqual(code, 1, refused)
        self.assertIn('绑定', refused['problem'])
        self.assertEqual(self.current()['approvals'], [])
        self.assertIsNone(self.current()['review'])
        code, refreshed = self.command('review', '--task', self.task['id'], '--run', old_run)
        self.assertEqual(code, 0, refreshed)
        self.assertTrue(refreshed['recheck'])
        self.assertIn('方案', self.draft_path().read_text())
        info = self.draft_path().read_text().split('## 评审信息', 1)[1].split('## 规范 standards', 1)[0]
        self.assertIn('- 批准方案与代码：是', info)
        self.assertIn('- 复核：待复核', info)

    def test_medium_to_simple_assessment_refreshes_old_draft_with_approval_fields(self):
        self.start('medium')
        old_run = self.run_checks()['artifact']['path']
        self.draft_path().write_text(self.completed(self.draft_path().read_text()))
        self.assertNotIn('批准方案与代码', self.draft_path().read_text())
        self.design['assessment']['complexity'] = 'simple'
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        code, refused = self.command('review', '--task', self.task['id'], '--run', old_run, '--submit')
        self.assertEqual(code, 1, refused)
        self.assertIn('绑定', refused['problem'])
        self.assertIsNone(self.current()['review'])
        code, refreshed = self.command('review', '--task', self.task['id'], '--run', old_run)
        self.assertEqual(code, 0, refreshed)
        self.assertTrue(refreshed['recheck'], refreshed)
        self.assertIn('- 批准方案与代码：', self.draft_path().read_text())
        self.assertIn('- 复核：待复核', self.draft_path().read_text())

    def test_implementer_opinion_is_saved_without_combined_approval_and_accept_is_refused(self):
        self.start()
        self.run_checks()
        code, submitted = self.submit(reviewer='bob')
        self.assertEqual(code, 0, submitted)
        self.assertEqual(self.current()['review'], submitted['artifact'])
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('implementation owner', refused['problem'])
        self.assertEqual(self.current()['approvals'], [])

    def test_changed_source_expires_approval_and_requires_explicit_approval_recheck(self):
        first = self.reviewed()
        old = read(artifact_valid(self.root, first['approval']))
        (self.root / 'app.py').write_text('def add(a,b):\n    return sum((a,b))\n')
        self.run_checks()
        path = self.draft_path()
        source = path.read_text()
        self.assertIn('- 批准方案与代码：是', source)
        start = source.index('## 评审信息')
        self.assertIn('- 复核：待复核', source[start:source.index('## 规范 standards')])
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        source = source.replace('- 复核：待复核', '- 复核：已复核')
        path.write_text(source)
        code, second = self.command('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, second)
        fresh = read(artifact_valid(self.root, second['approval']))
        self.assertNotEqual(fresh['code_digest'], old['code_digest'])
        self.assertEqual(fresh['run_refs'], [self.ran['artifact']])
        code, accepted = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)

    def test_approval_draft_accepts_flags_and_retains_record_input(self):
        self.configure('medium')
        code, result = self.command('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                                     '--reviewer', 'carol', '--confirmation', 'Confirmed the exact business plan', '--mode', 'plan')
        self.assertEqual(code, 0, result)
        value = read(artifact_valid(self.root, result['artifact']))
        self.assertEqual((value['reviewer'], value['confirmation'], value['mode']),
                         ('carol', 'Confirmed the exact business plan', 'design'))
        write(self.root / '.tw/local/approval-input.json', {'reviewer': 'carol', 'mode': 'design'})
        code, result = self.command('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                                     '--record', '.tw/local/approval-input.json')
        self.assertEqual(code, 0, result)
        self.assertEqual(read(artifact_valid(self.root, result['artifact']))['mode'], 'design')

    def test_approval_flags_are_bound_to_the_request_identity(self):
        self.configure('medium')
        arguments = ('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
                     '--reviewer', 'carol', '--mode', 'plan', '--request-id', 'approval-flags')
        code, first = self.command(*arguments, '--confirmation', 'First actual confirmation')
        self.assertEqual(code, 0, first)
        code, refused = self.command(*arguments, '--confirmation', 'Another actual confirmation')
        self.assertEqual(code, 1, refused)
        self.assertIn('different inputs', refused['problem'])

    def test_four_user_commands_deliver_without_handwritten_review_or_report_json(self):
        self.start()
        self.run_checks()
        code, submitted = self.submit()
        self.assertEqual(code, 0, submitted)
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', 'No reusable knowledge changed.')
        self.assertEqual(code, 0, delivered)
        self.assertEqual(self.invocations, ['start', 'run', 'review', 'deliver'])
        self.assertTrue(delivered['delivery_complete'])
        self.assertIn('summary_markdown', delivered)
        self.assertTrue(self.current()['acceptance'])
        self.assertTrue(self.current()['delivery_report'])
        self.assertTrue(self.current()['delivery'])
        self.assertEqual([row['step'] for row in delivered['steps']], ['acceptance', 'delivery-report', 'delivery'])

    def test_deliver_with_knowledge_reuses_existing_acceptance_and_lists_all_files(self):
        accepted = self.accepted('medium')
        self.rule()
        code, result = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertTrue(result['delivery_complete'])
        self.assertTrue(result['steps'][0]['reused'])
        self.assertEqual(self.current()['acceptance'], accepted['artifact'])
        report = read(artifact_valid(self.root, self.current()['delivery_report']))
        self.assertEqual(report['knowledge']['files'], ['.tw/rules/addition.md'])

    def test_deliver_stops_at_acceptance_for_missing_or_failed_review(self):
        self.start()
        self.run_checks()
        source = self.completed(self.draft_path().read_text())
        source = self.field(source, '## 规范 standards', '结论', '不通过')
        self.draft_path().write_text(source)
        code, submitted = self.command('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, submitted)
        self.assertEqual(read(artifact_valid(self.root, submitted['artifact']))['standards']['status'], 'failed')
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'No knowledge update.')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['stopped_at'], 'acceptance')
        self.assertFalse(result['delivery_complete'])
        self.assertFalse(self.current()['acceptance'])
        self.assertFalse(self.current()['delivery_report'])
        self.assertTrue(result['steps'][0]['result']['request_directory'])

    def test_deliver_after_source_changes_rechecks_acceptance_and_stops(self):
        accepted = self.accepted()
        (self.root / 'app.py').write_text('def add(a,b): return a+b+1\n')
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'No knowledge update.')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['stopped_at'], 'acceptance')
        self.assertFalse(result['steps'][0]['reused'])
        self.assertFalse(result['delivery_complete'])
        self.assertEqual(self.current()['acceptance'], accepted['artifact'])

    def test_deliver_without_reason_stops_at_report_then_reuses_acceptance(self):
        self.reviewed()
        code, result = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 1, result)
        self.assertEqual(result['stopped_at'], 'delivery-report')
        self.assertIn('--reason', result['next_action'])
        accepted = self.current()['acceptance']
        self.assertTrue(accepted)
        self.assertIsNone(self.current()['delivery'])
        code, result = self.command('deliver', '--task', self.task['id'], '--reason', 'Only implementation detail changed.')
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['acceptance'], accepted)
        self.assertTrue(result['steps'][0]['reused'])

    def test_existing_valid_report_is_reused_without_retyping_its_reason(self):
        self.reviewed()
        code, first = self.command('deliver', '--task', self.task['id'], '--reason', 'No reusable conclusion.')
        self.assertEqual(code, 0, first)
        report = self.current()['delivery_report']
        code, result = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertTrue(result['reused'])
        self.assertEqual(result['artifact'], self.current()['delivery'])
        self.assertEqual(self.current()['delivery_report'], report)

    def test_interrupted_deliver_reuses_the_completed_acceptance_and_report(self):
        self.reviewed()
        original = commands.dispatch
        interrupted = []

        def dispatch(args, root):
            if args.command == 'verify' and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt('stop at the public verify entry')
            return original(args, root)

        with patch.object(commands, 'dispatch', side_effect=dispatch), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            workflow.main(['deliver', '--root', str(self.root), '--task', self.task['id'], '--reason', 'No knowledge change.'])
        accepted, report = self.current()['acceptance'], self.current()['delivery_report']
        self.assertTrue(accepted)
        self.assertTrue(report)
        self.assertIsNone(self.current()['delivery'])
        code, result = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['acceptance'], accepted)
        self.assertEqual(self.current()['delivery_report'], report)
        self.assertTrue(result['steps'][0]['reused'])
        self.assertTrue(result['steps'][1]['reused'])

    def test_deliver_interrupted_before_the_report_continues_with_the_given_reason(self):
        self.reviewed()
        original = commands.dispatch
        interrupted = []

        def dispatch(args, root):
            if args.command == 'delivery-template' and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt('stop after business acceptance')
            return original(args, root)

        with patch.object(commands, 'dispatch', side_effect=dispatch), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            workflow.main(['deliver', '--root', str(self.root), '--task', self.task['id'], '--reason', 'No knowledge change.'])
        accepted = self.current()['acceptance']
        self.assertTrue(accepted)
        self.assertIsNone(self.current()['delivery_report'])
        code, result = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertTrue(result['delivery_complete'])
        self.assertTrue(result['steps'][0]['reused'])
        self.assertEqual(self.current()['acceptance'], accepted)
        report = read(artifact_valid(self.root, self.current()['delivery_report']))
        self.assertEqual(report['knowledge'], {'files': [], 'reason': 'No knowledge change.'})

    def test_omitting_changed_knowledge_is_still_rejected_by_final_verification(self):
        self.accepted('medium')
        self.rule()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        report = read(artifact_valid(self.root, drafted['artifact']))
        report['knowledge'] = {'files': [], 'reason': 'Incorrectly omitted the actual knowledge change.'}
        write(self.root / '.tw/local/omitted-knowledge.json', report)
        code, refused = self.command('verify', '--task', self.task['id'], '--report', '.tw/local/omitted-knowledge.json')
        self.assertEqual(code, 1, refused)
        self.assertIn('没有列入', refused['problem'])
        self.assertIsNone(self.current()['delivery'])

    def test_deliver_refuses_knowledge_added_after_its_report_then_regenerates_on_resume(self):
        self.reviewed('medium')
        original = commands.dispatch
        inserted = []

        def dispatch(args, root):
            if args.command == 'verify' and not inserted:
                inserted.append(self.rule('late-rule', '交付期间新增的规则'))
            return original(args, root)

        output = io.StringIO()
        with patch.object(commands, 'dispatch', side_effect=dispatch), contextlib.redirect_stdout(output):
            code = workflow.main(['deliver', '--root', str(self.root), '--task', self.task['id'], '--reason', 'No knowledge change.'])
        refused = json.loads(output.getvalue())
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['stopped_at'], 'delivery')
        self.assertIn('没有列入', refused['problem'])
        self.assertFalse(refused['delivery_complete'])
        accepted, report = self.current()['acceptance'], self.current()['delivery_report']
        self.assertIsNone(self.current()['delivery'])
        code, resumed = self.command('deliver', '--task', self.task['id'])
        self.assertEqual(code, 0, resumed)
        self.assertEqual(self.current()['acceptance'], accepted)
        self.assertNotEqual(self.current()['delivery_report'], report)
        self.assertEqual(read(artifact_valid(self.root, self.current()['delivery_report']))['knowledge']['files'], ['.tw/rules/late-rule.md'])

    def test_precondition_failure_in_a_child_keeps_the_stage_and_failure_record(self):
        self.reviewed('medium')
        original = commands.dispatch
        removed = []

        def dispatch(args, root):
            if args.command == 'verify' and not removed:
                path = artifact_valid(self.root, self.current()['delivery_report'])
                removed.append((path, path.read_bytes()))
                path.unlink()
            return original(args, root)

        output = io.StringIO()
        try:
            with patch.object(commands, 'dispatch', side_effect=dispatch), contextlib.redirect_stdout(output):
                code = workflow.main(['deliver', '--root', str(self.root), '--task', self.task['id'], '--reason', 'No knowledge change.'])
        finally:
            for path, value in removed:
                path.write_bytes(value)
        refused = json.loads(output.getvalue())
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused.get('stopped_at'), 'delivery', refused)
        failure = refused['steps'][-1]['result']
        self.assertEqual(failure['error_code'], 'current-materials-incomplete')
        self.assertTrue((self.root / failure['request_directory'] / 'response.json').is_file())
        self.assertIsNone(self.current()['delivery'])

    def test_same_deliver_request_retries_without_more_child_records(self):
        self.reviewed()
        args = ('deliver', '--task', self.task['id'], '--reason', 'No knowledge update.', '--request-id', 'deliver-retry')
        code, first = self.command(*args)
        self.assertEqual(code, 0, first)
        claims = sorted(self.current_path().parent.glob('requests/*/request.json'))
        code, again = self.command(*args)
        self.assertEqual(code, 0, again)
        self.assertTrue(again['reused'])
        self.assertEqual(again['artifact'], self.current()['delivery'])
        self.assertEqual(sorted(self.current_path().parent.glob('requests/*/request.json')), claims)

    def test_combined_submission_same_request_is_idempotent(self):
        self.start()
        self.run_checks()
        code, first = self.submit(request_id='approve-and-review')
        self.assertEqual(code, 0, first)
        code, again = self.command('review', '--task', self.task['id'], '--submit', '--request-id', 'approve-and-review')
        self.assertEqual(code, 0, again)
        self.assertEqual(first['artifact'], again['artifact'])
        self.assertEqual(first['approval'], again['approval'])


if __name__ == '__main__':
    unittest.main()
