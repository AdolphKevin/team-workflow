"""T7 A2: start, generated acceptance requirements and accept through the public CLI."""
import copy
import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_coordination
import test_delivery
import test_workflow as fixtures
import plan_fixtures as plans
from common import artifact, digest, read, write
import delivery
import designs
import validation
import validation_session
import coordination
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import workflow
from common import Invalid

TW = fixtures.SCRIPTS.parents[1] / 'tw.py'


class StartAccept(unittest.TestCase):
    base = test_delivery.DeliveryCases
    setUp, git, check, setup_task, write, name = (base.setUp, base.git, base.check,
                                               base.setup_task, base.write, base.name)

    def setup_task(self, *args, **kwargs):
        return test_delivery.DeliveryCases.setup_task(self, *args, ready_scenarios=False, **kwargs)

    def command(self, *args):
        result = subprocess.run([sys.executable, str(TW), '--root', str(self.root), 'team', *args],
                                text=True, capture_output=True)
        return result.returncode, json.loads(result.stdout)

    def start(self, *extra):
        return self.command('start', '--task', self.name('task'), *extra)

    def contexts(self):
        return sorted((self.root / '.tw/local/tasks').glob('*/requests/*/context.json'))

    def test_first_simple_start_creates_context_and_points_to_run(self):
        self.setup_task()
        code, result = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, result)
        self.assertIs(result['continued'], False)
        self.assertEqual(result['task_id'], self.task['id'])
        self.assertEqual(result['context'], result['artifact'])
        self.assertEqual(result['task_directory'], str(self.contexts()[0].parent.parent.parent.relative_to(self.root)))
        self.assertTrue(result['implementation_ready'])
        self.assertEqual(result['gaps'], [])
        self.assertEqual(result['next_step']['id'], 'run')
        self.assertIn('tw team run', result['next_step']['next_command'])
        self.assertIn(self.task['id'], result['next_step']['next_command'])
        self.assertIn('--task ' + self.task['id'], result['next_step']['next_command'])

    def test_same_start_continues_without_another_context(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        contexts = self.contexts()
        code, again = self.start()
        self.assertEqual(code, 0, again)
        self.assertTrue(again['continued'])
        self.assertEqual(again['task_directory'], first['task_directory'])
        self.assertEqual(again['context'], first['context'])
        self.assertEqual(self.contexts(), contexts)
        self.assertNotEqual(again['brief']['path'], first['brief']['path'])
        self.assertTrue(again['brief']['path'].startswith(again['request_directory'] + '/'))
        self.assertEqual(again['next_step']['id'], 'run')
        code, status = self.command('status', '--context', again['context']['path'])
        self.assertEqual(code, 0, status)
        prepared = next(row for row in status['steps'] if row['id'] == 'prepare')
        self.assertEqual((prepared['state'], prepared['evidence']), ('done', first['context']['path']))
        self.assertEqual(status['next_step']['id'], 'run')
        self.assertIn('tw team run', status['next_step']['next_command'])

    def test_new_design_start_supersedes_the_previous_context(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        revised = copy.deepcopy(self.design)
        revised['revision'] = 2
        revised['sections'][-1]['body'] = 'Implement and document addition'
        self.write('design-2', revised)
        code, changed = self.start('--design', self.name('design-2'), '--design-history', self.name('design'))
        self.assertEqual(code, 0, changed)
        self.assertFalse(changed['continued'])
        self.assertEqual(changed['superseded_context'], first['context'])
        self.assertNotEqual(changed['context'], first['context'])
        self.assertEqual(changed['task_directory'], first['task_directory'])
        self.assertEqual(len(self.contexts()), 2)

    def test_changed_task_starts_a_new_context(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        self.task['non_goals'] = ['Multiplication']
        self.write('task', self.task)
        code, changed = self.start()
        self.assertEqual(code, 0, changed)
        self.assertFalse(changed['continued'])
        self.assertEqual(changed['superseded_context'], first['context'])
        self.assertEqual(read(self.root / changed['task']['path']), self.task)

    def test_task_identity_can_continue_and_resolve_acceptance_context(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        code, again = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, again)
        self.assertTrue(again['continued'])
        self.assertEqual(again['context'], first['context'])
        code, refused = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['error_code'], 'review-not-submitted')
        self.assertIn('tw team run', refused['next_action'])

    def test_id_only_acceptance_is_saved_and_bound_as_the_completed_task(self):
        self.setup_task()
        original = copy.deepcopy(self.task)
        self.task['acceptance'] = [{'id': 'A1'}]
        self.write('task', self.task)
        code, result = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, result)
        completed = read(self.root / result['task']['path'])
        self.assertEqual(completed, original)
        context = read(self.root / result['context']['path'])
        brief = read(self.root / context['brief']['path'])
        self.assertEqual(brief['task_digest'], digest(original))
        claim = read(self.root / result['request_directory'] / 'request.json')
        self.assertEqual(claim['task_digest'], digest(original))
        code, again = self.start()
        self.assertEqual(code, 0, again)
        self.assertTrue(again['continued'])
        self.assertEqual(again['context'], result['context'])
        self.assertEqual(read(self.root / self.name('task'))['acceptance'], [{'id': 'A1'}])

    def test_partial_acceptance_text_is_rejected_even_when_it_matches_the_design(self):
        self.setup_task()
        for missing in ('expectation', 'checks'):
            task = copy.deepcopy(self.task)
            task['acceptance'][0].pop(missing)
            write(self.root / self.name('task'), task)
            with self.subTest(missing=missing):
                code, result = self.start('--design', self.name('design'))
                self.assertEqual(code, 1, result)
                self.assertIn('验收项只写编号，内容以方案为准', result['problem'])

    def test_acceptance_text_is_refused_with_ids_only_hint(self):
        self.setup_task()
        self.task['acceptance'][0]['expectation'] = 'A different expectation'
        write(self.root / self.name('task'), self.task)
        code, result = self.start('--design', self.name('design'))
        self.assertEqual(code, 1, result)
        self.assertIn('验收项只写编号，内容以方案为准', result['problem'])

    def test_help_exposes_start_accept_and_rejects_removed_commands_and_phase(self):
        result = subprocess.run([sys.executable, str(TW), 'team', '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(?m)^\s+start\s+')
        self.assertRegex(result.stdout, r'(?m)^\s+accept\s+')
        self.assertNotRegex(result.stdout, r'\b(?:prepare|resume)\b')
        for args in (['prepare'], ['resume'], ['verify', '--phase', 'acceptance']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(TW), 'team', *args], text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)

    def acceptance_materials(self):
        code, started = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, started)
        context = started['context']['path']
        code, ran = self.command('run', '--context', context)
        self.assertEqual(code, 0, ran)
        ref = ran['artifact']
        self.write('approval-new', designs.approval_draft(self.design, 'carol', 'Approved actual execution',
                   code_digest=validation.source_digest(self.root, self.profile), run_refs=[ref]))
        plans.submit_scenarios(self.root, self.task)
        code, drafted = self.command('review', '--context', context, '--run', ref['path'])
        self.assertEqual(code, 0, drafted)
        review = read(self.root / drafted['binding']['path'])['template']
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read actual command and exact assertion', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Actual addition returned 3',
                                 'evidence': [ref], 'observations': plans.observations(self.root, ref)}]
        self.write('review-new', review)
        return context, ref

    def test_accept_builds_report_and_preserves_the_original_verification(self):
        self.setup_task()
        context, ref = self.acceptance_materials()
        code, accepted = self.command('accept', '--context', context, '--run', ref['path'],
                                      '--review', self.name('review-new'), '--approval', self.name('approval-new'))
        self.assertEqual(code, 0, accepted)
        self.assertTrue(accepted['business_accepted'])
        self.assertFalse(accepted['delivery_complete'])
        self.assertIn('summary_markdown', accepted)
        record = read(self.root / accepted['artifact']['path'])
        self.assertEqual(record['kind'], 'acceptance')
        self.assertEqual(record['report']['runs'], [ref['path']])
        expected = delivery.verify(self.root, self.profile, self.task, record['report'], 'acceptance')
        for key in ('business_accepted', 'checks', 'sections', 'observations', 'materials', 'task_digest'):
            self.assertEqual(record[key], expected[key], key)
        code, status = self.command('status', '--context', context)
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'acceptance')['state'], 'done')
        self.assertEqual(status['next_step']['id'], 'knowledge')

    def test_accept_rejects_the_implementer_and_status_points_to_an_independent_review(self):
        self.setup_task()
        context, ref = self.acceptance_materials()
        review = read(self.root / self.name('review-new'))
        review['reviewer'] = 'bob'
        self.write('review-new', review)
        code, refused = self.command('accept', '--context', context, '--run', ref['path'],
                                     '--review', self.name('review-new'), '--approval', self.name('approval-new'))
        self.assertEqual(code, 1, refused)
        self.assertIn('Reviewer must not be the implementation owner: bob', refused['problem'])
        code, status = self.command('status', '--context', context)
        self.assertEqual(code, 0, status)
        self.assertEqual(status['next_step']['id'], 'acceptance')
        # Rerunning accept with the same review would fail again; the step shows the repair from that refusal.
        self.assertIn('未参与实施的人', status['next_step']['next_command'])
        self.assertIn('tw team review', status['next_step']['next_command'])
        self.assertNotIn('--phase', status['next_step']['next_command'])

    def test_new_context_restarts_steps_after_an_earlier_acceptance(self):
        self.setup_task()
        context, ref = self.acceptance_materials()
        code, accepted = self.command('accept', '--context', context, '--run', ref['path'],
                                      '--review', self.name('review-new'), '--approval', self.name('approval-new'))
        self.assertEqual(code, 0, accepted)
        revised = copy.deepcopy(self.design)
        revised['revision'] = 2
        revised['sections'][-1]['body'] = 'Addition with revised documentation'
        self.write('design-2', revised)
        code, changed = self.start('--design', self.name('design-2'), '--design-history', self.name('design'))
        self.assertEqual(code, 0, changed)
        self.assertFalse(changed['continued'])
        self.assertEqual(changed['next_step']['id'], 'run')
        self.assertEqual(next(row for row in changed['steps'] if row['id'] == 'acceptance')['state'], 'pending')

    def test_accept_task_file_refuses_explicit_changes_since_start(self):
        self.setup_task()
        context, ref = self.acceptance_materials()
        self.task['non_goals'] = ['A changed task version']
        self.write('task', self.task)
        code, refused = self.command('accept', '--task', self.name('task'), '--run', ref['path'],
                                     '--review', self.name('review-new'), '--approval', self.name('approval-new'))
        self.assertEqual(code, 1, refused)
        self.assertIn('start', refused['problem'])

    def test_accept_inherits_the_context_approval_when_no_new_approval_is_supplied(self):
        self.setup_task(complexity='medium')
        self.write('approval-design', designs.approval_draft(self.design, 'carol', 'Approved the design', mode='design'))
        code, started = self.start('--design', self.name('design'), '--approval', self.name('approval-design'))
        self.assertEqual(code, 0, started)
        context = started['context']['path']
        code, ran = self.command('run', '--context', context)
        self.assertEqual(code, 0, ran)
        plans.submit_scenarios(self.root, self.task)
        code, drafted = self.command('review', '--context', context, '--run', ran['artifact']['path'])
        self.assertEqual(code, 0, drafted)
        ref = ran['artifact']
        review = read(self.root / drafted['binding']['path'])['template']
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read command and exact result', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': '1 + 2 returned 3',
                                 'evidence': [ref], 'observations': plans.observations(self.root, ref)}]
        self.write('review-new', review)
        code, accepted = self.command('accept', '--task', self.task['id'], '--run', ref['path'],
                                      '--review', self.name('review-new'))
        self.assertEqual(code, 0, accepted)
        self.assertTrue(accepted['business_accepted'])
        record = read(self.root / accepted['artifact']['path'])
        self.assertEqual(record['report']['approvals'], [read(self.root / context)['approvals'][0]['path']])

    def test_accept_existing_report_can_use_task_identity(self):
        self.setup_task()
        context, ref = self.acceptance_materials()
        code, first = self.command('accept', '--context', context, '--run', ref['path'],
                                   '--review', self.name('review-new'), '--approval', self.name('approval-new'))
        self.assertEqual(code, 0, first)
        code, accepted = self.command('accept', '--task', self.task['id'],
                                      '--report', first['request_directory'] + '/report.json')
        self.assertEqual(code, 0, accepted)
        self.assertTrue(accepted['business_accepted'])

    def test_successful_continuation_supersedes_a_failed_start_without_new_preparation(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        original = copy.deepcopy(self.task)
        self.task['design_id'] = 'another-plan'
        self.write('task', self.task)
        code, failed = self.start()
        self.assertEqual(code, 1, failed)
        self.write('task', original)
        code, resumed = self.start()
        self.assertEqual(code, 0, resumed)
        self.assertTrue(resumed['continued'])
        self.assertEqual(resumed['context'], first['context'])
        self.assertEqual(len(self.contexts()), 1)
        self.assertEqual(resumed['next_step']['id'], 'run')
        code, status = self.command('status', '--context', first['context']['path'])
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'prepare')['state'], 'done')
        self.assertEqual(status['next_step']['id'], 'run')

    def test_start_rejects_a_context_from_another_task_identity(self):
        self.setup_task()
        code, first = self.start('--design', self.name('design'))
        self.assertEqual(code, 0, first)
        other = dict(self.task, id='TASK-other', parent=self.task['id'], acceptance_scope='task')
        self.write('other-task', plans.written_task(other))
        for task_arg in (self.name('other-task'), 'TASK-other'):
            with self.subTest(task=task_arg):
                code, refused = self.command('start', '--task', task_arg, '--context', first['context']['path'])
                self.assertEqual(code, 1, refused)
                self.assertIn('属于另一个任务', refused['problem'])
                self.assertEqual(len(self.contexts()), 1)


class StartPlatform(unittest.TestCase):
    base = test_coordination.CoordinationCases
    setUp, git, check, prepare, body, github, publish_fixture, establish_design, handoff = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github,
        base.publish_fixture, base.establish_design, base.handoff)

    def command(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main([*(args or ('start', '--issue', self.url)), '--root', str(self.root)])
        return code, json.loads(output.getvalue())

    def prepared_platform(self, with_handoff=True, owners=None, approved=True):
        self.prepare()
        if owners is not None:
            self.issue['assignees'] = [{'login': owner} for owner in owners]
        fixtures.write_config(self.root, self.profile)
        self.git('add', '.tw/config.json')
        self.git('commit', '-qm', 'share the platform check configuration')
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            self.establish_design(approved=approved)
            if with_handoff:
                self.publish_fixture(coordination.draft(self.root, self.profile, self.url, self.handoff(), kind='design'), 'alice')
            code, first = self.command()
        self.assertEqual(code, 0, first)
        self.assertFalse(first['continued'])
        return first

    def test_platform_continuation_keeps_handoff_and_source_checks(self):
        first = self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, resumed = self.command()
            self.assertEqual(code, 0, resumed)
            self.assertTrue(resumed['continued'])
            self.assertTrue(resumed['ready_to_implement'])
            self.assertEqual(resumed['context'], first['context'])
            (self.root / 'app.py').write_text('def add(a, b): return 0\n')
            code, refused = self.command()
        self.assertEqual(code, 1, refused)
        self.assertTrue(refused['continued'])
        self.assertIn('Source content changed', str(refused['gaps']))
        self.assertEqual(len(list((self.root / '.tw/local/tasks').glob('*/requests/*/context.json'))), 1)

    def test_platform_read_failure_is_a_continuation_gap_with_a_saved_brief(self):
        first = self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=Invalid('offline fixture')):
            code, refused = self.command()
        self.assertEqual(code, 1, refused)
        self.assertTrue(refused['continued'])
        self.assertEqual(refused['context'], first['context'])
        self.assertFalse(refused['implementation_ready'])
        self.assertIn('offline fixture', str(refused['gaps']))
        self.assertTrue((self.root / refused['brief']['path']).is_file())

    def test_platform_continuation_without_handoff_or_owner_keeps_prepare_done(self):
        first = self.prepared_platform(with_handoff=False, owners=[])
        self.assertEqual(first['gaps'], [])
        self.assertEqual(next(row for row in first['steps'] if row['id'] == 'prepare')['state'], 'done')
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, resumed = self.command()
            self.assertEqual(code, 0, resumed)
            self.assertTrue(resumed['continued'])
            self.assertTrue(resumed['ready_to_implement'])
            self.assertEqual(resumed['gaps'], [])
            self.assertEqual(resumed['context'], first['context'])
            self.assertEqual(next(row for row in resumed['steps'] if row['id'] == 'prepare')['state'], 'done')
            code, status = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row for row in status['steps'] if row['id'] == 'prepare')['state'], 'done')
        self.assertEqual(status['next_step']['id'], 'run')
        self.assertNotIn('tw team start', status['next_step']['next_command'])

    def test_platform_continuation_without_handoff_keeps_unconfirmed_progress_gap(self):
        self.prepared_platform(with_handoff=False, owners=[])
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            self.publish_fixture(coordination.progress_draft(self.root, self.profile, self.url,
                {'author': 'bob', 'done': ['Read the implementation'], 'verified': [],
                 'remaining': ['Confirm the result'], 'questions': []}, 'pending-progress'), 'bob')
            code, result = self.command()
        self.assertEqual(code, 1, result)
        self.assertTrue(result['continued'])
        self.assertEqual(result['gaps'], ['New progress has not been confirmed in the current handoff'])
        self.assertFalse(result['ready_to_implement'])

    def test_platform_continuation_without_handoff_keeps_active_validation_gap(self):
        self.prepared_platform(with_handoff=False, owners=[])
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            with validation_session.session(self.root, self.profile, [self.task]):
                code, result = self.command()
        self.assertEqual(code, 1, result)
        self.assertTrue(result['continued'])
        self.assertEqual(result['gaps'], ['Validation is active; keep the shared workspace unchanged'])
        self.assertFalse(result['ready_to_implement'])

    def test_platform_continuation_without_handoff_keeps_platform_change_gap(self):
        self.prepared_platform(with_handoff=False, owners=[])
        read_fixture = platform_transport(self.github)
        reads = 0

        def changing_platform(root, operation, *arguments):
            nonlocal reads
            if operation == 'task':
                reads += 1
                self.issue['assignees'] = [{'login': 'owner-' + str(reads)}]
            return read_fixture(root, operation, *arguments)

        with patch.object(platform_read, 'call', side_effect=changing_platform):
            code, result = self.command()
        self.assertEqual(code, 1, result)
        self.assertTrue(result['continued'])
        self.assertIn('Platform changed while reading; refresh requirements, responsibilities and progress', result['gaps'])
        self.assertFalse(result['ready_to_implement'])

    def test_platform_continuation_without_handoff_keeps_approval_and_scope_gaps(self):
        self.prepared_platform(with_handoff=False, owners=[], approved=False)
        (self.root / 'outside.py').write_text('unmapped = True\n')
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, result = self.command()
        self.assertEqual(code, 1, result)
        self.assertTrue(result['continued'])
        self.assertIn('Selected task sections are not ready for implementation; resolve approval, decisions or assignment',
                      result['gaps'])
        self.assertIn('Changed source paths cannot all be assigned to declared design task scopes', result['gaps'])
        self.assertFalse(result['ready_to_implement'])

    def test_platform_acceptance_ids_expand_from_the_published_design(self):
        self.prepared_platform()
        self.task['acceptance'] = [{'id': 'A1'}]
        self.issue['body'] = self.body()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, result = self.command()
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / result['task']['path'])['acceptance'],
                         [{'id': 'A1', 'expectation': '1 + 2 is 3', 'checks': ['unit']}])


if __name__ == '__main__':
    unittest.main()
