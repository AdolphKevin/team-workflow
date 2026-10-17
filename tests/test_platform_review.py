"""D4: reviewers publish the generated Markdown; CLI reads it through the project script."""
import plan_fixtures as plans
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_four_command_delivery as four
import test_approval_revision as revision_cases
from common import read
import coordination
from tw_runtime.team import platform_script


class PlatformReview(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, current_path, current, draft_path, run_checks, field, completed = (
        base.setUp, base.git, base.check, base.configure, base.current_path, base.current, base.draft_path,
        base.run_checks, base.field, base.completed)
    command = revision_cases.ApprovalRevision.command

    def response(self):
        os.environ['TW_PLATFORM_RESPONSES'] = json.dumps({'task': self.platform,
            'commit': {'exists': True, 'revision': self.git('rev-parse', 'HEAD').strip(),
                       'author': self.git('show', '-s', '--format=%an <%ae>', 'HEAD').strip(),
                       'time': self.git('show', '-s', '--format=%aI', 'HEAD').strip()},
            'reference': {'reachable': True, 'kind': 'task'}})
        platform_script.clear_cache()

    def post(self, body, kind='review', author='reviewer-account'):
        number = len(self.platform['items'])
        at = f'2026-01-01T00:00:{number:02d}Z'
        item = {'url': self.url + '#item-' + str(number), 'author': author,
                'created_at': at, 'updated_at': at, 'body': body, 'kind': kind}
        self.platform['items'].append(item)
        self.response()
        return item

    def prepare(self, complexity='medium'):
        self.url = 'https://code.example/group/project/tasks/12'
        self.task['id'] = self.url
        self.git('remote', 'add', 'origin', 'https://code.example/group/project.git')
        self.profile['platform'] = {'argv': [sys.executable, str(Path(__file__).with_name('platform_fixture.py'))],
                                   'operations': ['task', 'commit', 'reference']}
        self.configure(complexity)
        self.git('add', '.tw/config.json')
        self.git('commit', '-qm', 'platform fixture configuration')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.task['base'] = self.git('rev-parse', 'HEAD').strip()
        body = plans.task_body(self.task, prose='Addition works.')
        self.platform = {'id': self.url, 'url': self.url, 'repository': 'code.example/group/project',
            'state': 'open', 'owners': ['bob'], 'items': [{'url': self.url, 'author': 'implementer-account',
            'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
            'kind': 'task', 'body': body}], 'raw': {'fixture': 'offline'}}
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        self.response()
        publication = plans.draft_design(self.root, self.url, self.design)
        self.post(publication['pr_description'], 'change', 'implementer-account')
        self.post(publication['markdown'], 'comment', 'implementer-account')
        self.post(coordination.draft_approval(self.url, {'reviewer': 'carol', 'mode': 'design'})['markdown'])
        code, started = self.command('start', '--task', self.url)
        self.assertEqual(code, 0, started)
        self.run_checks()
        return self.completed(self.draft_path().read_text())

    def test_latest_bound_platform_review_is_submitted_with_original_markdown_and_identity(self):
        source = self.prepare()
        self.post(source)
        latest = self.field(source, '## 需求 spec', '理由', '已逐项核对，采用最新评审。')
        item = self.post(latest)
        self.post(source, 'comment')  # A later ordinary comment is not a code review.
        self.post('Only a discussion; no review binding.')
        original = self.draft_path().read_bytes()
        code, result = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, result)
        review = read(self.root / result['artifact']['path'])
        self.assertEqual(review['platform_author'], item['author'])
        self.assertEqual(review['platform_url'], item['url'])
        self.assertEqual(review['spec']['summary'], '已逐项核对，采用最新评审。')
        self.assertEqual((self.root / result['review_markdown']['path']).read_text(), latest)
        self.assertEqual(self.draft_path().read_bytes(), original)
        self.assertEqual(self.current()['review'], result['artifact'])

    def test_deliver_registers_newer_platform_review_then_continues(self):
        source = self.prepare()
        self.post(source)
        code, delivered = self.command('deliver', '--task', self.url, '--reason', 'No reusable knowledge change.')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'], delivered)
        self.assertEqual([row['step'] for row in delivered['steps']], ['review', 'acceptance', 'delivery-report', 'delivery'])
        imported = self.current()['review']
        self.assertEqual(read(self.root / imported['path'])['platform_author'], 'reviewer-account')
        latest = self.field(source, '## 需求 spec', '理由', '第二轮已独立核对验收结果。')
        item = self.post(latest)
        code, again = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 0, again)
        self.assertTrue(again['reused'])
        self.assertEqual(self.current()['review'], imported)
        code, registered = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, registered)
        self.assertNotEqual(self.current()['review'], imported)
        code, again = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 0, again)
        self.assertEqual(again['steps'][0]['step'], 'acceptance')
        review = read(self.root / self.current()['review']['path'])
        self.assertEqual(review['platform_url'], item['url'])
        self.assertEqual(review['spec']['summary'], '第二轮已独立核对验收结果。')
        import reviews
        registered = reviews._state(self.root, self.url)['latest']
        self.assertEqual(registered['submitted_at'], item['updated_at'])
        self.assertEqual(registered['platform_review'], {key: item[key] for key in ('url', 'updated_at')})

    def test_platform_review_by_the_change_author_account_is_accepted_and_recorded(self):
        # Only the reviewer name is checked against the implementation owner; platform accounts are recorded.
        source = self.prepare()
        self.platform['items'][1]['kind'] = 'comment'
        item = self.post(source, author='implementer-account')
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        review = read(self.root / self.current()['review']['path'])
        self.assertEqual((review['platform_author'], review['platform_url']), ('implementer-account', item['url']))

    def test_deliver_keeps_a_newer_local_submission_including_legacy_registration(self):
        import reviews
        from common import write
        source = self.prepare()
        self.post(source)
        local = self.field(source, '## 需求 spec', '理由', '本地最后提交的独立评审。')
        self.draft_path().write_text(local)
        code, submitted = self.command('review', '--task', self.url, '--submit', '--out', '.tw/local/local-review.json')
        self.assertEqual(code, 0, submitted)
        editor = reviews.locations(self.root, self.url)[1]
        state = read(editor)
        self.assertEqual(state['latest']['submitted_at'], submitted['submitted_at'])
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                if legacy:
                    state['latest'].pop('submitted_at', None)
                    for row in state['submitted'].values():
                        row.pop('submitted_at', None)
                    write(editor, state)
                code, delivered = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
                self.assertEqual(code, 0, delivered)
                self.assertEqual(self.current()['review'], submitted['artifact'])
                if delivered.get('reused'):
                    self.assertEqual(delivered['artifact'], self.current()['delivery'])
                else:
                    self.assertNotIn('review', [row['step'] for row in delivered['steps']])

    def test_deliver_reuses_the_same_platform_submission_including_legacy_registration(self):
        import reviews
        from common import write
        source = self.prepare()
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                if legacy:
                    editor = reviews.locations(self.root, self.url)[1]
                    state = read(editor)
                    for row in [state['latest'], *state['submitted'].values()]:
                        row.pop('submitted_at', None)
                        row.pop('platform_review', None)
                    write(editor, state)
                code, delivered = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
                self.assertEqual(code, 0, delivered)
                self.assertEqual(self.current()['review'], submitted['artifact'])
                if delivered.get('reused'):
                    self.assertEqual(delivered['artifact'], self.current()['delivery'])
                else:
                    self.assertNotIn('review', [row['step'] for row in delivered['steps']])

    def missing_submission_time(self, platform):
        import reviews
        from common import write
        source = self.prepare()
        self.post(source)
        self.draft_path().write_text(source)
        flags = ['--from-platform'] if platform else ['--submit']
        code, submitted = self.command('review', '--task', self.url, *flags)
        self.assertEqual(code, 0, submitted)
        self.post(source)
        editor = reviews.locations(self.root, self.url)[1]
        state = read(editor)
        for row in [state['latest'], *state['submitted'].values()]:
            row.pop('submitted_at', None)
            row.pop('platform_review', None)
        write(editor, state)
        for name in ('request.json', 'response.json'):
            (self.root / submitted['request_directory'] / name).unlink()
        code, refused = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['error_code'], 'invalid-or-incomplete-input', refused)
        self.assertIn('登记记录', refused['problem'])
        self.assertIn(submitted['artifact']['path'], refused['problem'])
        if platform:
            self.assertEqual(refused['next_action'], 'tw team review --task ' + self.url + ' --from-platform')
        else:
            self.assertIn('变更请求评审', refused['next_action'])
            self.assertIn('--from-platform', refused['next_action'])
            self.assertIn('tw team deliver', refused['next_action'])

    def test_missing_local_submission_time_reports_registration_input_error(self):
        self.missing_submission_time(platform=False)

    def test_missing_platform_submission_time_reports_registration_input_error(self):
        self.missing_submission_time(platform=True)

    def test_deliver_stops_at_review_when_newest_platform_binding_is_stale(self):
        source = self.prepare()
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        self.post(source)
        code, refused = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['stopped_at'], 'review')
        self.assertEqual([row['step'] for row in refused['steps']], ['review'])
        self.assertIn('源码', refused['problem'])
        self.assertNotIn(refused['problem'], refused['next_action'])
        self.assertIn('tw team run --task ' + self.url, refused['next_action'])
        self.assertIn('tw team review --task ' + self.url, refused['next_action'])
        self.assertEqual(refused['next_action'], refused['steps'][0]['result']['next_action'])
        self.assertEqual(self.current()['review'], submitted['artifact'])

    def test_deliver_uses_updated_time_when_an_earlier_platform_entry_is_edited(self):
        source = self.prepare()
        first = self.post(source)
        self.post(self.field(source, '## 需求 spec', '理由', '后来创建的评审。'))
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        first.update(body=self.field(source, '## 需求 spec', '理由', '最晚更新的评审。'), updated_at='2026-01-02T00:00:00Z')
        self.response()
        code, delivered = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 0, delivered)
        review = read(self.root / self.current()['review']['path'])
        self.assertEqual((review['platform_url'], review['spec']['summary']), (first['url'], '最晚更新的评审。'))

    def test_status_closed_task_reports_last_records_and_open_task_checks_current_source(self):
        source = self.prepare()
        self.post(source)
        code, delivered = self.command('deliver', '--task', self.url, '--reason', '本次沿用已有知识。')
        self.assertEqual(code, 0, delivered)
        code, before = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, before)
        (self.root / 'app.py').write_text('def add(a,b): return sum((a,b))\n')
        self.platform['state'] = 'closed'
        self.response()
        code, closed = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, closed)
        self.assertEqual(closed['summary'], '任务已关闭')
        self.assertEqual(closed['task_phase'], 'closed')
        self.assertIsNone(closed['next_step'])
        self.assertEqual(closed['next_action'], '任务已关闭')
        self.assertEqual([row['state'] for row in closed['steps']], ['done'] * 7)
        self.assertEqual(closed['publication'], before['publication'])
        self.assertNotIn('源码已变', '\n'.join(closed['step_lines']))
        code, pending = self.command('scenarios', 'pending', '--task', self.url)
        self.assertEqual(code, 0, pending)
        self.assertEqual(pending['task_phase'], 'closed')
        self.assertEqual(pending['summary'], '任务已关闭')
        self.assertEqual(pending['pending'], [])
        self.platform['state'] = 'open'
        self.response()
        code, opened = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, opened)
        self.assertEqual(opened['task_phase'], 'delivered')
        (self.root / 'app.py').write_text('def add(a,b): return a+b+1\n')
        code, failed = self.command('run', '--task', self.url)
        self.assertEqual(code, 1, failed)
        self.platform['state'] = 'closed'
        self.response()
        self.profile['checks'] = {}
        self.profile['required_checks']['code'] = []
        import test_workflow as fixtures
        fixtures.write_config(self.root, self.profile)
        code, closed = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, closed)
        self.assertEqual(closed['summary'], '任务已关闭')
        self.assertEqual(next(row['state'] for row in closed['steps'] if row['id'] == 'run'), 'failed')

    def test_closed_status_reads_pre_scenario_snapshot_as_records(self):
        from common import write, artifact
        self.prepare()
        group = self.current()
        path = self.root / group['design']['path']
        value = read(path)
        value['sections'][1]['data']['scenario'] = {'roles': ['用户'], 'steps': ['旧格式']}
        value['sections'][1]['data'].pop('scenarios')
        write(path, value)
        group['design'] = artifact(self.root, path)
        write(self.current_path(), group)
        self.platform['state'] = 'closed'
        self.response()
        code, closed = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, closed)
        self.assertEqual(closed['summary'], '任务已关闭')
        self.assertEqual(closed['task_phase'], 'closed')
        self.assertIsNone(closed['next_step'])
        self.assertNotIn('stale', [row['state'] for row in closed['steps']])

    def test_platform_entry_cannot_be_mixed_with_a_local_file_or_submit(self):
        source = self.prepare()
        self.post(source)
        for extra in (('--file', str(self.draft_path())), ('--submit',)):
            with self.subTest(extra=extra):
                code, refused = self.command('review', '--task', self.url, '--from-platform', *extra)
                self.assertNotEqual(code, 0, refused)
                self.assertIsNone(self.current()['review'])

    def test_latest_mismatched_draft_or_binding_is_rejected_without_falling_back(self):
        source = self.prepare()
        self.post(source)
        for changed in (source.replace('"draft_id": "', '"draft_id": "0'),
                        source.replace('"task_digest": "', '"task_digest": "0')):
            with self.subTest(changed=changed[:40]):
                self.post(changed)
                code, refused = self.command('review', '--task', self.url, '--from-platform')
                self.assertEqual(code, 1, refused)
                self.assertEqual(refused['error_code'], 'review-incomplete')
                self.assertEqual(refused['section'], '绑定')
                self.assertIsNone(self.current()['review'])

    def test_platform_review_must_use_the_current_local_draft_even_when_source_is_identical(self):
        source = self.prepare()
        self.post(source)
        self.draft_path().rename(self.draft_path().with_name('saved-review.md'))
        code, fresh = self.command('review', '--task', self.url)
        self.assertEqual(code, 0, fresh)
        self.assertNotEqual(self.draft_path().read_text(), source)
        code, refused = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['error_code'], 'review-binding-stale')
        self.assertIn('tw team review', refused['next_action'])
        self.assertIsNone(self.current()['review'])

    def test_source_change_rejects_platform_markdown_and_retains_existing_name_check(self):
        source = self.prepare()
        self.post(self.field(source, '## 评审信息', '评审人', 'bob'))
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        code, refused = self.command('deliver', '--task', self.url, '--reason', 'No knowledge change.')
        self.assertEqual(code, 1, refused)
        self.assertIn('Reviewer must not be the implementation owner', refused['problem'])
        (self.root / 'app.py').write_text('def add(a,b):\n    return sum((a,b))\n')
        self.post(source)
        code, refused = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['error_code'], 'review-binding-stale')
        self.assertIn('tw team review', refused['next_action'])

    def test_platform_rechecks_and_issue_history_follow_local_submission_rules(self):
        source = self.prepare()
        issue = '\n### 问题 Q-platform\n- 编号：Q-platform\n- 负责人：carol\n- 影响范围：A1\n- 阻塞阶段：acceptance\n- 状态：open\n- 摘要：需要补查边界。\n'
        self.post(source.replace('## 风险', issue + '\n## 风险'))
        code, initial = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, initial)
        (self.root / 'app.py').write_text('def add(a,b):\n    return sum((a,b))\n')
        self.run_checks()
        pending = self.draft_path().read_text()
        self.assertIn('Q-platform', pending)
        self.assertIn('- 复核：待复核', pending)
        self.post(pending)
        code, refused = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 1, refused)
        self.assertIn('逐项复核', refused['problem'])
        confirmed = pending.replace('- 复核：待复核', '- 复核：已复核')
        self.post(confirmed)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        self.assertEqual(read(self.root / initial['artifact']['path'])['findings'],
                         read(self.root / submitted['artifact']['path'])['findings'])

    def test_simple_task_platform_review_carries_its_combined_approval_through_delivery(self):
        source = self.prepare('simple')
        source = self.field(source, '## 评审信息', '批准方案与代码', '是')
        self.post(source)
        code, delivered = self.command('deliver', '--task', self.url, '--reason', 'No knowledge change.')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'], delivered)

    def test_platform_submission_retry_is_idempotent_including_generated_approval(self):
        source = self.prepare('simple')
        source = self.field(source, '## 评审信息', '批准方案与代码', '是')
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform', '--request-id', 'platform-retry')
        self.assertEqual(code, 0, submitted)
        code, again = self.command('review', '--task', self.url, '--from-platform', '--request-id', 'platform-retry')
        self.assertEqual(code, 0, again)
        self.assertEqual(again, submitted)
        self.platform['items'][-1]['body'] = self.field(source, '## 需求 spec', '理由', '本次意见有变化。')
        self.response()
        code, refused = self.command('review', '--task', self.url, '--from-platform', '--request-id', 'platform-retry')
        self.assertEqual(code, 1, refused)
        self.assertIn('Request ID', refused['problem'])

    def test_published_review_author_and_original_body_are_rechecked_at_acceptance(self):
        source = self.prepare()
        item = self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        original = copy.deepcopy(item)
        for change in ({'body': source + '\nEdited after importing.\n'}, {'author': 'implementer-account'}):
            with self.subTest(change=next(iter(change))):
                item.update(original)
                item.update(change)
                self.response()
                code, refused = self.command('accept', '--task', self.url)
                self.assertEqual(code, 1, refused)
                self.assertIn('平台评审', refused['problem'])
                self.assertEqual(self.current()['review'], submitted['artifact'])

    def test_deliver_without_a_bound_platform_review_stops_before_acceptance(self):
        self.prepare()
        self.post('A discussion without the generated Markdown.')
        code, refused = self.command('deliver', '--task', self.url, '--reason', 'No knowledge change.')
        self.assertEqual(code, 1, refused)
        self.assertEqual(refused['stopped_at'], 'review')
        self.assertEqual([row['step'] for row in refused['steps']], ['review'])
        self.assertEqual(refused['steps'][0]['result']['error_code'], 'review-not-submitted')
        self.assertIn(self.draft_path().relative_to(self.root).as_posix(), refused['next_action'])
        self.assertIsNone(self.current()['review'])


    def test_local_task_in_a_platform_project_does_not_detour_to_platform_review(self):
        self.profile['platform'] = {'argv': [sys.executable, str(Path(__file__).with_name('platform_fixture.py'))],
                                   'operations': ['task', 'commit', 'reference']}
        environment = patch.dict(os.environ, {'TW_PLATFORM_EXIT': '1', 'TW_PLATFORM_STDERR': 'platform must not be called'})
        environment.start()
        self.addCleanup(environment.stop)
        self.base.start(self, 'simple')
        self.run_checks()
        code, refused = self.command('deliver', '--task', self.task['id'], '--reason', 'No knowledge change.')
        self.assertEqual(code, 1, refused)
        self.assertNotIn('review', [row['step'] for row in refused['steps']])
        self.assertNotEqual(refused.get('stopped_at'), 'review')
        self.assertNotIn('platform must not be called', json.dumps(refused, ensure_ascii=False))

if __name__ == '__main__':
    unittest.main()
