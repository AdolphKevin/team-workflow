"""Public entry regressions for the observed conversation failures."""
import contextlib
import copy
import io
import json
import sys
import unittest

import test_workflow as fixtures
from common import Invalid, artifact, read, write
import workflow
import contracts
import delivery
import designs
import knowledge
import validation
import validation_session
import plan_fixtures as plans
import test_delivery as delivery_cases


def problem(identifier='permission-gap', affects=('A1',), blocks=('acceptance',)):
    return {'id': identifier, 'summary': 'A related operation still needs a decision', 'owner': 'carol',
            'affects': list(affects), 'blocks': list(blocks), 'state': 'open', 'resolution': {}}


class BusinessEvidence(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check
    fake_cs = fixtures.WorkflowCases.fake_cs
    setup_task = delivery_cases.DeliveryCases.setup_task
    name = delivery_cases.DeliveryCases.name
    write = delivery_cases.DeliveryCases.write

    def verify(self):
        return delivery.verify(self.root, self.profile, self.task, self.report, self.skill, 'acceptance')

    def refresh(self):
        self.write('design', self.design)
        self.write('task', self.task)
        self.write('brief', knowledge.brief(self.root, self.task, self.skill, [], []))
        run, _ = validation.run_batch(self.root, self.profile, [self.task])
        self.runs = [run.relative_to(self.root).as_posix()]
        self.report['runs'] = self.runs
        self.write('approval', designs.approval_draft(self.design, 'carol', 'Reviewed the current plan and code',
            code_digest=validation.source_digest(self.root, self.profile), run_refs=[artifact(self.root, run)]))
        review = delivery.review_template(self.root, self.profile, self.task, self.report)
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        ref = artifact(self.root, run)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Inspected actual behavior', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Executed the public operation',
                                'evidence': [ref], 'observations': [plans.observation(ref)]}]
        self.write('review', review)
        self.write('report', self.report)

    def test_missing_scenario_or_assessment_never_prepares_implementation(self):
        self.setup_task()
        for field in ('scenario', 'verification'):
            value = copy.deepcopy(self.design)
            del value['sections'][1]['data'][field]
            with self.assertRaisesRegex(Invalid, 'scenario'):
                designs.approval_status(value, [], changed_paths=[])
        self.design['assessment']['drivers'] = []
        with self.assertRaises(Invalid):
            designs.approval_status(self.design, [], changed_paths=[])

    def test_local_unit_success_cannot_certify_a_business_journey(self):
        self.setup_task()
        self.profile['checks']['unit']['coverage']['level'] = 'unit'
        self.refresh()
        with self.assertRaisesRegex(Invalid, 'Verification level'):
            self.verify()

    def test_fresh_business_entry_catches_missing_creation_despite_seeded_test_success(self):
        self.setup_task()
        application = ('import json,sys\nfrom pathlib import Path\n'
                       'state=Path(sys.argv[2])\n'
                       'if sys.argv[1]=="install": state.write_text(json.dumps({"shop":True}))\n'
                       'elif sys.argv[1]=="send":\n'
                       ' data=json.loads(state.read_text()); assert data.get("channel"), "channel missing after installation"\n')
        (self.root / 'app.py').write_text(application)
        self.profile['checks']['unit']['argv'] = [sys.executable, '-c', 'seeded={"channel": True}; assert seeded["channel"]']
        self.profile['checks']['unit']['coverage']['level'] = 'unit'
        journey = copy.deepcopy(self.profile['checks']['unit'])
        journey['coverage'] = {**plans.coverage(), 'entrypoints': ['app.py:install', 'app.py:send']}
        journey['argv'] = [sys.executable, '-c',
            'import subprocess,sys; state=".team-workflow/business-state.json"; '
            'subprocess.run([sys.executable,"app.py","install",state],check=True); '
            'subprocess.run([sys.executable,"app.py","send",state],check=True)']
        self.profile['checks']['journey'] = journey
        self.task['goal'] = 'A newly installed shop can accept its first message'
        self.task['acceptance'][0]['expectation'] = 'Installation creates the channel needed to accept a message'
        self.task['acceptance'][0]['checks'] = ['journey']
        self.design['sections'][0]['body'] = self.task['goal']
        self.design['sections'][1]['body'] = self.task['acceptance'][0]['expectation']
        self.design['sections'][1]['data']['scenario'] = {'actor': 'buyer', 'initial_state': 'No installed shop',
            'steps': ['Install through the public CLI', 'Send the first message'],
            'expected': 'Message accepted after installation', 'negative_cases': ['A missing channel prevents accepting the message'],
            'sources': plans.sources()}
        self.design['sections'][1]['data']['verification']['coverage'] = journey['coverage']
        self.design['sections'][1]['data']['checks'] = ['journey']
        self.refresh()
        first = read(self.root / self.runs[0])
        outcomes = {r['id']: r['status'] for r in first['results']}
        self.assertEqual(outcomes['unit'], 'passed')
        self.assertEqual(outcomes['journey'], 'failed')
        with self.assertRaisesRegex(Invalid, 'Check did not pass'):
            self.verify()
        # Repair the isolated business fixture, then exercise the same real CLI journey.
        (self.root / 'app.py').write_text(application.replace('{"shop":True}', '{"shop":True,"channel":True}'))
        self.refresh()
        review = read(self.root / self.name('review'))
        review['acceptance'][0]['observations'][0]['check'] = 'journey'
        self.write('review', review)
        self.assertTrue(self.verify()['business_accepted'])

    def test_repository_entry_cannot_certify_the_public_entry(self):
        self.setup_task()
        self.profile['checks']['unit']['coverage']['entrypoints'] = ['repository.add']
        self.refresh()
        with self.assertRaisesRegex(Invalid, 'entrypoint'):
            self.verify()

    def test_recorded_notification_cannot_certify_real_delivery(self):
        self.setup_task()
        self.profile['checks']['unit']['coverage']['substitutes'] = ['notification recorder']
        self.refresh()
        with self.assertRaisesRegex(Invalid, 'substituted'):
            self.verify()

    def test_source_reference_and_passed_text_do_not_replace_observations(self):
        self.setup_task()
        review = read(self.root / self.name('review'))
        review['acceptance'][0]['observations'] = []
        self.write('review', review)
        with self.assertRaisesRegex(Invalid, 'actual execution'):
            self.verify()
        review['acceptance'][0]['observations'] = [plans.observation(artifact(self.root, self.root / 'app.py'))]
        self.write('review', review)
        with self.assertRaisesRegex(Invalid, 'run was not verified'):
            self.verify()

    def test_required_case_cannot_be_invented_or_omitted(self):
        self.setup_task()
        self.design['sections'][1]['data']['verification']['cases'] = ['sample::TestFreshStart']
        self.refresh()
        with self.assertRaisesRegex(Invalid, 'required observed cases'):
            self.verify()
        review = read(self.root / self.name('review'))
        review['acceptance'][0]['observations'][0]['cases'] = ['sample::TestFreshStart']
        self.write('review', review)
        with self.assertRaisesRegex(Invalid, 'missing, failed or skipped'):
            self.verify()

    def test_parent_cannot_claim_completion_from_only_child_acceptance(self):
        self.setup_task()
        additional = copy.deepcopy(self.design['sections'][1])
        additional['id'] = 'whole-journey'
        self.design['sections'].append(additional)
        self.design['sections'][0]['data']['requirement_acceptance'].append('whole-journey')
        self.write('design', self.design)
        with self.assertRaisesRegex(Invalid, 'Parent requirement omits'):
            self.verify()

    def test_child_result_is_explicitly_limited_to_the_task(self):
        self.setup_task(task_id='TASK-child', design_task_id='TASK-parent')
        result = self.verify()
        self.assertEqual(result['acceptance_scope'], 'task')
        self.assertTrue(result['business_accepted'])
        self.assertFalse(result['delivery_complete'])

    def test_known_issue_cannot_disappear_from_a_passed_review(self):
        self.setup_task()
        self.design['issues'] = [problem()]
        self.write('design', self.design)
        with self.assertRaisesRegex(Invalid, 'permission-gap'):
            self.verify()

    def test_failed_review_keeps_issues_for_the_next_attempt(self):
        self.setup_task()
        review = read(self.root / self.name('review'))
        review['findings'] = [problem()]
        self.write('review', review)
        args = ['verify', '--root', str(self.root), '--task', self.name('task'),
                '--report', self.name('report'), '--phase', 'acceptance']
        first = io.StringIO()
        with contextlib.redirect_stdout(first):
            self.assertEqual(workflow.main(args), 1)
        self.assertIn('Unresolved issue', first.getvalue())
        review['findings'] = []
        self.write('review', review)
        second = io.StringIO()
        with contextlib.redirect_stdout(second):
            self.assertEqual(workflow.main(args), 1)
        self.assertIn('disappeared', second.getvalue())
        template = delivery.review_template(self.root, self.profile, self.task, self.report)
        self.assertEqual(template['findings'][0]['id'], 'permission-gap')

    def test_deferred_and_accepted_issues_need_real_disposition_fields(self):
        value = problem()
        value.update(state='deferred', resolution={'reason': 'Later release', 'evidence': ['decision comment']})
        with self.assertRaises(Invalid):
            contracts.issue(value)
        value['resolution'].update(confirmed_by='carol')
        with self.assertRaises(Invalid):
            contracts.issue(value)
        value['resolution'].update(follow_up='TASK-follow-up', scope_change='Current delivery excludes this operation')
        contracts.issue(value)
        value['resolution']['confirmation'] = 'Confirmed this scope change in the weekly meeting'
        contracts.issue(value)
        for bad in (None, '__REPLACE__'):
            value['resolution']['confirmation'] = bad
            with self.subTest(confirmation=bad), self.assertRaises(Invalid):
                contracts.issue(value)
        value['resolution'].pop('confirmation')
        value['resolution']['confirmed_by'] = ''
        with self.assertRaises(Invalid):
            contracts.issue(value)

    def test_issue_only_blocks_its_affected_branch(self):
        self.setup_task()
        self.design['issues'] = [problem(affects=('A1',), blocks=('implementation', 'acceptance'))]
        state = designs.approval_status(self.design, [], changed_paths=[])
        self.assertFalse(state['implementation_ready'])
        self.assertEqual(contracts.unresolved(self.design['issues'], ['unrelated'], 'implementation'), [])

    def test_knowledge_draft_is_partial_until_business_acceptance_exists(self):
        self.setup_task()
        draft = knowledge.completion_template(self.root, self.profile, self.task, self.skill)
        self.assertEqual(draft['task']['status'], 'in-progress')
        self.assertEqual(draft['items'], [])
        accepted = self.verify()
        self.write('acceptance', accepted)
        path = self.root / self.name('acceptance')
        draft = knowledge.completion_template(self.root, self.profile, self.task, self.skill, [path])
        self.assertEqual(draft['task']['status'], 'completed')
        self.assertEqual(draft['task']['source']['workflow_acceptances'],
                         [{**artifact(self.root, path), 'task_id': self.task['id']}])
        self.assertEqual(knowledge.pending_acceptance(draft, [self.task]), [])

    def test_knowledge_rejects_an_unbound_or_stale_completion(self):
        self.setup_task()
        self.write('acceptance', self.verify())
        path = self.root / self.name('acceptance')
        script = self.skill / 'scripts/cs_knowledge.py'
        script.write_text(script.read_text().replace('"task":{"source":source', '"task":{"source":{}'))
        with self.assertRaisesRegex(Invalid, 'reference the actual'):
            knowledge.finish(self.root, self.profile, self.task, self.skill, 'CS-T',
                self.root / self.name('brief'), 'none', 'No new rule', path)
        review = read(self.root / self.name('review'))
        review['spec']['summary'] = 'Changed after acceptance'
        self.write('review', review)
        with self.assertRaises(Invalid):
            knowledge.completion_template(self.root, self.profile, self.task, self.skill, [path])

    def test_knowledge_scope_cannot_use_an_unrelated_repository_path(self):
        self.setup_task()
        self.write('acceptance', self.verify())
        script = self.skill / 'scripts/cs_knowledge.py'
        script.write_text(script.read_text().replace("'path': 'app.py'", "'path': 'unrelated/backend'"))
        with self.assertRaisesRegex(Invalid, 'knowledge scope'):
            knowledge.finish(self.root, self.profile, self.task, self.skill, 'CS-T',
                self.root / self.name('brief'), 'none', 'No new rule', self.root / self.name('acceptance'))

    def test_unresolved_environment_does_not_execute_the_check(self):
        self.setup_task()
        self.profile['checks']['unit']['coverage']['isolation'] = 'unresolved'
        path, record = validation.run_batch(self.root, self.profile, [self.task])
        self.assertEqual(record['results'][0]['state'], 'unavailable')
        self.assertIn('isolation', record['results'][0]['detail'])
        with self.assertRaises(Invalid):
            validation.verify_runs(self.root, self.profile, self.task, [str(path.relative_to(self.root))])

    def test_validation_session_is_visible_and_does_not_claim_editor_enforcement(self):
        self.setup_task()
        self.assertIsNone(validation_session.active(self.root))
        with validation_session.session(self.root, self.profile, [self.task]):
            self.assertEqual(validation_session.active(self.root)['running'][0]['tasks'], [self.task['id']])
            for option in (['--design', self.name('design')], ['--report', self.name('report')]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = workflow.main(['resume', '--root', str(self.root), '--task', self.name('task'), *option])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 0, result)
                self.assertFalse(result['implementation_ready'])
                self.assertTrue(result['validation_active'])
        self.assertIsNone(validation_session.active(self.root))

    def test_local_resume_checks_task_against_current_plan(self):
        self.setup_task()
        original = copy.deepcopy(self.task)
        self.profile['risk_checks']['public-contract'] = ['unit']
        write(self.root / '.team-workflow.json', self.profile)
        variants = [dict(original, risks=['public-contract']),
                    dict(original, design_id='another-plan'),
                    dict(original, acceptance_scope='task', parent='another-parent'),
                    dict(original, acceptance=[{**original['acceptance'][0], 'expectation':'A different requirement'}])]
        for task in variants:
            self.write('task', task)
            for command in ('status', 'resume'):
                with self.subTest(command=command, task=task):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = workflow.main([command, '--root', str(self.root), '--task', self.name('task'),
                                              '--design', self.name('design')])
                    result = json.loads(output.getvalue())
                    self.assertNotEqual(code, 0, result)
                    self.assertFalse(result.get('implementation_ready', False))

    def test_missing_brief_names_the_missing_argument(self):
        self.setup_task()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['review-template', '--root', str(self.root),
                                  '--task', self.name('task'), '--design', self.name('design')])
        self.assertEqual(code, 1)
        self.assertIn('Missing --brief', json.loads(output.getvalue())['problem'])

    def test_shared_reference_cannot_be_a_json_pass_without_original_outputs(self):
        self.setup_task()
        fabricated = {'schema_version': 6, 'kind': 'execution', 'source_unchanged': True,
                      'results': [{'id': 'unit', 'status': 'passed', 'state': 'finished', 'exit_code': 0,
                          'binding': {'definition': validation.execution_definition(self.profile['checks']['unit'])},
                          'cases': {}, 'artifacts': []}]}
        with self.assertRaisesRegex(Invalid, 'original stdout'):
            validation.inspect_record(self.root, self.profile, fabricated)
        self.assertEqual(validation.inspect_record(self.root, self.profile, read(self.root / self.runs[0])), {'unit'})


if __name__ == '__main__':
    unittest.main()
