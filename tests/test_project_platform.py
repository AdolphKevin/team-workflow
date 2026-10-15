"""Project onboarding acceptance against the captured GitHub REST responses.

The archive was not supplied: download tests use a synthetic ZIP and its own
digest, explicitly replacing only size/digest in copied artifact metadata.
Submitted reviews have no real sample; their REST shape follows GitHub's review
API, with a separate synthetic GraphQL lastEditedAt response.
"""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'skills/team-knowledge/scripts/tw_runtime/team'),
                str(ROOT / 'skills/team-knowledge/scripts')]
from common import Invalid
from tw_runtime.team import platform_script
import portable

SAMPLES = Path(__file__).with_name('fixtures') / 'project_platform'
SLUG = 'AdolphKevin/team-workflow'
REPO = 'github.com/' + SLUG
ISSUE = 'https://github.com/' + SLUG + '/issues/2'
PULL = 'https://github.com/' + SLUG + '/pull/3'
SHA = 'e117f8b25b438f3957a62add9d1134bd59d217fb'
API = 'repos/' + SLUG
LOCATOR = {'run_id': 38719357681, 'attempt': 1, 'job_id': 116369807488, 'artifact_id': 11964392562}


def sample(name):
    return json.loads((SAMPLES / name).read_text())


class ProjectPlatform(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='project-platform-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / '.tw').mkdir()
        shutil.copyfile(ROOT / '.tw/platform.py', self.root / '.tw/platform.py')
        config = {'platform': {'argv': [sys.executable, '.tw/platform.py'], 'timeout': 30,
                              'operations': ['task', 'commit', 'reference', 'ci-result']}}
        (self.root / '.tw/config.json').write_text(json.dumps(config))
        client = self.root / 'bin/gh'
        client.parent.mkdir()
        client.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path('
                          + repr(str(Path(__file__).with_name('project_platform_gh.py')))
                          + ', run_name="__main__")\n')
        client.chmod(0o755)
        self.responses = self.root / 'responses.json'
        self.log = self.root / 'requests.jsonl'
        self.download_number = 0
        self.routes = {}
        self.route(API + '/issues/2', sample('issue-2.json'))
        self.route(API + '/issues/2/comments?per_page=100', sample('issue-2-comments.json'))
        self.route(API + '/pulls?state=all&per_page=100', [[sample('pull-3.json')]])
        self.route(API + '/pulls/3', sample('pull-3.json'))
        self.routes['graphql:' + sample('pull-3.json')['node_id']] = {'node_of': API + '/pulls/3', 'lastEditedAt': None}
        self.route(API + '/issues/3/comments?per_page=100', sample('pull-3-issue-comments.json'))
        self.route(API + '/pulls/3/reviews?per_page=100', sample('pull-3-reviews.json'))
        self.route(API + '/pulls/3/comments?per_page=100', sample('pull-3-review-comments.json'))
        self.route(API + '/commits/' + SHA, sample('commit-e117f8b.json'))
        self.route(API + '/contents/README.md?ref=' + SHA, sample('contents-readme.json'))
        self.route(API + '/actions/runs/38719357681', sample('run.json'))
        self.jobs_endpoint = API + '/actions/runs/38719357681/attempts/1/jobs?per_page=100'
        self.artifacts_endpoint = API + '/actions/runs/38719357681/artifacts?per_page=100'
        self.route(self.jobs_endpoint, [sample('run-jobs.json')])
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(zipfile.ZipInfo('offline-fixture.txt', (2026, 10, 15, 0, 0, 0)),
                             'Synthetic download; the real archive was not captured.\n')
        self.archive = stream.getvalue()
        artifacts = sample('run-artifacts.json')
        for artifact in artifacts['artifacts']:
            artifact['digest'] = 'sha256:' + hashlib.sha256(self.archive).hexdigest()
            artifact['size_in_bytes'] = len(self.archive)
            self.routes[API + f'/actions/artifacts/{artifact["id"]}/zip'] = {
                'base64': base64.b64encode(self.archive).decode()}
        self.route(self.artifacts_endpoint, [artifacts])
        environment = patch.dict(os.environ, {'PATH': str(client.parent) + os.pathsep + os.environ.get('PATH', ''),
                    'TW_PROJECT_GH_RESPONSES': str(self.responses), 'TW_PROJECT_GH_LOG': str(self.log)})
        environment.start()
        self.addCleanup(environment.stop)
        platform_script.clear_cache()
        self.addCleanup(platform_script.clear_cache)

    def route(self, endpoint, body):
        self.routes[endpoint] = {'body': body}

    def body(self, endpoint):
        return self.routes[endpoint]['body']

    def save(self):
        self.responses.write_text(json.dumps(self.routes))
        platform_script.clear_cache()

    def call(self, operation, *arguments):
        self.save()
        # call executes the actual project script, then runs platform_script.validate.
        return platform_script.call(self.root, operation, *arguments)

    def read_task(self):
        return self.call('task', '--id', ISSUE)

    def requests(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def import_ci(self, locator=None):
        self.save()
        self.download_number += 1
        directory = self.root / f'download-{self.download_number}'
        directory.mkdir()
        # Also exercise the tool's ownership, success and time-range checks.
        result = portable.provider(self.root, locator if locator is not None else LOCATOR, directory)
        self.assertEqual((directory / result['archive']).read_bytes(), self.archive)
        return result

    def unlink_pull(self):
        for page in self.body(API + '/issues/2/comments?per_page=100'):
            for row in page:
                row['body'] = row['body'].replace(PULL, '无关联变更请求')

    def test_registered_operations_and_unchanged_sample_task(self):
        config = json.loads((ROOT / '.tw/config.json').read_text())
        self.assertEqual(config['platform']['argv'], ['python3', '.tw/platform.py'])
        self.assertEqual(config['platform']['operations'], ['task', 'commit', 'reference', 'ci-result'])
        result = self.read_task()
        self.assertEqual((result['id'], result['url'], result['repository'], result['state'], result['owners']),
                         (ISSUE, ISSUE, REPO, 'closed', ['AdolphKevin']))
        self.assertEqual(len(result['items']), 9)  # Issue + seven real comments + PR description.
        self.assertEqual(result['items'][0]['body'], sample('issue-2.json')['body'])
        expected = {row['html_url']: row for row in sample('issue-2-comments.json')[0]}
        expected[PULL] = sample('pull-3.json')
        self.assertEqual({row['url'] for row in result['items'][1:]}, set(expected))
        for row in result['items'][1:]:
            original = expected[row['url']]
            # The PR description was never edited (lastEditedAt null); its REST updated_at is later activity.
            edited = original['created_at'] if row['url'] == PULL else original['updated_at']
            self.assertEqual((row['body'], row['author'], row['created_at'], row['updated_at']),
                             (original['body'], original['user']['login'], original['created_at'], edited))
            self.assertEqual(row['kind'], 'change' if row['url'] == PULL else 'comment')
        self.assertEqual(result['raw'][0]['response'], sample('issue-2.json'))
        self.assertEqual(result['raw'][1]['response'], sample('issue-2-comments.json'))

    def test_without_linked_pull_returns_only_issue_and_its_comments(self):
        self.unlink_pull()
        result = self.read_task()
        self.assertEqual([row['kind'] for row in result['items']], ['task'] + ['comment'] * 7)
        self.assertNotIn(API + '/pulls/3', [r['endpoint'] for r in self.requests()])

    def test_closing_keyword_finds_pull_when_issue_does_not_link_it(self):
        self.unlink_pull()
        for body in ('Closes #2', 'Fixes AdolphKevin/team-workflow#2', 'Resolves ' + ISSUE):
            with self.subTest(body=body):
                pull = self.body(API + '/pulls/3')
                pull['body'] = body
                self.route(API + '/pulls?state=all&per_page=100', [[copy.deepcopy(pull)]])
                self.assertEqual([row['url'] for row in self.read_task()['items'] if row['kind'] == 'change'], [PULL])
        for body in ('Closes #20', 'See #2', 'Closes Other/repository#2', 'Closes ' + ISSUE + '0'):
            with self.subTest(unrelated=body):
                self.body(API + '/pulls?state=all&per_page=100')[0][0]['body'] = body
                self.assertFalse(any(row['kind'] == 'change' for row in self.read_task()['items']))

    def test_pagination_reads_all_pages_and_sorts_equal_timestamps_by_url(self):
        rows = self.body(API + '/issues/2/comments?per_page=100')[0]
        rows[1]['created_at'] = rows[2]['created_at']
        rows[1]['updated_at'] = rows[2]['updated_at']
        self.route(API + '/issues/2/comments?per_page=100', [rows[4:], rows[:4]])
        unrelated = copy.deepcopy(sample('pull-3.json'))
        unrelated.update(id=99, number=99, body='Unrelated')
        self.route(API + '/pulls?state=all&per_page=100', [[unrelated], [sample('pull-3.json')]])
        result = self.read_task()
        self.assertEqual(len(result['items']), 9)
        order = [(platform_script.timestamp(row['created_at']), row['url']) for row in result['items'][1:]]
        self.assertEqual(order, sorted(order))
        list_requests = [r for r in self.requests() if '?' in r['endpoint']]
        self.assertTrue(list_requests)
        self.assertTrue(all(r['paginate'] and r['slurp'] for r in list_requests))

    def test_pr_comments_inline_comments_and_documented_review_shape_keep_full_body(self):
        original = sample('issue-2-comments.json')[0][0]
        discussion = copy.deepcopy(original)
        discussion.update(id=81, html_url=PULL + '#issuecomment-81', body='讨论原文\r\n')
        inline = copy.deepcopy(original)
        inline.update(id=82, html_url=PULL + '#discussion_r82', body='行内意见\n')
        review = {'id': 83, 'node_id': 'PRR_fixture83', 'user': {'login': 'independent-reviewer'},
                  'html_url': PULL + '#pullrequestreview-83', 'state': 'APPROVED',
                  'submitted_at': '2026-10-15T09:00:00Z',
                  'body': '# 评审\r\n\n<!-- 完整绑定区 -->\n```json\n{"bound":"原文"}\n```\n'}
        self.route(API + '/issues/3/comments?per_page=100', [[discussion]])
        self.route(API + '/pulls/3/comments?per_page=100', [[inline]])
        self.route(API + '/pulls/3/reviews?per_page=100', [[review]])
        self.body(API + '/pulls/3').update(comments=1, review_comments=1)
        metadata = {'id': review['node_id'], 'url': review['html_url'], 'body': review['body'], 'lastEditedAt': None}
        self.route('graphql:PRR_fixture83', {'data': {'node': metadata}})
        result = self.read_task()
        rows = {row['url']: row for row in result['items']}
        for source in (discussion, inline, review):
            self.assertEqual(rows[source['html_url']]['body'], source['body'])
        self.assertEqual(rows[review['html_url']]['kind'], 'review')
        self.assertEqual(rows[review['html_url']]['updated_at'], review['submitted_at'])
        metadata['lastEditedAt'] = '2026-10-15T08:00:00Z'
        self.assertEqual(self.read_task()['items'][-1]['updated_at'], review['submitted_at'])
        metadata['lastEditedAt'] = '2026-10-15T10:00:00Z'
        self.assertEqual(self.read_task()['items'][-1]['updated_at'], metadata['lastEditedAt'])
        metadata['body'] = 'changed during the read'
        with self.assertRaisesRegex(Invalid, '正文在读取期间变化'):
            self.read_task()

    def test_change_request_edit_time_is_its_body_edit_not_later_activity(self):
        # Real case (PR #6): a review moved the PR's REST updated_at although its description was never edited.
        pull = self.body(API + '/pulls/3')
        self.assertNotEqual(pull['updated_at'], pull['created_at'])
        change = next(row for row in self.read_task()['items'] if row['kind'] == 'change')
        self.assertEqual(change['updated_at'], pull['created_at'])
        self.routes['graphql:' + pull['node_id']]['lastEditedAt'] = '2026-10-11T00:00:00Z'
        change = next(row for row in self.read_task()['items'] if row['kind'] == 'change')
        self.assertEqual(change['updated_at'], '2026-10-11T00:00:00Z')

    def test_redirected_issue_is_refused_without_following_its_comments(self):
        self.body(API + '/issues/2')['html_url'] = ISSUE.replace('/2', '/200')
        with self.assertRaisesRegex(Invalid, '重定向'):
            self.read_task()
        self.assertEqual([row['endpoint'] for row in self.requests()], [API + '/issues/2'])

    def test_comment_deletion_or_pagination_failure_never_becomes_an_empty_list(self):
        endpoint = API + '/issues/2/comments?per_page=100'
        for status in (404, 403, 500):
            with self.subTest(status=status):
                self.routes[endpoint] = {'status': status}
                with self.assertRaisesRegex(Invalid, f'HTTP {status}') as error:
                    self.read_task()
                self.assertNotIn('private diagnostic', str(error.exception))
        self.route(endpoint, [[]])
        with self.assertRaisesRegex(Invalid, '评论数量'):
            self.read_task()

    def test_duplicate_pages_and_missing_author_are_refused(self):
        endpoint = API + '/issues/2/comments?per_page=100'
        original = sample('issue-2-comments.json')[0]
        self.route(endpoint, [original, original])
        with self.assertRaisesRegex(Invalid, '重复对象'):
            self.read_task()
        self.route(endpoint, [original])
        original[0]['user'] = None
        with self.assertRaisesRegex(Invalid, '字段缺失或类型错误'):
            self.read_task()

    def test_commit_uses_git_author_and_author_time_from_real_response(self):
        result = self.call('commit', '--repo', REPO, '--revision', SHA)
        self.assertEqual(result, {'exists': True, 'revision': SHA,
            'author': 'AdolphKevin <27267992+AdolphKevin@users.noreply.github.com>', 'time': '2026-10-15T10:18:33Z'})
        self.body(API + '/commits/' + SHA)['sha'] = '0' * 40
        with self.assertRaisesRegex(Invalid, '提交号与请求不同'):
            self.call('commit', '--repo', REPO, '--revision', SHA)
        # A commit the platform does not have is reported, not refused: the contract allows null author and time.
        # GitHub answers an unknown full SHA with HTTP 422 (checked against the real API); 404 is kept for safety.
        for status in (422, 404):
            self.routes[API + '/commits/' + SHA] = {'status': status}
            with self.subTest(status=status):
                self.assertEqual(self.call('commit', '--repo', REPO, '--revision', SHA),
                                 {'exists': False, 'revision': SHA, 'author': None, 'time': None})

    def test_references_cover_task_change_commit_pinned_file_and_comment(self):
        comment = sample('issue-2-comments.json')[0][0]
        self.route(API + f'/issues/comments/{comment["id"]}', comment)
        cases = [(ISSUE, 'task'), (PULL, 'change'), (comment['html_url'], 'comment'),
                 ('https://github.com/' + SLUG + '/commit/' + SHA, 'commit'),
                 ('https://github.com/' + SLUG + '/blob/' + SHA + '/README.md', 'file')]
        for url, kind in cases:
            with self.subTest(url=url):
                result = self.call('reference', '--url', url)
                self.assertTrue(result['reachable'])
                self.assertEqual(result['kind'], kind)
                if kind in ('commit', 'file'):
                    self.assertEqual(result['revision'], SHA)  # Contents.sha is a blob, not a commit.

    def test_deleted_comment_404_never_falls_back_to_reachable_issue(self):
        comment = sample('issue-2-comments.json')[0][0]
        self.routes[API + f'/issues/comments/{comment["id"]}'] = {'status': 404}
        self.assertEqual(self.call('reference', '--url', comment['html_url']), {'reachable': False, 'kind': 'comment'})
        platform_script.clear_cache()
        with self.assertRaisesRegex(Invalid, '无法读取引用'):
            platform_script.reference(self.root, comment['html_url'])
        self.assertTrue(all(r['endpoint'].startswith(API + '/issues/comments/') for r in self.requests()))

    def test_reference_review_and_inline_comment_use_their_own_endpoints(self):
        for suffix, endpoint in (('#discussion_r51', '/pulls/comments/51'),
                                 ('#pullrequestreview-52', '/pulls/3/reviews/52')):
            with self.subTest(suffix=suffix):
                self.route(API + endpoint, {'html_url': PULL + suffix})
                self.assertEqual(self.call('reference', '--url', PULL + suffix), {'reachable': True, 'kind': 'comment'})
        with self.assertRaisesRegex(Invalid, '不能退回父对象'):
            self.call('reference', '--url', ISSUE + '#unrecognized-comment')

    def test_ci_real_metadata_maps_every_provenance_field_and_both_matrix_jobs(self):
        for locator, version in ((LOCATOR, '3.13'),
                ({**LOCATOR, 'job_id': 116369807445, 'artifact_id': 11963703679}, '3.10')):
            with self.subTest(version=version):
                result = self.import_ci(locator)
                receipt = result['provenance']
                raw_job = next(row for row in sample('run-jobs.json')['jobs'] if row['id'] == locator['job_id'])
                raw_artifact = next(row for row in sample('run-artifacts.json')['artifacts'] if row['id'] == locator['artifact_id'])
                self.assertEqual(receipt, {'repository': REPO, 'revision': SHA,
                    'run': {'id': 38719357681, 'attempt': 1, 'latest_attempt': 1, 'succeeded': True,
                            'url': 'https://github.com/' + SLUG + '/actions/runs/38719357681'},
                    'job': {'id': raw_job['id'], 'name': raw_job['name'], 'run_id': raw_job['run_id'],
                            'attempt': raw_job['run_attempt'], 'started_at': raw_job['started_at'],
                            'finished_at': raw_job['completed_at'], 'succeeded': True},
                    'artifact': {'id': raw_artifact['id'], 'run_id': raw_artifact['workflow_run']['id'],
                                 'revision': raw_artifact['workflow_run']['head_sha'],
                                 'created_at': raw_artifact['created_at'], 'expired': False,
                                 'digest': 'sha256:' + hashlib.sha256(self.archive).hexdigest()}})
                manifest = {'run_context': {'repository': REPO, 'run_id': '38719357681', 'attempt': '1', 'job': 'validate'},
                            'started_at': '2026-10-15T10:19:00Z', 'finished_at': '2026-10-15T10:20:00Z'}
                portable.provider_binding(locator, receipt, manifest)
                self.assertEqual(receipt['job']['name'], f'validate ({version})')

    def test_ci_jobs_and_artifacts_are_paginated_not_truncated(self):
        jobs = sample('run-jobs.json')
        self.route(self.jobs_endpoint, [{'total_count': 2, 'jobs': jobs['jobs'][:1]},
                                        {'total_count': 2, 'jobs': jobs['jobs'][1:]}])
        artifacts = self.body(self.artifacts_endpoint)[0]['artifacts']
        self.route(self.artifacts_endpoint, [{'total_count': 2, 'artifacts': artifacts[1:]},
                                             {'total_count': 2, 'artifacts': artifacts[:1]}])
        self.import_ci()

    def test_ci_expired_artifact_is_refused_before_download(self):
        self.body(self.artifacts_endpoint)[0]['artifacts'][0]['expired'] = True
        with self.assertRaisesRegex(Invalid, '产物已过期'):
            self.import_ci()
        self.assertFalse(any(r['endpoint'].endswith('/zip') for r in self.requests()))

    def test_ci_job_from_other_attempt_run_or_revision_is_refused(self):
        original = copy.deepcopy(self.body(self.jobs_endpoint))
        for changes in ({'run_attempt': 2}, {'run_id': 99}, {'head_sha': '0' * 40}, {'id': 99}):
            with self.subTest(changes=changes):
                self.route(self.jobs_endpoint, copy.deepcopy(original))
                self.body(self.jobs_endpoint)[0]['jobs'][1].update(changes)
                with self.assertRaisesRegex(Invalid, '不属于'):
                    self.import_ci()

    def test_ci_cannot_pair_another_matrix_artifact_even_when_times_overlap(self):
        with self.assertRaisesRegex(Invalid, 'Python 版本或尝试不一致'):
            self.import_ci({**LOCATOR, 'artifact_id': 11963703679})
        self.body(self.jobs_endpoint)[0]['jobs'][1]['name'] = 'Run behavior regressions (3.13)'
        with self.assertRaisesRegex(Invalid, 'validate 标识'):
            self.import_ci()

    def test_ci_wrong_artifact_run_revision_digest_or_time_is_refused(self):
        original = copy.deepcopy(self.body(self.artifacts_endpoint))
        cases = [({'expired': 'false'}, '字段缺失或类型错误'),
                 ({'created_at': '2026-10-15T11:00:00Z'}, '时间范围'),
                 ({'digest': 'sha256:' + '0' * 64}, '摘要不一致')]
        for changes, error in cases:
            with self.subTest(changes=changes):
                self.route(self.artifacts_endpoint, copy.deepcopy(original))
                self.body(self.artifacts_endpoint)[0]['artifacts'][0].update(changes)
                with self.assertRaisesRegex(Invalid, error):
                    self.import_ci()
        for changes in ({'id': 99}, {'head_sha': '0' * 40}, {'repository_id': 99}):
            with self.subTest(relation=changes):
                self.route(self.artifacts_endpoint, copy.deepcopy(original))
                self.body(self.artifacts_endpoint)[0]['artifacts'][0]['workflow_run'].update(changes)
                with self.assertRaisesRegex(Invalid, '产物不属于'):
                    self.import_ci()

    def test_ci_requires_latest_successful_run_and_successful_job(self):
        endpoint = API + '/actions/runs/38719357681'
        for changes in ({'run_attempt': 2}, {'status': 'in_progress'}, {'conclusion': 'failure'},
                        {'id': 99}, {'path': '.github/workflows/unrelated.yml'}):
            with self.subTest(changes=changes):
                self.route(endpoint, sample('run.json'))
                self.body(endpoint).update(changes)
                with self.assertRaises(Invalid):
                    self.import_ci()
        self.route(endpoint, sample('run.json'))
        self.body(self.jobs_endpoint)[0]['jobs'][1]['conclusion'] = 'failure'
        with self.assertRaisesRegex(Invalid, '任务尚未成功完成'):
            self.import_ci()

    def test_ci_output_and_locator_cannot_overwrite_existing_files(self):
        directory = self.root / 'nonempty'
        directory.mkdir()
        target = directory / 'keep.txt'
        target.write_text('keep')
        with self.assertRaisesRegex(Invalid, '现有空目录'):
            self.call('ci-result', '--locator', json.dumps(LOCATOR), '--output', str(directory))
        self.assertEqual(target.read_text(), 'keep')
        for locator in ({**LOCATOR, 'attempt': True}, {**LOCATOR, 'extra': 1},
                        {**LOCATOR, 'artifact_id': '../escape'}, {'run_id': 1}):
            with self.subTest(locator=locator), self.assertRaises(Invalid):
                self.import_ci(locator)

    def test_script_failure_has_no_partial_json_or_private_gh_diagnostic(self):
        self.routes[API + '/issues/2'] = {'status': 403}
        self.save()
        result = subprocess.run([sys.executable, str(self.root / '.tw/platform.py'), 'task', '--id', ISSUE],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, f'GitHub 只读请求失败（HTTP 403）：{API}/issues/2\n')


if __name__ == '__main__':
    unittest.main()
