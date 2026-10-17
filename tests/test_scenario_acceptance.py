"""E-A5/E-A6/E-A8：场景验收、评审结果和交付回归。"""
import copy
import json
import unittest

import test_scenario_rounds as rounds_fixture
import test_markdown_review as review_fixture
from common import read


class ScenarioAcceptance(unittest.TestCase):
    base = rounds_fixture.ScenarioRounds
    setUp, git, check, setup_task, write, name, current, current_path = (
        base.setUp, base.git, base.check, base.setup_task, base.write, base.name, base.current, base.current_path)
    call, prepare, save_scenarios, approve_start, pending, result, submit = (
        base.call, base.prepare, base.save_scenarios, base.approve_start, base.pending, base.result, base.submit)
    # 只复用夹具；前段的场景契约在原测试类运行。
    __unittest_skip__ = False
    field = review_fixture.MarkdownReview.field
    completed = review_fixture.MarkdownReview.completed

    def all_results(self, status='pass', **extra):
        return [self.result(key, status, **extra) for key in ('S-P', 'S-N', 'T-P', 'T-N')]

    def reviewed(self):
        code, value = self.call('review', '--task', self.task['id'])
        self.assertEqual(code, 0, value)
        path = self.root / value['review_file']
        path.write_text(self.completed(path.read_text()).replace('- 复核：待复核', '- 复核：已复核'))
        code, submitted = self.call('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 0, submitted)
        return value, submitted

    def test_run_waits_for_scenarios_and_pending_points_to_submit_with_root(self):
        self.prepare()
        additional = copy.deepcopy(self.design['sections'][1])
        additional.update(id='A2', title='第二验收项')
        self.design['sections'][1]['data']['scenarios'][0]['nodes'] = ['S']
        additional['data']['scenarios'][0]['nodes'] = ['T']
        self.design['sections'].append(additional)
        self.design['sections'][0]['data']['requirement_acceptance'].append('A2')
        self.design['sections'][0]['data']['impact'][0]['acceptance'].append('A2')
        self.design['sections'][2]['data']['acceptance'].append('A2')
        self.task['acceptance'].append({'id': 'A2', 'expectation': additional['body'], 'checks': ['unit']})
        self.write('task', self.task)
        self.write('design', self.design)
        self.approve_start()
        code, ran = self.call('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ran)
        self.assertNotIn('review_draft', ran)
        self.assertIn('scenarios pending', ran['next_action'])
        pending = self.pending()
        self.assertIn('按清单执行场景', pending['next_action'])
        self.assertIn('scenarios submit', pending['next_action'])
        self.assertIn('--root ', pending['next_action'])
        from commands import readable
        self.assertNotIn('-：', readable(pending))
        self.assertEqual(self.submit(self.all_results())[0], 0)
        code, ready = self.call('run', '--task', self.task['id'])
        self.assertEqual(code, 0, ready)
        text = (self.root / ready['review_file']).read_text()
        for key, included, excluded in (('A1', ('S-P', 'S-N'), ('T-P', 'T-N')),
                                         ('A2', ('T-P', 'T-N'), ('S-P', 'S-N'))):
            section = text.partition('## 验收 ' + key)[2].split('\n## ', 1)[0]
            for token in (*included, 'passed', '实际结果', '已核对预期结果与副作用', '执行者', 'carol', '轮次：1'):
                self.assertIn(token, section)
            for token in excluded:
                self.assertNotIn(token, section)

    def test_accept_requires_scenarios_and_records_summary_and_rounds(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        self.reviewed()
        code, rejected = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, rejected.get('error_code')), (1, 'scenario-acceptance-incomplete'))
        self.assertIn('S-P', rejected['problem'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, accepted = self.call('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertEqual(accepted['summary_counts'], {'passed': 4, 'failed': 0, 'blocked': 0, 'pending': 0})
        self.assertEqual(len(accepted['scenario_rounds']), 1)
        self.assertTrue(accepted['regression_pending'])
        self.assertEqual([r['id'] for r in accepted['automation_status']['pending']], ['S-P', 'S-N', 'T-P', 'T-N'])
        self.assertIn('一次通过率：4/4', accepted['summary_markdown'])
        self.assertIn('多人一致：0/0', accepted['summary_markdown'])
        self.assertIn('S-P：not-declared', accepted['summary_markdown'])

    def test_review_protects_scenarios_and_prefills_blocked_issue(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        rows = self.all_results()
        rows[-1].update(status='blocked', finding='F-env', actual='入口环境受阻', evidence=[])
        self.assertEqual(self.submit(rows)[0], 0)
        code, draft = self.call('review', '--task', self.task['id'])
        self.assertEqual(code, 0, draft)
        text = (self.root / draft['review_file']).read_text()
        for word in ('场景执行', 'T-N', 'blocked', '入口环境受阻', 'carol', '轮次', '### 问题 F-env'):
            self.assertIn(word, text)
        self.assertNotIn('人工观察', text)
        value = read(self.root / draft['binding']['path'])
        self.assertIn('scenario_rounds', value['bindings'])
        self.assertNotIn('manual', value)
        (self.root / draft['review_file']).write_text(self.completed(text).replace('入口环境受阻', '已修改'))
        code, refused = self.call('review', '--task', self.task['id'], '--submit')
        self.assertEqual(code, 1, refused)

    def test_complex_accept_requires_cases_then_rechecks_current_union(self):
        self.prepare()
        self.design['assessment']['complexity'] = 'complex'
        self.write('design', self.design)
        self.approve_start()
        self.call('run', '--task', self.task['id'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'tester-cases-missing'))
        self.assertIn('测试同事的用例集', refused['problem'])
        self.assertIn('scenarios import-cases', refused['next_action'])
        path = self.root / '.tw/local/cases.json'
        path.write_text(json.dumps({'cases': [{'id': 'C1', 'title': '合成用例'}]}))
        self.assertEqual(self.call('scenarios', 'import-cases', '--task', self.task['id'], path)[0], 0)
        pairs = self.root / '.tw/local/pairs.json'
        pairs.write_text(json.dumps({'covered': [{'case': 'C1', 'scenarios': ['S-P'], 'note': '核对场景'}], 'conflict': [], 'disposed': []}))
        self.assertEqual(self.call('scenarios', 'coverage', '--task', self.task['id'], '--pairs', pairs)[0], 0)
        code, accepted = self.call('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        path.write_text(json.dumps({'cases': [{'id': 'C2', 'title': '新增合成用例'}]}))
        self.assertEqual(self.call('scenarios', 'import-cases', '--task', self.task['id'], path)[0], 0)
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'scenario-coverage-incomplete'))
        self.assertIn('C2', refused['problem'])
        self.assertNotIn('C1', refused['problem'])


    def test_blocked_requires_accepted_or_deferred_finding(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        rows = self.all_results()
        rows[-1].update(status='blocked', finding='F-env', actual='验收环境尚未开放', evidence=[])
        rows[0].update(status='skip', finding='F-env', actual='约定与环境开放后一并复验', evidence=[], note='环境开放后复验')
        self.assertEqual(self.submit(rows)[0], 0)
        draft, _ = self.reviewed()
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'scenario-acceptance-incomplete'))
        self.assertIn('T-N', refused['problem'])
        self.assertIn('accepted', refused['problem'])
        self.assertIn('deferred', refused['problem'])
        self.assertEqual(refused['scenario_states'], {'failed': [], 'pending': [], 'blocked': ['S-P', 'T-N']})
        self.assertIn('review', refused['next_action'])
        self.assertIn('--submit', refused['next_action'])
        self.assertEqual(refused['next_action'], '在评审的问题小节填写处置后提交：tw team review --task '
                         + self.task['id'] + ' --submit --root ' + str(self.root))
        self.assertNotIn('scenarios pending', refused['next_action'])
        code, stopped = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 1, stopped)
        self.assertEqual(stopped['stopped_at'], 'acceptance')
        self.assertEqual(stopped['scenario_states'], refused['scenario_states'])
        self.assertEqual(stopped['next_action'], refused['next_action'])
        path = self.root / draft['review_file']
        text = path.read_text()
        for field, value in {'状态': 'deferred', '处置理由': '先交付可运行入口', '处置证据': 'SOP#env',
                             '确认人': 'user', '跟进任务': 'TASK-env（2026-11-01）', '范围调整': '环境开放后复验 T-N'}.items():
            text = self.field(text, '### 问题 F-env', field, value)
        path.write_text(text)
        self.assertEqual(self.call('review', '--task', self.task['id'], '--submit')[0], 0)
        code, accepted = self.call('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertEqual(accepted['summary_counts']['blocked'], 2)
        for command, extra in (('accept', []), ('deliver', ['--reason', '现有知识已覆盖']), ('verify', [])):
            code, result = self.call(command, '--task', self.task['id'], *extra)
            self.assertEqual(code, 0, result)
            self.assertEqual(result['unverified_scope'], [
                {'scenario': 'S-P', 'status': 'skip', 'finding': 'F-env', 'finding_state': 'deferred'},
                {'scenario': 'T-N', 'status': 'blocked', 'finding': 'F-env', 'finding_state': 'deferred'}])
            summary = result['summary_markdown']
            self.assertIn('**未验证范围**', summary)
            self.assertIn('S-P：skip；问题 F-env：deferred', summary)
            self.assertIn('T-N：blocked；问题 F-env：deferred', summary)

    def test_regression_is_generated_and_handwritten_automation_is_rejected(self):
        self.prepare()
        events = [{'Action': 'pass', 'Package': 'p', 'Test': 'TestA'}, {'Action': 'pass', 'Package': 'p'}]
        self.check('print(' + repr('\n'.join(json.dumps(row) for row in events)) + ')', format='go-json')
        import test_workflow
        test_workflow.write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'unit', 'cases': ['p::TestA']}
        self.scenarios['sops'][0]['scenarios'][1]['regression'] = {'check': 'unit', 'cases': ['p::Missing']}
        self.scenarios['sops'][1]['scenarios'][0]['regression'] = {'manual': '外部入口由用户核对', 'owner': 'QA', 'trigger': '发版前'}
        self.save_scenarios()
        self.approve_start()
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, delivered = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'])
        self.assertTrue(delivered['regression_pending'])
        self.assertEqual([r['id'] for r in delivered['automation_status']['automated']], ['S-P'])
        self.assertEqual([r['id'] for r in delivered['automation_status']['manual-only']], ['T-P'])
        self.assertEqual([r['id'] for r in delivered['automation_status']['pending']], ['S-N', 'T-N'])
        self.assertEqual([r['reason'] for r in delivered['automation_status']['pending']],
                         ['cases-not-passed', 'not-declared'])
        code, report = self.call('delivery-template', '--task', self.task['id'])
        self.assertEqual(code, 0, report)
        value = read(self.root / report['artifact']['path'])
        self.assertNotIn('automation', value)
        value['automation'] = {}
        path = self.root / '.tw/local/retired-report.json'
        path.write_text(json.dumps(value))
        code, refused = self.call('verify', '--task', self.task['id'], '--report', path)
        self.assertEqual(code, 1, refused)
        self.assertIn('回归状态写在场景文件各场景的 regression', refused['problem'])

    def test_new_scenario_expires_review_and_only_new_id_is_listed(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        extra = copy.deepcopy(self.scenarios['sops'][0]['scenarios'][0])
        extra.update(id='S-ADDED', title='遗漏的输入')
        self.scenarios['sops'][0]['scenarios'].append(extra)
        self.save_scenarios()
        self.assertEqual([row['id'] for row in self.pending()['pending']], ['S-ADDED'])
        self.approve_start()
        self.assertEqual(self.call('run', '--task', self.task['id'])[0], 0)
        self.assertEqual(self.submit([self.result('S-ADDED')])[0], 0)
        code, status = self.call('status', '--task', self.task['id'])
        self.assertEqual(code, 0, status)
        self.assertEqual(next(row['state'] for row in status['steps'] if row['id'] == 'review'), 'stale')
        draft, _ = self.reviewed()
        self.assertEqual(draft['changes']['scenarios'], ['S-ADDED'])
        code, result = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, result)

    def test_manual_verification_reports_line_and_no_checks_omit_verification(self):
        self.prepare()
        import designs
        import design_files
        from common import Invalid
        raw = (self.root / self.name('design')).read_text()
        changed = raw.replace('- 验证：自动', '- 验证：人工')
        line = next(i for i, text in enumerate(changed.splitlines(), 1) if text.startswith('- 验证：人工'))
        with self.assertRaisesRegex(Invalid, '第 ' + str(line) + ' 行.*人工执行按场景逐条记录，用 tw team scenarios submit 登记'):
            designs.load(changed, scenario_reader=design_files.scenario_reader(self.root))
        data = self.design['sections'][1]['data']
        data['checks'] = []
        data.pop('verification')
        raw = designs.render(self.design)
        self.assertIn('- 检查：无', raw)
        self.assertNotIn('- 验证：', raw)
        self.assertNotIn('verification', designs.load(raw, scenario_reader=design_files.scenario_reader(self.root))['sections'][1]['data'])
    def test_regression_pending_names_a_deferred_review_issue(self):
        self.prepare()
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'pending': 'F-reg'}
        self.save_scenarios()
        self.approve_start()
        self.call('run', '--task', self.task['id'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, refused)
        self.assertIn('regression.pending', refused['problem'])
        review = read(self.root / self.current()['review']['path'])
        issue = {'id': 'F-reg', 'summary': '回归入口待补充', 'owner': 'QA', 'affects': ['A1'],
                 'blocks': ['acceptance'], 'state': 'accepted',
                 'resolution': {'reason': '业务结果已经独立核对', 'evidence': ['SOP#reg'], 'confirmed_by': 'user'}}
        review['findings'].append(issue)
        path = self.root / '.tw/local/regression-review.json'
        path.write_text(json.dumps(review))
        code, refused = self.call('accept', '--task', self.task['id'], '--review', path)
        self.assertEqual(code, 1, refused)
        self.assertIn('deferred', refused['problem'])
        issue['state'] = 'deferred'
        issue['resolution'].update(follow_up='TASK-reg（2026-11-01）', scope_change='后续任务沉淀 S-P 的回归')
        path.write_text(json.dumps(review))
        code, accepted = self.call('accept', '--task', self.task['id'], '--review', path)
        self.assertEqual(code, 0, accepted)
        self.assertEqual(accepted['automation_status']['pending'][0],
                         {'id': 'S-P', 'pending': 'F-reg', 'reason': 'deferred'})

    def test_regression_check_without_a_current_passing_run_explains_pending(self):
        self.prepare()
        self.profile['checks']['reg'] = {**self.profile['checks']['unit'], 'format': 'go-json'}
        import test_workflow
        test_workflow.write_config(self.root, self.profile)
        self.scenarios['sops'][0]['scenarios'][0]['regression'] = {'check': 'reg', 'cases': ['p::TestA']}
        self.save_scenarios()
        self.approve_start()
        self.call('run', '--task', self.task['id'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        code, accepted = self.call('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, accepted)
        self.assertEqual(accepted['automation_status']['pending'][0],
                         {'id': 'S-P', 'check': 'reg', 'cases': ['p::TestA'], 'reason': 'check-not-passed'})
    def test_failed_scenario_rejects_a_passed_review_and_names_its_state(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        rows = self.all_results()
        rows[0].update(status='fail', actual='入口结果与确认的预期不符')
        self.assertEqual(self.submit(rows)[0], 0)
        self.reviewed()
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'scenario-acceptance-incomplete'))
        self.assertIn('S-P：failed', refused['problem'])
        self.assertEqual(refused['scenario_states'], {'failed': ['S-P'], 'pending': [], 'blocked': []})
        self.assertIn('scenarios pending', refused['next_action'])
        self.assertIn('--root ', refused['next_action'])
        self.assertFalse(self.current().get('acceptance'))
        code, stopped = self.call('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 1, stopped)
        self.assertEqual(stopped['stopped_at'], 'acceptance')
        self.assertEqual(stopped['scenario_states'], {'failed': ['S-P'], 'pending': [], 'blocked': []})
        self.assertIn('S-P：failed', stopped['problem'])
        self.assertIn('scenarios pending', stopped['next_action'])
        self.assertFalse(self.current().get('acceptance'))
    def test_accept_names_new_pending_scenario_before_an_expired_review(self):
        self.prepare()
        self.call('run', '--task', self.task['id'])
        self.assertEqual(self.submit(self.all_results())[0], 0)
        self.reviewed()
        extra = copy.deepcopy(self.scenarios['sops'][0]['scenarios'][0])
        extra.update(id='S-LATE', title='补充的边界输入')
        self.scenarios['sops'][0]['scenarios'].append(extra)
        self.save_scenarios()
        code, refused = self.call('accept', '--task', self.task['id'])
        self.assertEqual((code, refused.get('error_code')), (1, 'scenario-acceptance-incomplete'), refused)
        self.assertIn('S-LATE：pending', refused['problem'])
