"""Acceptance and final delivery retain independent review and knowledge disposition."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixtures
import plan_fixtures as plans
from common import Invalid, artifact, read, write
import delivery
import designs
import knowledge
import validation
import workflow
import coordination
from tw_runtime.team import platform_script as platform_read
from platform_fixtures import CONFIG as PLATFORM_CONFIG, transport as platform_transport


class DeliveryCases(unittest.TestCase):
    setUp = fixtures.WorkflowCases.setUp
    git = fixtures.WorkflowCases.git
    check = fixtures.WorkflowCases.check

    def setup_task(self, complexity='simple', task_id=None, design_task_id=None, extra_check=False, ready_scenarios=True):
        self.check('import app; assert app.add(1,2)==3')
        if extra_check:
            self.profile['checks']['safety'] = copy.deepcopy(self.profile['checks']['unit'])
            self.profile['checks']['safety']['purpose'] = 'Additional required project behavior'
            self.profile['required_checks']['code'].append('safety')
        if task_id:
            self.task['id'] = task_id
        self.design = {'data_version': 1, 'kind': 'design', 'id': 'D-add', 'revision': 1,
            'task_id': design_task_id or self.task['id'], 'assessment': {'complexity': complexity, 'risks': [],
                'effort': 'one hour', 'drivers': ['single function'], 'uncertainties': [], 'required_skills': ['Python']},
            'roles': {'design_owner': 'alice', 'implementation_owner': 'bob', 'acceptance_owner': 'carol'},
            'sections': [
                {'id': 'scope-global', 'type': 'global-scope', 'title': 'Addition', 'body': self.task['goal'], 'data': {}, 'depends_on': []},
                {'id': 'A1', 'type': 'acceptance', 'title': 'Result', 'body': self.task['acceptance'][0]['expectation'], 'data': {'checks': ['unit']}, 'depends_on': []},
                {'id': 'T1', 'type': 'task', 'title': 'Implement', 'body': 'Implement addition',
                 'data': {'acceptance': ['A1'], 'scope': ['app.py'], 'blocked_by': []}, 'depends_on': []}]}
        plans.plan(self.design)
        if self.task['id'] != self.design['task_id']:
            self.task.update(acceptance_scope='task', parent=self.design['task_id'])
        fixtures.write_config(self.root, self.profile)
        self.write('task', self.task)
        self.write('design', self.design)
        self.write('brief', knowledge.brief(self.root, self.task, [], []))
        run, _ = validation.run_batch(self.root, self.profile, [self.task])
        self.runs = [run.relative_to(self.root).as_posix()]
        approval = designs.approval_draft(self.design, 'carol', 'Explicit plan and code approval',
                    code_digest=validation.source_digest(self.root, self.profile), run_refs=[artifact(self.root, run)])
        self.write('approval', approval)
        self.report = {'data_version': 1, 'task_id': self.task['id'], 'design': self.name('design'),
            'approvals': [self.name('approval')], 'brief': self.name('brief'), 'runs': self.runs, 'review': self.name('review')}
        if ready_scenarios:
            plans.submit_scenarios(self.root, self.task, self.report)
        review = delivery.review_template(self.root, self.profile, self.task, self.report)
        ref = artifact(self.root, run)
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': 'Read public behavior and actual assertion output', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': 'Executed assertion 1+2=3', 'evidence': [ref], 'observations': plans.observations(self.root, ref)}]
        self.write('review', review)
        self.write('report', self.report)

    def name(self, name):
        return plans.design_name(name)

    def write(self, name, value):
        if isinstance(value, dict) and value.get('kind') == 'design':
            plans.write_design(self.root / self.name(name), value)
        else:
            write(self.root / self.name(name), plans.written_task(value) if name == 'task' else value)

    def evidence_targets(self):
        other = self.root / '.tw/local/other-repository'
        other.mkdir(parents=True)
        subprocess.check_call(['git', '-C', str(other), 'init', '-q'])
        subprocess.check_call(['git', '-C', str(other), 'remote', 'add', 'origin',
                               'https://github.com/example/evidence.git'])
        self.profile['external_inputs'] = {'other': {'kind': 'repository',
            'repository': 'github.com/example/evidence', 'role': 'build'}}
        write(self.root / '.tw/local/repositories.json', {'repositories': {'github.com/example/evidence': str(other)}})
        fixtures.write_config(self.root, self.profile)
        return [(self.root, {}), (other, {'repository': 'github.com/example/evidence'})]

    def test_referenced_large_evidence_requires_explicit_override(self):
        for target, identity in self.evidence_targets():
            with self.subTest(identity=identity):
                path = target / '.tw/local/large.txt'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('wb') as handle:
                    handle.truncate(64 * 1024 * 1024 + 1)
                ref = {**artifact(target, path), **identity}
                with self.assertRaisesRegex(Invalid, 'exceeds 64 MiB'):
                    delivery.evidence(self.root, self.profile, ref)

    def test_evidence_cli_persists_large_override_for_final_verification(self):
        for target, identity in self.evidence_targets():
            with self.subTest(identity=identity):
                path = target / '.tw/local/large.txt'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('wb') as handle:
                    handle.truncate(64 * 1024 * 1024 + 1)
                args = ['evidence', '--root', str(self.root), '--path', path.relative_to(target).as_posix()]
                if identity:
                    args += ['--evidence-repository', identity['repository']]
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = workflow.main([*args, '--allow-large-evidence'])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 0, result)
                ref = result['artifacts'][0]
                self.assertIs(ref.get('allow_large_evidence'), True)
                self.assertEqual(delivery.evidence(self.root, self.profile, ref), path)
                with self.assertRaisesRegex(Invalid, 'must be a boolean'):
                    delivery.evidence(self.root, self.profile, {**ref, 'allow_large_evidence': 'true'})

    def test_external_compiled_evidence_cannot_bypass_final_verification(self):
        for target, identity in self.evidence_targets():
            with self.subTest(identity=identity):
                path = target / '.tw/local/build.bin'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'\x7fELFcompiled output')
                ref = {**artifact(target, path), **identity}
                with self.assertRaisesRegex(Invalid, 'compiled executable'):
                    delivery.evidence(self.root, self.profile, ref)
                with self.assertRaisesRegex(Invalid, 'compiled executable'):
                    delivery.evidence(self.root, self.profile, {**ref, 'allow_large_evidence': True})

    def test_acceptance_needs_no_completed_knowledge_and_final_delivery_does(self):
        self.setup_task()
        result = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertTrue(result['business_accepted'])
        self.assertFalse(result['delivery_complete'])
        self.assertFalse(result['closable'])
        with self.assertRaises(Invalid) as raised:
            delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertEqual(raised.exception.error_code, 'acceptance-record-missing')
        self.write('acceptance', result)
        self.report['acceptance'] = self.name('acceptance')
        with self.assertRaisesRegex(Invalid, '知识处置'):
            delivery.verify(self.root, self.profile, self.task, self.report)
        self.report['knowledge'] = {'files': [], 'reason': 'Existing source owns the requirement'}
        delivered = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(delivered['delivery_complete'])
        self.assertFalse(delivered['closable'])
        self.report['close_authorization'] = {'confirmed_by': 'carol', 'reference': 'Explicit user authorization to close this task'}
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report)['closable'])

    def test_final_delivery_needs_this_tasks_current_acceptance_record(self):
        self.setup_task()
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.report['acceptance'] = self.name('acceptance')
        self.report['knowledge'] = {'files': [], 'reason': 'Existing source owns the requirement'}
        for change, message in (({'business_accepted': False}, '不是通过的业务验收记录'),
                                ({'kind': 'delivery-verification'}, '不是通过的业务验收记录'),
                                ({'task_id': 'TASK-other'}, '其他任务'),
                                ({'sections': {}}, '方案章节已变化'),
                                ({'source_digest': '0' * 64}, '源码已变化')):
            with self.subTest(change=change):
                self.write('acceptance', {**accepted, **change})
                with self.assertRaisesRegex(Invalid, message):
                    delivery.verify(self.root, self.profile, self.task, self.report)
        self.write('acceptance', accepted)
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report)['delivery_complete'])

    def test_final_delivery_rejects_an_acceptance_of_other_runs_or_reviews(self):
        self.setup_task()
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.write('acceptance', accepted)
        self.report.update(acceptance=self.name('acceptance'),
                           knowledge={'files': [], 'reason': 'Existing source owns the requirement'})
        rerun, _ = validation.run_batch(self.root, self.profile, [self.task])
        ref = artifact(self.root, rerun)
        self.write('approval-2', designs.approval_draft(self.design, 'carol', 'Reviewed the new run',
                   code_digest=validation.source_digest(self.root, self.profile), run_refs=[ref]))
        review = read(self.root / self.name('review'))
        for axis in ('standards', 'spec'):
            review[axis]['evidence'] = [ref]
        review['acceptance'][0].update(evidence=[ref], observations=plans.observations(self.root, ref))
        self.write('review-2', review)
        self.report.update(runs=[rerun.relative_to(self.root).as_posix()], approvals=[self.name('approval-2')],
                           review=self.name('review-2'))
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')['business_accepted'])
        with self.assertRaisesRegex(Invalid, '材料已变化，需要用当前材料重新验收'):
            delivery.verify(self.root, self.profile, self.task, self.report)

    def test_equivalent_paths_and_identical_copies_keep_the_acceptance(self):
        self.setup_task()
        self.report['runs'] = ['./' + p for p in self.runs]
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.write('acceptance', accepted)
        (self.root / self.name('review-copy')).write_bytes((self.root / self.name('review')).read_bytes())
        self.report.update(review=self.name('review-copy'), runs=self.runs, acceptance=self.name('acceptance'),
                           knowledge={'files': [], 'reason': 'Existing source owns the requirement'})
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report)['delivery_complete'])

    def test_automatic_observation_must_reference_selected_run(self):
        self.setup_task()
        original = self.root / self.runs[0]
        focused, _ = validation.run_batch(self.root, self.profile, [self.task], selected=['unit'])
        self.report['runs'] = [*self.runs, focused.relative_to(self.root).as_posix()]
        for original_status in ('passed', 'failed'):
            with self.subTest(original_status=original_status):
                record = read(original)
                record['results'][0].update(status=original_status, exit_code=0 if original_status == 'passed' else 1)
                write(original, record)
                refs = [artifact(self.root, self.root / name) for name in self.report['runs']]
                self.write('approval', designs.approval_draft(self.design, 'carol', 'Reviewed both actual runs',
                    code_digest=validation.source_digest(self.root, self.profile), run_refs=refs))
                review = read(self.root / self.name('review'))
                review['standards']['evidence'] = review['spec']['evidence'] = [refs[1]]
                review['acceptance'][0]['evidence'] = [refs[1]]
                review['acceptance'][0]['observations'] = plans.observations(self.root, refs[0])
                self.write('review', review)
                with self.assertRaisesRegex(Invalid, 'selected execution'):
                    delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
                review['acceptance'][0]['observations'] = plans.observations(self.root, refs[1])
                self.write('review', review)
                self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')['business_accepted'])

    def test_removed_fixture_does_not_invalidate_finished_acceptance(self):
        marker = self.root / '.tw/local/fixture-id.txt'
        marker.parent.mkdir(exist_ok=True)
        marker.write_text('postgres-container-1')
        identity = [sys.executable, '-c', "from pathlib import Path; print(Path('.tw/local/fixture-id.txt').read_text())"]
        self.check = lambda code, **kw: fixtures.WorkflowCases.check(
            self, code, environment={'kind': 'fixture', 'identity': identity}, **kw)
        self.setup_task()
        accepted = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertEqual(accepted['environment_checked'], 'now')
        self.assertEqual(accepted['environment']['unit']['fixture']['identity'], 'postgres-container-1')
        self.write('acceptance', accepted)
        self.report['acceptance'] = self.name('acceptance')
        marker.unlink()  # the isolated database was cleaned up after acceptance
        with self.assertRaisesRegex(Invalid, 'Cannot confirm environment identity'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.report['knowledge'] = {'files': [], 'reason': 'Existing source owns the requirement'}
        delivered = delivery.verify(self.root, self.profile, self.task, self.report)
        self.assertTrue(delivered['delivery_complete'])
        self.assertEqual(delivered['environment_checked'], 'recorded at acceptance')
        self.assertEqual(delivered['environment'], accepted['environment'])
        (self.root / 'app.py').write_text('def add(a, b):\n    return b+a\n')
        # Changed code is still refused offline (here by the code approval bound to the source digest).
        with self.assertRaisesRegex(Invalid, '[Ss]ource|needs review'):
            delivery.verify(self.root, self.profile, self.task, self.report)

    def test_missing_or_stale_combined_approval_cannot_accept(self):
        self.setup_task()
        self.report['approvals'] = []
        with self.assertRaisesRegex(Invalid, 'approval|review'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.report['approvals'] = [self.name('approval')]
        (self.root / 'app.py').write_text('def add(a,b): return a+b+0\n')
        with self.assertRaisesRegex(Invalid, 'approval|review'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_late_brief_does_not_backdate_reading(self):
        self.setup_task()
        value = read(self.root / self.name('brief'))
        value['at'] = '2099-01-01T00:00:00+00:00'
        self.write('brief', value)
        with self.assertRaisesRegex(Invalid, 'after execution'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_weakening_required_checks_does_not_reuse_old_review(self):
        self.setup_task(extra_check=True)
        self.profile['checks']['unrelated'] = copy.deepcopy(self.profile['checks']['unit'])
        self.assertTrue(delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')['business_accepted'])
        self.profile['required_checks']['code'] = ['unit']
        with self.assertRaisesRegex(Invalid, 'validation policy'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_start_context_and_accept_cli_roundtrip(self):
        self.setup_task()
        def cli(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = workflow.main([*args, '--root', str(self.root)])
            return code, json.loads(output.getvalue())
        code, prepared = cli('start', '--task', self.name('task'), '--design', self.name('design'))
        self.assertEqual(code, 0, prepared)
        self.assertTrue(prepared['implementation_ready'])
        code, status = cli('status', '--context', prepared['context']['path'])
        self.assertEqual(code, 0, status)
        self.assertNotIn('closable', status)
        self.assertEqual(status['verified_records'], {})
        code, result = cli('accept', '--task', self.name('task'), '--report', self.name('report'))
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'])

    def document_acceptance(self):
        self.setup_task()
        self.task['kind'] = 'docs'
        self.task['acceptance'][0]['checks'] = []
        self.design['sections'][1]['data']['checks'] = []
        self.design['sections'][1]['data'].pop('verification')
        # 文档使用声明的 doc 入口逐场景记录。
        self.profile['acceptance_entries'] = {'doc': {'surface': 'doc', 'operate': '阅读文档',
            'observe': ['段落'], 'evidence': ['核对记录'], 'isolation': '临时目录'}}
        path = self.root / 'tests/fixtures/scenarios.json'
        value = read(path)
        for node in value['sops']:
            for scenario in node['scenarios']:
                scenario['verify'] = 'doc'
        write(path, value)
        from common import sha
        self.design['sections'][1]['data']['scenarios'][0]['sha256'] = sha(path)
        fixtures.write_config(self.root, self.profile)
        self.write('design', self.design)
        self.write('task', self.task)
        self.write('brief', knowledge.brief(self.root, self.task, [], []))
        self.report['runs'] = []
        self.write('approval', designs.approval_draft(self.design, 'carol', '已核对文档入口',
                    code_digest=validation.source_digest(self.root, self.profile), run_refs=[]))
        rounds = plans.submit_scenarios(self.root, self.task, self.report)
        review = delivery.review_template(self.root, self.profile, self.task, self.report)
        ref = artifact(self.root, self.root / 'app.py')
        review.update(reviewer='carol', knowledge_conflicts_resolved=True)
        for axis in ('standards', 'spec'):
            review[axis] = {'status': 'passed', 'summary': '已逐场景核对文档', 'evidence': [ref]}
        review['acceptance'] = [{'id': 'A1', 'status': 'passed', 'summary': '文档满足要求', 'evidence': [ref],
                                 'observations': [{'kind': 'scenarios', 'rounds': rounds}]}]
        self.write('review', review)

    def test_document_only_acceptance_does_not_invent_execution(self):
        self.document_acceptance()
        result = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertEqual(result['checks'], [])

    def test_scenario_executor_is_rechecked_when_roles_change(self):
        self.setup_task()
        import scenario_acceptance
        group, value = scenario_acceptance.current(self.root, self.profile, self.task, self.design)
        self.design['roles']['implementation_owner'] = ' CAROL '
        with self.assertRaisesRegex(Invalid, '场景执行者 must not be the implementation owner'):
            scenario_acceptance.check(self.root, self.profile, self.task, self.design,
                                      read(self.root / self.name('review')), group, value)

    def test_reviewer_must_not_be_the_implementer(self):
        self.setup_task()
        review = read(self.root / self.name('review'))
        review['reviewer'] = 'Bob'
        self.write('review', review)
        with self.assertRaisesRegex(Invalid, 'Reviewer must not be the implementation owner'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_acceptance_needs_recorded_implementer_to_check_independence(self):
        self.setup_task()
        self.design['roles']['implementation_owner'] = ''
        self.write('design', self.design)
        with self.assertRaisesRegex(Invalid, 'approval is missing|recorded implementation owner'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_acceptance_needs_confirmed_business_sources(self):
        self.setup_task()
        del self.design['sections'][1]['data']['sources']
        self.write('design', self.design)
        from contracts import execution_environment
        self.assertIn('Acceptance scenario needs confirmed business sources: A1',
                      execution_environment(self.profile, self.task, self.design))
        with self.assertRaisesRegex(Invalid, 'confirmed business sources: A1'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_scenario_sources_are_explicit_and_unique(self):
        self.setup_task()
        scenario = self.design['sections'][1]['data']
        valid = copy.deepcopy(scenario['sources'])
        for value, message in (([], 'non-empty'), ([{'ref': 'SOP#1', 'version': '1'}], 'Missing fields: confirmed_by'),
                               ([{'ref': '__REPLACE__', 'version': '1', 'confirmed_by': 'carol'}], 'Unfilled template'),
                               (valid + valid, 'Duplicate scenario source')):
            scenario['sources'] = value
            with self.subTest(value=value), self.assertRaisesRegex(Invalid, message):
                designs.fingerprints(self.design)
        scenario['sources'] = valid

    def test_readable_pending_status_and_report_status_execute_no_project_commands(self):
        self.setup_task(complexity='medium', ready_scenarios=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['status', '--root', str(self.root), '--task', self.name('task'),
                                  '--design', self.name('design'), '--format', 'text'])
        self.assertEqual(code, 0)
        self.assertNotIn('通过', output.getvalue())
        self.assertIn('scope-global', output.getvalue())
        marker = self.root / 'should-not-be-created'
        import sys
        self.profile['checks']['unit']['environment'] = {'kind': 'fixture',
            'identity': [sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).write_text("bad"); print("fixture")']}
        fixtures.write_config(self.root, self.profile)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = workflow.main(['status', '--root', str(self.root), '--task', self.name('task'), '--report', self.name('report')])
        self.assertEqual(code, 0, output.getvalue())
        self.assertFalse(marker.exists())
        self.assertNotIn('business_accepted', json.loads(output.getvalue()))
        self.assertEqual(json.loads(output.getvalue())['verified_records'], {})

    def test_undeclared_regression_lists_each_scenario_as_pending(self):
        self.setup_task()
        result = delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')
        self.assertEqual([row['id'] for row in result['automation_status']['pending']], ['SYNTH-01-P01', 'SYNTH-01-N01'])
        self.assertTrue(result['regression_pending'])

    def test_handwritten_automation_points_to_scenario_regression(self):
        self.setup_task()
        self.report['automation'] = {'scenarios': []}
        with self.assertRaisesRegex(Invalid, '回归状态写在场景文件各场景的 regression'):
            delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')

    def test_parent_withdrawal_during_child_acceptance_is_rejected(self):
        parent = 'https://github.com/example/project/issues/1'
        child = 'https://github.com/example/project/issues/2'
        self.setup_task(task_id=child, design_task_id=parent)
        parent_task = {**self.task, 'id': parent, 'acceptance_scope': 'requirement'}
        parent_task.pop('parent', None)
        def issue(url, task, parent_url=None):
            return {'html_url': url, 'body': plans.task_body(task, parent_url),
                'assignees': [{'login': 'bob'}], 'comments_data': []}
        parent_issue, child_issue = issue(parent, parent_task), issue(child, self.task, parent)
        withdrawal, watching, count = None, False, 0
        def append(draft):
            parent_issue['comments_data'].append({'html_url': parent + '#issuecomment-' + str(len(parent_issue['comments_data']) + 1),
                'body': draft['markdown'], 'user': {'login': draft['record'].get('creator', 'carol')}})
        def api(endpoint, **kwargs):
            nonlocal count
            selected = parent_issue if '/issues/1' in endpoint else child_issue
            if selected is parent_issue and watching and '/comments' not in endpoint:
                count += 1
                if count == 2:
                    append(withdrawal)
            return copy.deepcopy(selected['comments_data'] if '/comments' in endpoint else selected)
        self.profile['platform'] = copy.deepcopy(PLATFORM_CONFIG)
        fixtures.write_config(self.root, self.profile)
        with patch.object(platform_read, 'call', side_effect=platform_transport(api)):
            append(plans.draft_design(self.root, parent, self.design))
            accepted = coordination.draft_approval(parent, {'reviewer': 'carol', 'confirmation': 'Final code and plan accepted',
                'code_digest': validation.source_digest(self.root, self.profile),
                'run_refs': [artifact(self.root, self.root / path) for path in self.runs]})
            append(accepted)
            self.write('approval', accepted['record']['approval'])
            withdrawal = coordination.draft_approval(parent, {'reviewer': 'carol', 'confirmation': 'A contract requirement needs correction',
                'decision': 'changes-requested', 'section_ids': 'all'})
            watching = True
            with self.assertRaisesRegex(Invalid, 'Platform requirements, approvals'):
                delivery.verify(self.root, self.profile, self.task, self.report, 'acceptance')


if __name__ == '__main__':
    unittest.main()
