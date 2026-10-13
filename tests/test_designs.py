"""Public design/review contracts; no platform writes or knowledge mutations."""
import copy
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-workflow/scripts'
sys.path.insert(0, str(SCRIPTS))
from common import Invalid
import designs
import plan_fixtures as plans


def section(identifier, kind, depends=(), data=None):
    return {'id': identifier, 'type': kind, 'title': identifier, 'body': 'Required behavior.',
            'data': data or {}, 'depends_on': list(depends)}


def example(complexity='medium'):
    return plans.plan({
        'kind': 'design', 'id': 'D-orders', 'revision': 1,
        'task_id': 'https://github.com/example/orders/issues/10',
        'assessment': {'complexity': complexity, 'risks': ['public-contract'], 'effort': 'One day',
                       'drivers': ['Two independent interfaces'], 'uncertainties': [],
                       'required_skills': ['API development']},
        'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'alice'},
        'sections': [section('scope-global', 'global-scope'),
                     section('api-1', 'interface'), section('api-2', 'interface'),
                     section('A1', 'acceptance', ['api-1'], {'checks': ['orders']}),
                     section('A2', 'acceptance', ['api-2'], {'checks': ['refunds']}),
                     section('T1', 'task', data={'acceptance': ['A1'], 'scope': ['src/orders'], 'blocked_by': []}),
                     section('T2', 'task', data={'acceptance': ['A2'], 'scope': ['src/refunds'], 'blocked_by': []})],
    })


def question(state='open'):
    resolution = {} if state == 'open' else {'reason': 'Keep refunds open for 30 days', 'evidence': ['Product confirmation']}
    return {'id': 'D1', 'summary': 'Which refund policy?', 'owner': 'alice', 'affects': ['api-2'],
            'blocks': ['implementation'], 'state': state, 'resolution': resolution}


def changed(design, identifier, body='Changed required behavior.'):
    result = copy.deepcopy(design)
    result['revision'] += 1
    next(item for item in result['sections'] if item['id'] == identifier)['body'] = body
    return result


class DesignCases(unittest.TestCase):
    def test_simple_child_of_complex_plan_uses_its_own_assessment(self):
        design = example('complex')
        child = next(row for row in design['sections'] if row['id'] == 'T1')
        child['data']['assessment'] = {**design['assessment'], 'complexity': 'simple', 'risks': ['persistence']}
        status = designs.approval_status(design, [], section_ids=['T1'], changed_paths=['src/orders/model.py'])
        self.assertTrue(status['implementation_ready'])
        self.assertEqual(status['review_mode'], 'combined')
        self.assertEqual(status['task_assessments']['T1']['risks'], ['persistence'])
        self.assertFalse(designs.approval_status(design, [], section_ids=['T2'], changed_paths=[])['implementation_ready'])

    def test_interface_change_invalidates_only_its_acceptance_and_task(self):
        before = example()
        after = changed(before, 'api-1')
        result = designs.impact(before, after, changed_paths=['src/orders/service.py'])
        self.assertEqual(result['changed'], ['api-1'])
        self.assertEqual(result['affected'], ['A1', 'T1', 'api-1'])
        self.assertEqual(result['unaffected'], ['A2', 'T2', 'api-2', 'scope-global'])
        self.assertEqual(result['affected_acceptance'], ['A1'])
        self.assertEqual(result['affected_tasks'], ['T1'])
        self.assertFalse(result['full_review_required'])
        self.assertEqual(before, example())

    def test_prior_approval_survives_only_unchanged_constraint_chains(self):
        before = example()
        approval = designs.approval_draft(before, 'alice', 'Reviewed in team meeting')
        after = changed(before, 'api-1')
        result = designs.approval_status(after, [approval], previous=before,
                                         changed_paths=['src/orders/service.py'])
        self.assertEqual(result['approved'], ['A2', 'T2', 'api-2', 'scope-global'])
        self.assertEqual(result['stale'], ['A1', 'T1', 'api-1'])
        self.assertFalse(result['implementation_ready'])
        self.assertFalse(result['acceptance_ready'])
        self.assertEqual(result['tasks']['T1']['state'], 'needs-review')
        self.assertEqual(result['tasks']['T2']['state'], 'ready')

    def test_request_to_change_global_scope_blocks_implementation(self):
        design = example()
        accepted = designs.approval_draft(design, 'alice', 'Initial acceptance')
        rejected = designs.approval_draft(design, 'bob', 'Scope requires another decision',
                                          decision='changes-requested', section_ids=['scope-global'])
        result = designs.approval_status(design, [accepted, rejected], changed_paths=[])
        self.assertFalse(result['implementation_ready'])
        self.assertEqual(result['tasks']['T1']['state'], 'needs-review')
        self.assertFalse(result['local_review_valid'])

    def test_deleted_section_needs_explicit_review_after_another_revision(self):
        first = example()
        second = copy.deepcopy(first)
        second['revision'] = 2
        second['sections'] = [row for row in second['sections'] if row['id'] != 'api-1']
        next(row for row in second['sections'] if row['id'] == 'A1')['depends_on'] = []
        third = changed(second, 'api-2')
        current_ids = [row['id'] for row in third['sections']]
        approval = designs.approval_draft(third, 'alice', 'Reviewed all current sections',
                                          section_ids=current_ids, history=[first, second])
        self.assertEqual(approval['deletions'], [])
        status = designs.approval_status(third, [approval], history=[first, second], changed_paths=[])
        self.assertFalse(status['fully_approved'])
        self.assertEqual([(row['id'], row['state']) for row in status['deletions']], [('api-1', 'unreviewed')])
        tombstone = designs.approval_draft(third, 'bob', 'Confirmed removing the obsolete interface',
                                          section_ids=[], deletion_ids=['api-1'], history=[first, second])
        final = designs.approval_status(third, [approval, tombstone], history=[first, second], changed_paths=[])
        self.assertTrue(final['fully_approved'], final)
        self.assertTrue(final['acceptance_ready'], final)

    def test_simple_high_risk_task_can_implement_but_needs_matching_combined_review(self):
        design = example('simple')
        design['assessment']['risks'] = ['authorization', 'persistence', 'public-contract']
        runs = [{'path': 'results/run-1.json', 'sha256': 'a' * 64}]
        before = designs.approval_status(design, [], changed_paths=['src/orders/model.py'])
        self.assertTrue(before['implementation_ready'])
        self.assertFalse(before['acceptance_ready'])
        approval = designs.approval_draft(design, 'alice', 'Plan and implementation accepted',
                                          code_digest='b' * 64, run_refs=runs)
        current = designs.approval_status(design, [approval], changed_paths=['src/orders/model.py'],
                                          code_digest='b' * 64, run_refs=runs)
        self.assertTrue(current['acceptance_ready'], current)
        changed_code = designs.approval_status(design, [approval], changed_paths=['src/orders/model.py'],
                                               code_digest='c' * 64, run_refs=runs)
        self.assertFalse(changed_code['acceptance_ready'])
        self.assertFalse(changed_code['local_review_valid'])

    def test_combined_review_also_binds_the_removal_of_sections(self):
        before = example('simple')
        after = copy.deepcopy(before)
        after['revision'] = 2
        after['sections'] = [row for row in after['sections'] if row['id'] not in {'api-2', 'A2', 'T2'}]
        scope = after['sections'][0]['data']
        scope['requirement_acceptance'] = ['A1']
        scope['impact'][0]['acceptance'] = ['A1']
        runs = [{'path': 'results/run-2.json', 'sha256': 'e' * 64}]
        combined = designs.approval_draft(after, 'alice', 'Reviewed all current code and sections',
                                         section_ids=[row['id'] for row in after['sections']],
                                         code_digest='d' * 64, run_refs=runs, previous=before)
        design_only = designs.approval_draft(after, 'bob', 'Approved deleting the unused refund plan',
                                            section_ids=[], deletion_ids=['api-2', 'A2', 'T2'], previous=before)
        result = designs.approval_status(after, [combined, design_only], previous=before, changed_paths=[],
                                         code_digest='d' * 64, run_refs=runs)
        self.assertTrue(result['fully_approved'])
        self.assertFalse(result['acceptance_ready'])
        self.assertFalse(result['combined_complete'])

    def test_changed_assessment_requires_review_but_assignments_do_not(self):
        before = example()
        approval = designs.approval_draft(before, 'alice', 'Plan accepted')
        reassigned = copy.deepcopy(before)
        reassigned['revision'] = 2
        reassigned['roles']['implementation_owner'] = 'charlie'
        stable = designs.approval_status(reassigned, [approval], previous=before, changed_paths=[])
        self.assertTrue(stable['fully_approved'])
        reassessed = copy.deepcopy(reassigned)
        reassessed['revision'] = 3
        reassessed['assessment']['complexity'] = 'complex'
        change = designs.impact(reassigned, reassessed, history=[before], changed_paths=[])
        self.assertTrue(change['assessment_changed'])
        self.assertEqual(change['affected'], ['A1', 'A2', 'T1', 'T2', 'api-1', 'api-2', 'scope-global'])
        stale = designs.approval_status(reassessed, [approval], history=[before, reassigned], changed_paths=[])
        self.assertFalse(stale['fully_approved'])
        self.assertFalse(stale['implementation_ready'])

    def test_one_task_can_finish_while_an_independent_task_needs_review(self):
        before = example()
        approval = designs.approval_draft(before, 'alice', 'Approved both independent interfaces')
        after = changed(before, 'api-2')
        result = designs.approval_status(after, [approval], previous=before, section_ids=['T1'],
                                         changed_paths=['src/orders/service.py', 'src/refunds/service.py'])
        self.assertEqual(result['required_sections'], ['A1', 'T1', 'api-1', 'scope-global'])
        self.assertEqual(result['required_tasks'], ['T1'])
        self.assertTrue(result['fully_approved'], result)
        self.assertTrue(result['implementation_ready'])
        self.assertTrue(result['acceptance_ready'])
        self.assertEqual(result['scope']['outside_selection'], ['src/refunds/service.py'])

    def test_deleted_interface_blocks_its_task_without_blocking_an_independent_task(self):
        before = example()
        old_review = designs.approval_draft(before, 'alice', 'Initial plan approved')
        after = copy.deepcopy(before)
        after['revision'] = 2
        after['sections'] = [row for row in after['sections'] if row['id'] != 'api-1']
        next(row for row in after['sections'] if row['id'] == 'A1')['depends_on'] = []
        updated = designs.approval_draft(after, 'alice', 'Current task wording approved',
                                         section_ids=['A1', 'T1'], previous=before)
        affected = designs.approval_status(after, [old_review, updated], previous=before,
                                           section_ids=['T1'], changed_paths=[])
        self.assertFalse(affected['implementation_ready'])
        self.assertFalse(affected['acceptance_ready'])
        self.assertEqual(affected['tasks']['T1']['unreviewed_deletions'], ['api-1'])
        independent = designs.approval_status(after, [old_review, updated], previous=before,
                                              section_ids=['T2'], changed_paths=[])
        self.assertTrue(independent['acceptance_ready'], independent)
        self.assertFalse(independent['deletions'][0]['required'])

    def test_removed_edges_still_participate_in_change_impact(self):
        before = example()
        after = changed(before, 'api-1')
        next(row for row in after['sections'] if row['id'] == 'A1')['depends_on'] = ['api-2']
        result = designs.impact(before, after, changed_paths=[])
        self.assertEqual(result['affected'], ['A1', 'T1', 'api-1'])
        self.assertEqual(result['affected_acceptance'], ['A1'])
        self.assertEqual(result['affected_tasks'], ['T1'])

    def test_global_scope_change_invalidates_every_section(self):
        before = example()
        after = changed(before, 'scope-global')
        result = designs.impact(before, after, changed_paths=[])
        self.assertEqual(result['unaffected'], [])
        self.assertEqual(result['affected_tasks'], ['T1', 'T2'])
        self.assertEqual(result['affected_acceptance'], ['A1', 'A2'])

    def test_full_approval_does_not_cover_a_later_section(self):
        before = example()
        accepted = designs.approval_draft(before, 'alice', 'Whole plan approved')
        after = copy.deepcopy(before)
        after['revision'] = 2
        after['sections'].append(section('data-1', 'data'))
        result = designs.approval_status(after, [accepted], previous=before, changed_paths=[])
        self.assertEqual(result['missing'], ['data-1'])
        self.assertFalse(result['fully_approved'])

    def test_same_content_with_reordered_keys_and_lf_has_the_same_fingerprints(self):
        before = example()
        before['sections'][1]['body'] = 'First line.\nSecond line.\n'
        before['sections'][3]['depends_on'] = ['api-1', 'api-2']
        after = copy.deepcopy(before)
        after['sections'][1]['body'] = 'First line.\r\nSecond line.\r\n'
        after['sections'][3]['depends_on'].reverse()
        after['sections'].reverse()
        after['roles']['implementation_owner'] = 'charlie'
        after['revision'] = 2
        self.assertEqual(designs.fingerprints(before), designs.fingerprints(after))

    def test_execution_prerequisites_do_not_create_constraint_dependencies(self):
        before = example()
        next(row for row in before['sections'] if row['id'] == 'T2')['data']['blocked_by'] = ['T1']
        after = changed(before, 'api-1')
        change = designs.impact(before, after, changed_paths=[])
        self.assertNotIn('T2', change['affected'])
        accepted = designs.approval_draft(before, 'alice', 'Both tasks approved')
        waiting = designs.approval_status(before, [accepted], changed_paths=[])
        self.assertEqual(waiting['tasks']['T2']['state'], 'waiting-for-tasks')
        ready = designs.approval_status(before, [accepted], changed_paths=[], completed_tasks=['T1'])
        self.assertTrue(ready['tasks']['T2']['ready'])

    def test_pending_decisions_block_only_affected_tasks_even_when_simple(self):
        design = example('simple')
        design['issues'] = [question()]
        design['assessment']['uncertainties'] = ['D1']
        status = designs.approval_status(design, [], changed_paths=[])
        self.assertEqual(status['tasks']['T2']['pending_decisions'], ['D1'])
        self.assertFalse(status['tasks']['T2']['ready'])
        self.assertTrue(status['tasks']['T1']['ready'])
        self.assertEqual(status['uncertainties'], ['D1'])
        selected = designs.approval_status(design, [], changed_paths=[], section_ids=['T1'])
        self.assertEqual(selected['required_pending_decisions'], [])
        self.assertTrue(selected['implementation_ready'])

    def test_confirming_a_business_answer_requires_review_of_affected_sections(self):
        before = example()
        before['issues'] = [question()]
        accepted = designs.approval_draft(before, 'alice', 'Known requirements reviewed')
        after = copy.deepcopy(before)
        after['revision'] = 2
        after['issues'] = [question('resolved')]
        status = designs.approval_status(after, [accepted], previous=before, changed_paths=[])
        self.assertEqual(status['stale'], ['A2', 'T2', 'api-2'])
        change = designs.impact(before, after, changed_paths=[])
        self.assertEqual(change['affected'], ['A2', 'T2', 'api-2'])
        self.assertEqual(change['decision_changes'], ['D1'])

    def test_missing_scope_or_unknown_changed_files_never_claim_local_approval(self):
        design = example()
        accepted = designs.approval_draft(design, 'alice', 'Plan approved')
        for paths in (None, ['src/orders-extra/service.py'], ['README.md']):
            with self.subTest(paths=paths):
                status = designs.approval_status(design, [accepted], changed_paths=paths)
                self.assertFalse(status['local_review_valid'])
                self.assertFalse(status['acceptance_ready'])
        design['sections'][-1]['data']['scope'] = []
        self.assertEqual(designs.scope_coverage(design, [])['missing_scopes'], ['T2'])
        whole = example()
        whole['sections'][-1]['data']['scope'] = ['.']
        self.assertEqual(designs.scope_coverage(whole, ['README.md'])['mapped']['README.md'], ['T2'])

    def test_missing_history_cannot_hide_an_earlier_deletion(self):
        design = example()
        design['revision'] = 3
        accepted = designs.approval_draft(design, 'alice', 'Current version reviewed')
        status = designs.approval_status(design, [accepted], changed_paths=[])
        self.assertFalse(status['history_complete'])
        self.assertFalse(status['fully_approved'])
        self.assertFalse(status['acceptance_ready'])
        self.assertFalse(status['implementation_ready'])

    def test_stale_format_or_forged_fingerprints_fail_closed(self):
        design = example()
        accepted = designs.approval_draft(design, 'alice', 'Plan approved')
        for field, value in (('schema_version', 4), ('fingerprint_version', 0)):
            with self.subTest(field=field):
                stale = copy.deepcopy(accepted)
                stale[field] = value
                status = designs.approval_status(design, [accepted, stale], changed_paths=[])
                self.assertFalse(status['ok'])
                self.assertFalse(status['acceptance_ready'])
        forged = copy.deepcopy(accepted)
        forged['sections']['api-1']['effective'] = 'a' * 64
        status = designs.approval_status(design, [forged], changed_paths=[])
        self.assertFalse(status['ok'])
        self.assertIn('differ', status['gaps'][0])

    def test_bad_references_and_cycles_are_rejected_before_impact_is_claimed(self):
        cases = []
        missing = example()
        missing['sections'][1]['depends_on'] = ['missing']
        cases.append(missing)
        cycle = example()
        cycle['sections'][1]['depends_on'] = ['api-2']
        cycle['sections'][2]['depends_on'] = ['api-1']
        cases.append(cycle)
        task_cycle = example()
        task_cycle['sections'][-2]['data']['blocked_by'] = ['T2']
        task_cycle['sections'][-1]['data']['blocked_by'] = ['T1']
        cases.append(task_cycle)
        invalid_scope = example()
        invalid_scope['sections'][-1]['data']['scope'] = ['../secrets']
        cases.append(invalid_scope)
        duplicate = example()
        duplicate['sections'].append(copy.deepcopy(duplicate['sections'][1]))
        cases.append(duplicate)
        old = example()
        old['schema_version'] = 4
        cases.append(old)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(Invalid):
                    designs.validate_design(value)


if __name__ == '__main__':
    unittest.main()
