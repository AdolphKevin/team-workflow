"""Continuation and imported execution against real isolated Git workspaces."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import test_workflow as fixtures
from common import Invalid, artifact, digest, read, write
import execution
import github_read
import handoffs
import portable
import verification
import workflow


class ContinuationCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs
    run_check = fixtures.WorkflowCases.run_check
    complete = fixtures.WorkflowCases.complete

    def prepare(self):
        self.url = 'https://github.com/example/project/issues/1'
        self.task['id'] = self.url
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.issue = {'html_url': self.url, 'updated_at': '2026-01-01T00:00:00Z', 'assignees': [{'login': 'alice'}],
                      'body': self.body(), 'comments_data': [], 'state': 'open'}

    def body(self):
        return 'Existing MATT specification.\n\n```team-workflow-task\n' + json.dumps(
            {'schema_version': 3, 'parent': None, 'task': self.task}) + '\n```\n'

    def progress(self):
        return {'owner': 'alice', 'done': ['Implementation read'], 'verified': [], 'remaining': ['Acceptance execution'],
                'questions': [], 'next': 'Run the declared acceptance check.',
                'versions': [{'repository': 'example/project', 'commit': self.task['base']}], 'references': [],
                'participants': [], 'contracts': [], 'dependencies': [], 'joint_owner': ''}

    def comment(self, draft, number=1):
        return {'html_url': self.url + '#issuecomment-' + str(number), 'body': draft['markdown']}

    def github(self, endpoint, paginate=False, binary=False):
        if endpoint == 'repos/example/project/issues/1':
            return copy.deepcopy(self.issue)
        if endpoint.startswith('repos/example/project/issues/1/comments'):
            return copy.deepcopy(self.issue['comments_data'])
        if '/commits/' in endpoint:
            return {'sha': endpoint.rsplit('/', 1)[1]}
        raise Invalid('Fixture cannot resolve ' + endpoint)

    def test_draft_and_resume_do_not_publish_or_claim_delivery(self):
        self.prepare()
        skill = self.fake_cs()
        with patch.object(github_read, 'api', side_effect=self.github):
            draft = handoffs.draft(self.root, self.profile, self.url, self.progress(), skill)
            self.assertTrue(draft['ok'], draft)
            self.assertEqual(self.issue['comments_data'], [])
            self.issue['comments_data'].append(self.comment(draft))
            resumed = handoffs.resume(self.root, self.profile, self.url, skill)
        self.assertTrue(resumed['ok'], resumed)
        self.assertEqual(resumed['delivery'], 'not-evaluated')
        self.assertEqual(resumed['current']['next'], self.progress()['next'])

    def test_parallel_handoffs_are_not_resolved_by_latest_timestamp(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=self.github):
            draft = handoffs.draft(self.root, self.profile, self.url, self.progress(), self.fake_cs())
        self.issue['comments_data'] = [self.comment(draft, 1), self.comment(draft, 2)]
        latest, _, gaps = handoffs.chain(self.issue)
        self.assertIsNone(latest)
        self.assertTrue(any('Concurrent' in g for g in gaps))

    def test_edited_predecessor_and_changed_requirements_are_detected(self):
        self.prepare()
        skill = self.fake_cs()
        with patch.object(github_read, 'api', side_effect=self.github):
            first = handoffs.draft(self.root, self.profile, self.url, self.progress(), skill)
            self.issue['comments_data'] = [self.comment(first)]
            second = handoffs.draft(self.root, self.profile, self.url, self.progress(), skill)
            self.issue['comments_data'].append(self.comment(second, 2))
            self.assertTrue(handoffs.resume(self.root, self.profile, self.url, skill)['ok'])
            self.issue['body'] = self.body().replace('Addition works', 'Subtraction works')
            self.assertIn('Requirements changed', str(handoffs.resume(self.root, self.profile, self.url, skill)['gaps']))
        self.issue['comments_data'][0]['body'] = first['markdown'].replace('Implementation read', 'Edited history')
        self.assertIn('Missing or edited predecessor', str(handoffs.chain(self.issue)[2]))

    def test_explicit_reconciliation_keeps_history_and_detects_later_edits(self):
        self.prepare()
        skill = self.fake_cs()
        with patch.object(github_read, 'api', side_effect=self.github):
            first = handoffs.draft(self.root, self.profile, self.url, self.progress(), skill)
            self.issue['comments_data'] = [self.comment(first, 1), self.comment(first, 2)]
            resumed = handoffs.resume(self.root, self.profile, self.url, skill)
            with self.assertRaisesRegex(Invalid, 'explicit resolution'):
                handoffs.draft(self.root, self.profile, self.url, self.progress(), skill)
            progress = self.progress()
            progress['resolution'] = {'history_digest': resumed['history_digest'], 'reason': 'Read both branches; combine their verified work and retain pending acceptance.'}
            reconciled = handoffs.draft(self.root, self.profile, self.url, progress, skill)
            self.issue['comments_data'].append(self.comment(reconciled, 3))
            self.assertTrue(handoffs.resume(self.root, self.profile, self.url, skill)['ok'])
            self.assertEqual(len(self.issue['comments_data']), 3)
            self.issue['comments_data'][0]['body'] += 'Edited prior history.'
            self.assertFalse(handoffs.resume(self.root, self.profile, self.url, skill)['ok'])
            with self.assertRaisesRegex(Invalid, 'History changed'):
                handoffs.draft(self.root, self.profile, self.url, progress, skill)

    def test_unshared_work_and_missing_owner_block_cross_machine_handoff(self):
        self.prepare()
        self.issue['assignees'] = []
        (self.root / 'new.py').write_text('unshared = True\n')
        with patch.object(github_read, 'api', side_effect=self.github):
            draft = handoffs.draft(self.root, self.profile, self.url, self.progress(), self.fake_cs())
        self.assertFalse(draft['ok'])
        self.assertIn('Unshared working changes', str(draft['gaps']))
        self.assertIn('not assigned', str(draft['gaps']))

    def test_closed_dependency_without_delivery_evidence_is_not_ready(self):
        self.prepare()
        progress = self.progress()
        progress['dependencies'] = [{'issue': self.url, 'repository': 'example/project', 'commit': self.task['base'], 'evidence': ''}]
        self.issue['state'] = 'closed'
        with patch.object(github_read, 'api', side_effect=self.github):
            draft = handoffs.draft(self.root, self.profile, self.url, progress, self.fake_cs())
        self.assertIn('no delivery evidence', str(draft['gaps']))

    def test_progress_does_not_change_requirement_digest(self):
        self.prepare()
        original = digest(handoffs.task_source(self.issue))
        self.issue['assignees'] = [{'login': 'bob'}]
        self.issue['updated_at'] = '2026-02-01T00:00:00Z'
        self.assertEqual(original, digest(handoffs.task_source(self.issue)))
        self.issue['body'] += '\nChanged prose acceptance: another required behavior.\n'
        self.assertNotEqual(original, digest(handoffs.task_source(self.issue)))

    def test_immutable_file_references_and_missing_reports(self):
        self.prepare()
        with patch.object(github_read, 'api', side_effect=lambda endpoint, **kw: {'type': 'file'} if '/contents/' in endpoint else self.github(endpoint, **kw)):
            github_read.reachable('https://github.com/example/project/blob/' + self.task['base'] + '/app.py#L1')
            github_read.reachable('https://github.com/example/project/commit/' + self.task['base'])
            with self.assertRaises(Invalid):
                github_read.reachable('https://github.com/example/project/blob/main/app.py')
        self.check('print("report missing")', format='junit', report='{output}/absent.xml')
        path, record = execution.run(self.root, self.profile, self.task, portable=True)
        self.assertEqual(record['results'][0]['status'], 'incomplete')
        manifest = read(path.parent / 'unit/result.json')
        with self.assertRaises(Invalid):
            portable.validate_result(self.root, self.profile, manifest, path.parent / 'unit')

    def archive_result(self):
        self.locator = {'kind': 'github-actions', 'repository': 'example/project', 'run_id': 17,
                        'attempt': 2, 'job_id': 21, 'artifact_id': 22}
        context = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'example/project',
                   'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'test'}
        with patch.dict('os.environ', context):
            path, record = execution.run(self.root, self.profile, self.task, portable=True)
        directory = path.parent / 'unit'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            for path in directory.rglob('*'):
                if path.is_file():
                    z.write(path, path.relative_to(directory).as_posix())
        self.archive = archive.getvalue()
        before = datetime.now(timezone.utc) - timedelta(minutes=1)
        after = datetime.now(timezone.utc) + timedelta(minutes=1)
        self.run = {'run_attempt': 2, 'head_sha': self.task['base'], 'status': 'completed', 'conclusion': 'success'}
        self.job = {'run_id': 17, 'run_attempt': 2, 'name': 'test (3.13)', 'status': 'completed', 'conclusion': 'success',
                    'started_at': before.isoformat(), 'completed_at': after.isoformat()}
        self.artifact_info = {'expired': False, 'created_at': datetime.now(timezone.utc).isoformat(),
                              'digest': 'sha256:' + hashlib.sha256(self.archive).hexdigest(),
                              'workflow_run': {'id': 17, 'head_sha': self.task['base']}}
        return record

    def actions(self, endpoint, **kw):
        if endpoint.endswith('/actions/runs/17'):
            return self.run
        if endpoint.endswith('/actions/jobs/21'):
            return self.job
        if endpoint.endswith('/actions/artifacts/22'):
            return self.artifact_info
        if endpoint.endswith('/actions/artifacts/22/zip'):
            return self.archive
        return self.github(endpoint, **kw)

    def test_actual_result_import_and_v3_delivery(self):
        self.prepare()
        skill, report, _ = self.complete()
        self.issue['body'] = self.body()
        self.archive_result()
        with patch.object(github_read, 'api', side_effect=self.actions):
            progress = self.progress()
            progress['remaining'] = []
            self.issue['comments_data'] = [self.comment(handoffs.draft(self.root, self.profile, self.url, progress, skill))]
            path, imported = portable.import_result(self.root, self.profile, self.locator)
            self.assertEqual(imported['result']['status'], 'passed')
            report.update(schema_version=3, issue=self.url, runs=[path.relative_to(self.root).as_posix()])
            review = read(self.root / report['review'])
            template = verification.review_template(self.root, self.profile, self.task,
                self.root / '.team-workflow/brief.json', self.root / '.team-workflow/knowledge.json', self.url)
            review['requirements'] = template['requirements']
            write(self.root / report['review'], review)
            result = verification.verify(self.root, self.profile, self.task, report, skill)
            self.issue['comments_data'] = []
            with self.assertRaisesRegex(Invalid, 'collaboration gaps'):
                verification.verify(self.root, self.profile, self.task, report, skill)
        self.assertTrue(result['ok'])

    def test_new_handoff_cannot_reuse_review_of_old_prose(self):
        self.prepare()
        skill, report, _ = self.complete()
        self.issue['body'] = self.body()
        report.update(schema_version=3, issue=self.url)
        with patch.object(github_read, 'api', side_effect=self.github):
            progress = self.progress()
            progress['remaining'] = []
            self.issue['comments_data'] = [self.comment(handoffs.draft(self.root, self.profile, self.url, progress, skill))]
            with self.assertRaisesRegex(Invalid, 'current platform requirements'):
                verification.verify(self.root, self.profile, self.task, report, skill)
            review = read(self.root / report['review'])
            template = verification.review_template(self.root, self.profile, self.task,
                self.root / '.team-workflow/brief.json', self.root / '.team-workflow/knowledge.json', self.url)
            review['requirements'] = template['requirements']
            write(self.root / report['review'], review)
            self.assertTrue(verification.verify(self.root, self.profile, self.task, report, skill)['ok'])
            self.issue['assignees'] = [{'login': 'bob'}]
            progress['owner'] = 'bob'
            self.issue['comments_data'].append(self.comment(handoffs.draft(self.root, self.profile, self.url, progress, skill), 2))
            self.assertTrue(verification.verify(self.root, self.profile, self.task, report, skill)['ok'])
            self.issue['body'] += '\nAdditional required behavior: reject invalid inputs.\n'
            self.issue['comments_data'].append(self.comment(handoffs.draft(self.root, self.profile, self.url, progress, skill), 3))
            self.assertTrue(handoffs.resume(self.root, self.profile, self.url, skill)['ok'])
            with self.assertRaisesRegex(Invalid, 'current platform requirements'):
                verification.verify(self.root, self.profile, self.task, report, skill)

    def test_new_attempt_missing_context_changed_source_and_job_rejected(self):
        self.prepare()
        self.check('assert 1+2 == 3')
        self.archive_result()
        with patch.object(github_read, 'api', side_effect=self.actions):
            self.run['run_attempt'] = 3
            with self.assertRaisesRegex(Invalid, 'newer run attempt'):
                portable.import_result(self.root, self.profile, self.locator)
            self.run['run_attempt'] = 2
            self.job['name'] = 'other'
            with self.assertRaisesRegex(Invalid, 'Captured job differs'):
                portable.import_result(self.root, self.profile, self.locator)
            self.job['name'] = 'test'
            (self.root / 'app.py').write_text('wrong = True\n')
            with self.assertRaisesRegex(Invalid, 'stale'):
                portable.import_result(self.root, self.profile, self.locator)

    def test_native_skip_zero_and_failure_cannot_import_as_green_ci(self):
        self.prepare()
        for state in ('skip', 'fail', 'zero'):
            with self.subTest(state=state):
                events = ([{'Action': state, 'Package': 'p', 'Test': 'TestActual'}] if state != 'zero' else []) + [{'Action': 'pass', 'Package': 'p'}]
                self.check('print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')', format='go-json')
                self.archive_result()
                with patch.object(github_read, 'api', side_effect=self.actions), self.assertRaisesRegex(Invalid, 'External check incomplete'):
                    portable.import_result(self.root, self.profile, self.locator)

    def test_archive_and_provider_metadata_are_rechecked(self):
        self.prepare()
        self.check('assert 1+2 == 3')
        self.archive_result()
        with patch.object(github_read, 'api', side_effect=self.actions):
            _, imported = portable.import_result(self.root, self.profile, self.locator)
            self.assertEqual(portable.validate_import(self.root, self.profile, imported)[0]['status'], 'passed')
            path = self.root / imported['manifest']['path']
            value = read(path)
            value['exit_code'] = 7
            write(path, value)
            imported['manifest'] = artifact(self.root, path)
            with self.assertRaisesRegex(Invalid, 'differs from provider archive'):
                portable.validate_import(self.root, self.profile, imported)

    def test_moving_workspace_preserves_portable_source_identity(self):
        self.prepare()
        before = portable.source_state(self.root, self.profile)
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            destination = Path(temp) / 'different-directory'
            shutil.copytree(self.root, destination)
            self.assertEqual(before, portable.source_state(destination, self.profile))

    def test_workflow_upgrade_during_execution_leaves_incomplete_evidence(self):
        self.prepare()
        self.check('print("actual command")')
        with patch.object(execution, 'tool_identity', side_effect=[{'version': 'before'}, {'version': 'after'}]):
            path, record = execution.run(self.root, self.profile, self.task, portable=True)
        self.assertFalse(record['source_unchanged'])
        with self.assertRaisesRegex(Invalid, 'producer changed'):
            portable.validate_result(self.root, self.profile, read(path.parent / 'unit/result.json'), path.parent / 'unit')

    def test_archive_cannot_write_outside_import_directory(self):
        for name in ('../escaped', '/absolute', 'a/../../escaped'):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr(name, 'bad')
            with self.assertRaises(Invalid):
                portable.unpack(output.getvalue(), self.root / '.team-workflow/imports/test')

    def test_read_client_rejects_other_hosts_and_prs(self):
        with self.assertRaises(Invalid):
            github_read.issue_ref('https://other.invalid/example/repo/issues/1')
        with patch.object(github_read, 'api', return_value={'pull_request': {}}):
            with self.assertRaises(Invalid):
                github_read.issue('https://github.com/example/project/issues/1')


if __name__ == '__main__':
    unittest.main()
