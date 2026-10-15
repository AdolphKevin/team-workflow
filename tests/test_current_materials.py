"""T7 A3: recorded material groups through real CLI calls, Git and concurrent processes."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_start_accept
import test_unified_team
import plan_fixtures as plans
from common import artifact, artifact_valid, read, write
import artifacts
import cleanup
import coordination
import designs
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport
import workflow

TW = test_start_accept.TW


class CurrentMaterials(unittest.TestCase):
    base = test_start_accept.StartAccept
    setUp, git, check, setup_task, write, name, command = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.command)
    rule = test_unified_team.UnifiedTeam.rule

    def current_path(self):
        return artifacts.directory(self.root, self.task['id']).parent.parent / 'current.json'

    def current(self):
        return read(self.current_path())

    def prepared(self):
        self.setup_task(complexity='medium')
        approval = designs.approval_draft(self.design, 'carol', 'Approved the specified design', mode='design')
        self.write('approval-design', approval)
        code, result = self.command('start', '--task', self.name('task'), '--design', self.name('design'),
                                    '--approval', self.name('approval-design'))
        self.assertEqual(code, 0, result)
        return result

    def run_identity(self, *extra):
        code, result = self.command('run', '--task', self.task['id'], *extra)
        self.assertEqual(code, 0, result)
        return result

    def reviewed(self):
        started = self.prepared()
        ran = self.run_identity()
        code, draft = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, draft)
        review = read(self.root / draft['binding']['path'])['template']
        ref = ran['artifact']
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read public behavior and exact assertion output', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Actual addition returned 3',
                                 'evidence': [ref], 'observations': [plans.observation(ref)]}]
        self.write('review-current', review)
        return started, ran, review

    def accepted(self):
        started, ran, review = self.reviewed()
        code, result = self.command('accept', '--task', self.task['id'], '--review', self.name('review-current'))
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'])
        return started, ran, review, result

    def test_start_records_a_complete_content_bound_group_and_continuation_keeps_it(self):
        started = self.prepared()
        group = self.current()
        self.assertEqual((group['data_version'], group['kind'], group['task_id']),
                         (1, 'current-materials', self.task['id']))
        context = read(self.root / started['context']['path'])
        self.assertEqual(group['context'], started['context'])
        for key in ('task', 'design', 'brief', 'approvals', 'design_history'):
            self.assertEqual(group[key], context[key], key)
        for key in ('context', 'task', 'design', 'brief'):
            artifact_valid(self.root, group[key])
        self.assertEqual(group['runs'], [])
        self.assertTrue(all(group[key] is None for key in ('review', 'acceptance', 'delivery_report', 'delivery')))
        before = self.current_path().read_bytes()
        code, resumed = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, resumed)
        self.assertTrue(resumed['continued'])
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_identity_flow_records_execution_acceptance_report_and_final_delivery(self):
        started, ran, _, accepted = self.accepted()
        group = self.current()
        self.assertEqual(group['runs'], [ran['artifact']])
        self.assertEqual(group['review'], artifact(self.root, self.root / self.name('review-current')))
        self.assertEqual(group['acceptance'], accepted['artifact'])
        self.rule()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        report = read(self.root / drafted['artifact']['path'])
        self.assertEqual(report['acceptance'], accepted['artifact']['path'])
        self.assertEqual(report['runs'], [ran['artifact']['path']])
        self.assertEqual(self.current()['delivery_report'], drafted['artifact'])
        code, delivered = self.command('verify', '--task', self.task['id'])
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'])
        self.assertEqual(self.current()['delivery'], delivered['artifact'])
        group = self.current_path().read_bytes()
        code, resumed = self.command('start', '--task', self.task['id'])
        self.assertEqual(code, 0, resumed)
        self.assertTrue(resumed['continued'])
        self.assertEqual(resumed['context'], started['context'])
        self.assertIsNone(resumed['next_step'])
        self.assertEqual(self.current_path().read_bytes(), group)

    def test_all_identity_commands_resolve_the_task_instead_of_reading_id_as_a_path(self):
        self.prepared()
        self.run_identity()
        self.write('approval-input', {'reviewer': 'carol', 'confirmation': 'Reviewed design and source'})
        for command, options in [('status', []), ('task-export', []),
                                 ('approval-draft', ['--record', self.name('approval-input')]),
                                 ('review', []), ('delivery-template', [])]:
            with self.subTest(command=command):
                code, result = self.command(command, '--task', self.task['id'], *options)
                self.assertEqual(code, 0, result)
                self.assertNotIn('Missing path: ' + self.task['id'], str(result))

    def test_templates_and_approval_drafts_do_not_register_their_outputs(self):
        self.prepared()
        self.run_identity()
        before = self.current_path().read_bytes()
        self.write('approval-input', {'reviewer': 'carol', 'confirmation': 'Reviewed the selected code'})
        for command, options in [('review', []), ('approval-draft', ['--record', self.name('approval-input')])]:
            code, result = self.command(command, '--task', self.task['id'], *options)
            self.assertEqual(code, 0, result)
            self.assertEqual(self.current_path().read_bytes(), before)

    def test_failed_execution_is_appended_but_failed_acceptance_does_not_replace_materials(self):
        _, _, review, _ = self.accepted()
        review['reviewer'] = 'bob'
        self.write('bad-review', review)
        before = self.current_path().read_bytes()
        code, refused = self.command('accept', '--task', self.task['id'], '--review', self.name('bad-review'))
        self.assertEqual(code, 1, refused)
        self.assertEqual(self.current_path().read_bytes(), before)
        self.check("raise SystemExit('deliberate failed check')")
        import test_workflow
        test_workflow.write_config(self.root, self.profile)
        code, failed = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 1, failed)
        self.assertEqual(self.current()['runs'][-1], failed['artifact'])
        self.assertEqual(len(self.current()['runs']), 2)

    def test_changed_or_missing_recorded_material_names_its_role_and_recovery_command(self):
        self.prepared()
        self.run_identity()
        group = self.current()
        for role, ref in [('context', group['context']), ('task', group['task']), ('design', group['design']),
                          ('brief', group['brief']), ('approvals', group['approvals'][0]), ('runs', group['runs'][0])]:
            path = self.root / ref['path']
            original = path.read_bytes()
            for change in ('changed', 'missing'):
                with self.subTest(role=role, change=change):
                    if change == 'changed': path.write_bytes(original + b'\n')
                    else: path.unlink()
                    code, refused = self.command('status', '--task', self.task['id'])
                    self.assertEqual(code, 1, refused)
                    self.assertIn(role, refused['problem'])
                    self.assertIn('start', refused['next_action'])
                    path.write_bytes(original)

    def test_identity_without_a_record_is_rejected_with_start_instructions(self):
        self.setup_task()
        for command in ('run', 'status', 'review', 'approval-draft', 'accept', 'delivery-template',
                        'verify', 'handoff', 'progress', 'task-export'):
            with self.subTest(command=command):
                code, refused = self.command(command, '--task', self.task['id'])
                self.assertEqual(code, 1, refused)
                self.assertIn('current', refused['problem'])
                self.assertIn('start', refused['next_action'])

    def test_explicit_review_and_approval_replace_the_record_after_success(self):
        _, _, review, _ = self.accepted()
        approval = designs.approval_draft(self.design, 'carol', 'Confirmed again against the same design', mode='design')
        self.write('approval-replacement', approval)
        review['standards']['summary'] = 'Independently reread standards and exact evidence'
        self.write('review-replacement', review)
        # An explicit replacement can repair a changed recorded material without trusting its old fingerprint.
        (self.root / self.name('review-current')).write_text('{}\n')
        code, result = self.command('accept', '--task', self.task['id'], '--review', self.name('review-replacement'),
                                    '--approval', self.name('approval-replacement'))
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['review'], artifact(self.root, self.root / self.name('review-replacement')))
        self.assertEqual(self.current()['approvals'], [artifact(self.root, self.root / self.name('approval-replacement'))])
        self.assertEqual(self.current()['acceptance'], result['artifact'])

    def test_new_context_resets_the_entire_group(self):
        old, _, _, _ = self.accepted()
        self.command('delivery-template', '--task', self.task['id'])
        self.task['non_goals'] = ['Multiplication']
        self.write('task', self.task)
        code, result = self.command('start', '--task', self.name('task'))
        self.assertEqual(code, 0, result)
        self.assertFalse(result['continued'])
        group = self.current()
        self.assertNotEqual(group['context'], old['context'])
        self.assertEqual(group['context'], result['context'])
        self.assertEqual(group['runs'], [])
        self.assertTrue(all(group[key] is None for key in ('review', 'acceptance', 'delivery_report', 'delivery')))

    def test_request_fingerprint_includes_automatically_selected_runs(self):
        self.prepared()
        self.run_identity()
        args = ('review', '--task', self.task['id'], '--request-id', 'selected-materials')
        code, first = self.command(*args)
        self.assertEqual(code, 0, first)
        before = (self.root / first['artifact']['path']).read_bytes()
        self.run_identity()
        code, refused = self.command(*args)
        self.assertEqual(code, 1, refused)
        self.assertIn('Request ID already belongs to different inputs', refused['problem'])
        self.assertEqual((self.root / first['artifact']['path']).read_bytes(), before)

    def test_run_retry_does_not_append_the_same_execution_twice(self):
        self.prepared()
        args = ('run', '--task', self.task['id'], '--request-id', 'run-retry')
        code, first = self.command(*args)
        self.assertEqual(code, 0, first)
        code, again = self.command(*args)
        self.assertEqual((code, again), (0, first))
        self.assertEqual(self.current()['runs'], [first['artifact']])

    def test_concurrent_starts_publish_one_consistent_group_or_explicitly_refuse_one(self):
        self.setup_task()
        args = [sys.executable, str(TW), '--root', str(self.root), 'team', 'start',
                '--task', self.name('task'), '--design', self.name('design')]
        processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        while any(p.poll() is None for p in processes):
            if self.current_path().exists():
                value = self.current()
                self.assertEqual(value['kind'], 'current-materials')
            time.sleep(0.01)
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertFalse(stderr, stderr)
            results.append(json.loads(stdout))
        self.assertTrue(any(row['ok'] for row in results), results)
        successes = [row for row in results if row['ok']]
        if len(successes) == 2:
            self.assertEqual(successes[0]['context'], successes[1]['context'])
        else:
            self.assertRegex(next(row for row in results if not row['ok'])['problem'], '另一个 start|并发')
        group = self.current()
        self.assertIn(group['context'], [row['context'] for row in successes])
        for key in ('context', 'task', 'design', 'brief'):
            artifact_valid(self.root, group[key])

    def test_cleanup_keeps_materials_referenced_only_by_the_current_group(self):
        self.prepared()
        ran = self.run_identity()
        path = self.root / '.tw/local/batches/current-only/run.json'
        path.parent.mkdir(parents=True)
        path.write_bytes((self.root / ran['artifact']['path']).read_bytes())
        group = self.current()
        group['runs'].append(artifact(self.root, path))
        write(self.current_path(), group)
        plan = cleanup.preview(self.root, 'all', 0)
        self.assertTrue(plan['ok'], plan)
        self.assertNotIn(str(path.parent.relative_to(self.root)), plan['candidates'])
        self.assertIn(str(path.parent.relative_to(self.root)), plan['protected'])
        cleanup.apply(self.root, plan)
        self.assertTrue(path.is_file())

    def test_status_records_explicit_materials_only_after_success(self):
        self.prepared()
        ran = self.run_identity()
        self.write('design-copy', self.design)
        before = self.current_path().read_bytes()
        code, result = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current_path().read_bytes(), before)
        code, result = self.command('status', '--task', self.task['id'], '--design', self.name('design-copy'),
                                    '--run', ran['artifact']['path'])
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['design'], artifact(self.root, self.root / self.name('design-copy')))
        before = self.current_path().read_bytes()
        self.write('bad-design', dict(self.design, id='another-plan'))
        code, refused = self.command('status', '--task', self.task['id'], '--design', self.name('bad-design'))
        self.assertEqual(code, 1, refused)
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_explicit_context_switches_the_whole_group_without_mixing_runs(self):
        first = self.prepared()
        old_run = self.run_identity()
        self.task['non_goals'] = ['Second task version']
        self.write('task', self.task)
        code, newer = self.command('start', '--task', self.name('task'))
        self.assertEqual(code, 0, newer)
        new_run = self.run_identity()
        code, selected = self.command('run', '--task', self.task['id'], '--context', first['context']['path'])
        self.assertEqual(code, 0, selected)
        group = self.current()
        self.assertEqual(group['context'], first['context'])
        old = read(self.root / first['context']['path'])
        self.assertEqual(group['task'], old['task'])
        self.assertEqual(group['design'], old['design'])
        self.assertEqual(group['runs'], [selected['artifact']])
        self.assertNotIn(old_run['artifact'], group['runs'])
        self.assertNotIn(new_run['artifact'], group['runs'])

    def test_explicit_delivery_report_records_the_materials_actually_verified(self):
        _, ran, _, accepted = self.accepted()
        self.rule()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        report = read(self.root / drafted['artifact']['path'])
        copied = self.root / '.tw/local/run-copy.json'
        copied.write_bytes((self.root / ran['artifact']['path']).read_bytes())
        report['runs'] = [str(copied.relative_to(self.root))]
        # Identical execution content at another path is already supported by the verifier.
        review = read(self.root / self.name('review-current'))
        ref = artifact(self.root, copied)
        for axis in ('standards', 'spec'):
            review[axis]['evidence'] = [ref]
        review['acceptance'][0].update(evidence=[ref], observations=[plans.observation(ref)])
        self.write('review-copy', review)
        report['review'] = self.name('review-copy')
        self.write('report-copy', report)
        code, accepted_copy = self.command('accept', '--task', self.task['id'], '--report', self.name('report-copy'))
        self.assertEqual(code, 0, accepted_copy)
        acceptance_copy = self.root / self.name('acceptance-copy')
        acceptance_copy.write_bytes((self.root / accepted_copy['artifact']['path']).read_bytes())
        report['acceptance'] = self.name('acceptance-copy')
        self.write('report-copy-final', report)
        code, delivered = self.command('verify', '--task', self.task['id'], '--report', self.name('report-copy-final'))
        self.assertEqual(code, 0, delivered)
        group = self.current()
        self.assertEqual(group['acceptance'], artifact(self.root, acceptance_copy))
        self.assertEqual(group['runs'], [ran['artifact'], ref])
        self.assertEqual(group['selected_runs'], [ref])
        self.assertEqual(group['review'], artifact(self.root, self.root / self.name('review-copy')))
        self.assertEqual(group['delivery_report'], artifact(self.root, self.root / self.name('report-copy-final')))
        code, again = self.command('verify', '--task', self.task['id'])
        self.assertEqual(code, 0, again)

    def test_explicit_run_selection_keeps_failed_execution_history(self):
        self.prepared()
        self.check("from pathlib import Path; import app; assert not Path('.tw/local/fail-check').exists(); assert app.add(1,2)==3")
        import test_workflow
        test_workflow.write_config(self.root, self.profile)
        passed = self.run_identity()
        code, draft = self.command('review', '--task', self.task['id'])
        self.assertEqual(code, 0, draft)
        review = read(self.root / draft['binding']['path'])['template']
        ref = passed['artifact']
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read exact execution output', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': '1+2 returned 3',
                                 'evidence': [ref], 'observations': [plans.observation(ref)]}]
        self.write('review-selected', review)
        marker = self.root / '.tw/local/fail-check'
        marker.touch()
        code, failed = self.command('run', '--task', self.task['id'])
        marker.unlink()
        self.assertEqual(code, 1, failed)
        code, automatic = self.command('accept', '--task', self.task['id'], '--review', self.name('review-selected'))
        self.assertEqual(code, 0, automatic)
        proof = read(self.root / automatic['artifact']['path'])
        # The existing contract chooses a current passing result and retains failed candidates as superseded.
        self.assertIn(failed['artifact']['path'], [row['path'] for row in proof['superseded_execution']])
        code, accepted = self.command('accept', '--task', self.task['id'], '--run', ref['path'],
                                      '--review', self.name('review-selected'))
        self.assertEqual(code, 0, accepted)
        group = self.current()
        self.assertEqual(group['runs'], [ref, failed['artifact']])
        self.assertEqual(group['selected_runs'], [ref])

    def test_concurrent_runs_append_both_results_without_lost_updates(self):
        self.prepared()
        args = [sys.executable, str(TW), '--root', str(self.root), 'team', 'run', '--task', self.task['id']]
        processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertFalse(stderr, stderr)
            result = json.loads(stdout)
            self.assertEqual(process.returncode, 0, result)
            results.append(result)
        self.assertCountEqual(self.current()['runs'], [row['artifact'] for row in results])

    def test_verify_retry_rejects_a_different_automatically_selected_group(self):
        self.accepted()
        self.rule()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        args = ('verify', '--task', self.task['id'], '--request-id', 'verify-materials')
        code, delivered = self.command(*args)
        self.assertEqual(code, 0, delivered)
        code, again = self.command(*args)
        self.assertEqual((code, again), (0, delivered))
        self.run_identity()
        code, refused = self.command(*args)
        self.assertEqual(code, 1, refused)
        self.assertIn('Request ID already belongs to different inputs', refused['problem'])
        code, stale_report = self.command('verify', '--task', self.task['id'])
        self.assertEqual(code, 1, stale_report)
        self.assertIn('delivery_report', stale_report['problem'])

    def test_identity_status_next_commands_keep_using_the_identity(self):
        self.prepared()
        code, status = self.command('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        for row in status['steps']:
            self.assertIn('--task ' + self.task['id'], row['next_command'])
            self.assertNotIn('--context', row['next_command'])
        self.assertEqual(status['next_step']['id'], 'run')

    def test_explicit_status_design_is_checked_even_when_a_report_is_recorded(self):
        self.accepted()
        code, drafted = self.command('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, drafted)
        before = self.current_path().read_bytes()
        self.write('wrong-design', dict(self.design, id='another-plan'))
        code, refused = self.command('status', '--task', self.task['id'], '--design', self.name('wrong-design'))
        self.assertEqual(code, 1, refused)
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_explicit_review_overrides_the_review_inside_an_existing_report(self):
        _, _, review, accepted = self.accepted()
        self.write('existing-report', read(self.root / accepted['artifact']['path'])['report'])
        review['reviewer'] = 'bob'
        self.write('self-review', review)
        before = self.current_path().read_bytes()
        code, refused = self.command('accept', '--task', self.task['id'], '--report', self.name('existing-report'),
                                     '--review', self.name('self-review'))
        self.assertEqual(code, 1, refused)
        self.assertIn('Reviewer must not be the implementation owner: bob', refused['problem'])
        self.assertEqual(self.current_path().read_bytes(), before)

    def test_task_identity_is_preserved_without_path_normalization(self):
        self.task['id'] = 'TASK//exact identity'
        self.prepared()
        code, result = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertEqual(self.current()['task_id'], 'TASK//exact identity')


class PlatformCurrentMaterials(unittest.TestCase):
    base = test_start_accept.StartPlatform
    setUp, git, check, prepare, body, github, publish_fixture, establish_design, handoff, prepared_platform = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github, base.publish_fixture,
        base.establish_design, base.handoff, base.prepared_platform)
    command = base.command

    def identity_command(self, command, *options):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main([command, '--root', str(self.root), '--task', self.url, *options])
        return code, json.loads(output.getvalue())

    def test_issue_address_as_identity_preserves_the_complete_url(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            code, result = self.identity_command('task-export')
        self.assertEqual(code, 0, result)
        self.assertEqual(read(self.root / result['artifact']['path'])['id'], self.url)

    def test_platform_design_newer_than_the_record_requires_start(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][-1]['body'] = 'Updated implementation instructions'
            self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
            code, refused = self.identity_command('status')
        self.assertEqual(code, 0, refused)
        self.assertIn('design', refused['stale_materials'])
        self.assertEqual(next(row for row in refused['steps'] if row['id'] == 'prepare')['state'], 'stale')
        self.assertIn('start', refused['next_action'])

    def test_platform_approval_newer_than_the_record_requires_start(self):
        self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            self.publish_fixture(coordination.draft_approval(self.url,
                {'reviewer': 'carol', 'confirmation': 'New explicit approval'}), 'carol')
            code, refused = self.identity_command('task-export')
        self.assertEqual(code, 1, refused)
        self.assertIn('approvals', refused['problem'])
        self.assertIn('start', refused['next_action'])

    def test_explicit_old_platform_context_cannot_bypass_the_current_design(self):
        first = self.prepared_platform()
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][-1]['body'] = 'New approved implementation instructions'
            self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
            self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol',
                'confirmation': 'Approved the new version'}), 'carol')
            code, current = self.command()
            self.assertEqual(code, 0, current)
            target = artifacts.directory(self.root, self.url).parent.parent / 'current.json'
            before = target.read_bytes()
            code, refused = self.identity_command('run', '--context', first['context']['path'])
        self.assertEqual(code, 1, refused)
        self.assertIn('design', refused['problem'])
        self.assertEqual(target.read_bytes(), before)

    def test_explicit_old_platform_design_or_approval_cannot_replace_the_current_group(self):
        first = self.prepared_platform()
        old_context = read(self.root / first['context']['path'])
        old_source = plans.write_design(self.root / '.tw/local/old-design.md', read(self.root / old_context['design']['path']))
        with patch.object(platform_read, 'call', side_effect=platform_transport(self.github)):
            revised = copy.deepcopy(self.design)
            revised['revision'] = 2
            revised['sections'][-1]['body'] = 'New approved implementation instructions'
            self.publish_fixture(plans.draft_design(self.root, self.url, revised), 'alice')
            self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol',
                'confirmation': 'Approved the new version'}), 'carol')
            code, current = self.command()
            self.assertEqual(code, 0, current)
            target = artifacts.directory(self.root, self.url).parent.parent / 'current.json'
            before = target.read_bytes()
            for command, option, value, role in [
                ('status', '--design', old_source.relative_to(self.root).as_posix(), 'design'),
                ('review', '--design', old_source.relative_to(self.root).as_posix(), 'design'),
                ('review', '--approval', old_context['approvals'][0]['path'], 'approvals')]:
                with self.subTest(command=command, option=option):
                    try:
                        code, refused = self.identity_command(command, option, value)
                        if command == 'status':
                            self.assertEqual(code, 0, refused)
                            self.assertIn(role, refused['stale_materials'])
                            self.assertEqual(next(row for row in refused['steps'] if row['id'] == 'prepare')['state'], 'stale')
                        else:
                            self.assertEqual(code, 1, refused)
                            self.assertIn(role, refused['problem'])
                        self.assertEqual(target.read_bytes(), before)
                    finally:
                        target.write_bytes(before)


if __name__ == '__main__':
    unittest.main()
