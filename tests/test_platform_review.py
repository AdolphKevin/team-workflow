"""D4: reviewers publish the generated Markdown; CLI reads it through the project script."""
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
        body = 'Addition works.\n```team-workflow-task\n' + json.dumps(
            {'data_version': 1, 'parent': None, 'task': self.task}) + '\n```\n'
        self.platform = {'id': self.url, 'url': self.url, 'repository': 'code.example/group/project',
            'state': 'open', 'owners': ['bob'], 'items': [{'url': self.url, 'author': 'implementer-account',
            'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
            'kind': 'task', 'body': body}], 'raw': {'fixture': 'offline'}}
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        self.response()
        self.post(coordination.draft_design(self.url, self.design)['markdown'], 'change', 'implementer-account')
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

    def test_deliver_imports_platform_review_only_when_no_review_is_submitted(self):
        source = self.prepare()
        self.post(source)
        code, delivered = self.command('deliver', '--task', self.url, '--reason', 'No reusable knowledge change.')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'], delivered)
        self.assertEqual([row['step'] for row in delivered['steps']], ['review', 'acceptance', 'delivery-report', 'delivery'])
        imported = self.current()['review']
        self.assertEqual(read(self.root / imported['path'])['platform_author'], 'reviewer-account')
        # A later discussion with a malformed binding cannot replace an already submitted review.
        self.post('<!-- tw-review:binding:start --> broken')
        code, again = self.command('deliver', '--task', self.url)
        self.assertEqual(code, 0, again)
        self.assertEqual(self.current()['review'], imported)
        self.assertNotIn('review', [row['step'] for row in again['steps']])

    def test_platform_identity_requires_change_and_a_different_author(self):
        source = self.prepare()
        self.post(source, author='implementer-account')
        code, refused = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 1, refused)
        self.assertIn('平台评审作者不能是变更请求作者', refused['problem'])
        self.assertIsNone(self.current()['review'])
        self.platform['items'][-1]['author'] = 'reviewer-account'
        self.platform['items'][1]['kind'] = 'comment'
        self.response()
        code, refused = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 1, refused)
        self.assertIn('无法核对平台身份', refused['problem'])
        self.assertIsNone(self.current()['review'])

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
                self.assertIn('重新生成复核稿', refused['problem'])
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
        self.assertIn('重新生成复核稿', refused['problem'])
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
        self.assertIn('重新生成复核稿', refused['problem'])

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
        self.assertIn('review 条目', refused['problem'])
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
