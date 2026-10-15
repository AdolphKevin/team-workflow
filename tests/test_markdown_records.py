"""M5: shared records name immutable Markdown in local git, never a second design."""
import copy
import hashlib
import unittest
from unittest.mock import patch

import test_coordination as fixtures
from common import Invalid, write
import coordination
import designs
from tw_runtime.team import platform_script
from platform_fixtures import transport


class MarkdownRecordCases(unittest.TestCase):
    base = fixtures.CoordinationCases
    setUp, git, check, prepare, body, github, publish_fixture = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github, base.publish_fixture)

    def setup_record(self):
        self.prepare()
        self.path = self.root / 'docs/design.md'
        self.path.parent.mkdir()
        self.raw = designs.render(self.design)
        self.path.write_text(self.raw)
        self.git('add', 'docs/design.md')
        self.git('commit', '-qm', 'publish Markdown fixture')
        self.transport = patch.object(platform_script, 'call', side_effect=transport(self.github))
        self.transport.start()
        self.addCleanup(self.transport.stop)

    def draft(self):
        return coordination.draft_design(self.url, self.design, path=self.path, root=self.root)

    def test_m5_record_contains_reference_and_pr_description_is_committed_source(self):
        self.setup_record()
        draft = self.draft()
        expected = {'id': self.design['id'], 'revision': 1, 'repository': 'github.com/example/project',
                    'path': 'docs/design.md', 'commit': self.git('rev-parse', 'HEAD').strip(),
                    'sha256': hashlib.sha256(self.raw.encode()).hexdigest()}
        self.assertEqual(draft['record']['design'], expected)
        # Reviewers read the original body; the JSON front matter becomes readable lines (no visible JSON).
        body = self.raw.split('\n---\n', 1)[1].lstrip('\n')
        self.assertTrue(draft['pr_description'].endswith(body))
        header = draft['pr_description'][:-len(body)]
        self.assertNotIn('{', header)
        self.assertNotRegex(draft['pr_description'], r'(?m)^(assessment|roles|design|task|revision):')
        for value in (self.design['id'], 'docs/design.md', expected['commit'][:7],
                      self.design['roles']['design_owner'], self.design['roles']['acceptance_owner']):
            self.assertIn(value, header)
        self.assertNotIn('sections', draft['record']['design'])
        self.publish_fixture(draft, 'alice')
        self.assertEqual(coordination.load(self.url, root=self.root)['design'], self.design)

    def test_m5_missing_commit_missing_file_and_bad_sha_are_separate_gaps(self):
        self.setup_record()
        draft = self.draft()
        for key, value, expected in [('commit', 'a' * 40, '先 fetch'),
                                     ('path', 'docs/missing.md', '不在提交'),
                                     ('sha256', 'b' * 64, 'sha256')]:
            with self.subTest(key=key):
                record = copy.deepcopy(draft['record'])
                record['design'][key] = value
                changed = coordination._draft_result('design', self.url, record)
                self.issue['comments_data'] = []
                self.publish_fixture(changed, 'alice')
                with patch.object(platform_script, 'commit', side_effect=AssertionError('must use local git')):
                    state = coordination.load(self.url, root=self.root)
                self.assertIsNone(state['design'])
                self.assertIn(expected, str(state['gaps']))

    def test_dirty_and_uncommitted_files_cannot_be_published(self):
        self.setup_record()
        self.path.write_text(self.raw + '\n未提交修改\n')
        with self.assertRaisesRegex(Invalid, '先提交'):
            self.draft()
        self.path = self.path.with_name('new.md')
        self.path.write_text(self.raw)
        with self.assertRaisesRegex(Invalid, '先提交'):
            self.draft()

    def test_description_is_never_a_published_record(self):
        self.setup_record()
        draft = self.draft()
        self.publish_fixture(draft, 'alice')
        self.issue['comments_data'][-1]['kind'] = 'change'
        state = coordination.load(self.url, issue=self.issue, root=self.root)
        self.assertIsNone(state['design'])
        self.assertEqual(state['gaps'], [])

    def test_staged_change_cannot_hide_behind_an_unchanged_working_file(self):
        self.setup_record()
        self.path.write_text(self.raw + '\n暂存修改\n')
        self.git('add', 'docs/design.md')
        self.path.write_text(self.raw)
        with self.assertRaisesRegex(Invalid, '先提交'):
            self.draft()

    def test_text_output_shows_both_reviewable_drafts(self):
        self.setup_record()
        import commands
        draft = self.draft()
        output = commands.readable(draft)
        self.assertIn(draft['pr_description'], output)
        self.assertIn(draft['markdown'], output)

    def test_status_and_start_surface_display_warning_without_blocking(self):
        self.setup_record()
        import contextlib
        import io
        import json
        import workflow
        import test_workflow
        from platform_fixtures import task_data
        test_workflow.write_config(self.root, self.profile)
        draft = self.draft()
        self.publish_fixture(draft, 'alice')
        self.publish_fixture(coordination.draft_approval(self.url, {'reviewer': 'carol'}), 'carol')
        # The description the tool generated (readable header + original body) is current: no warning.
        # start runs once (a second start would be a continuation with its own preconditions).
        for body, warned, commands in (('outdated', True, ('start', 'status')), (draft['pr_description'], False, ('status',))):
            normalized = task_data(self.issue)
            normalized['items'].append({'kind': 'change', 'url': self.url + '#description', 'body': body,
                'author': 'alice', 'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'})
            with patch.object(platform_script, 'call', return_value=normalized):
                for command in commands:
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = workflow.main([command, '--root', str(self.root), '--issue', self.url])
                    result = json.loads(output.getvalue())
                    with self.subTest(command=command, warned=warned):
                        self.assertEqual(code, 0, result)
                        self.assertTrue(result['implementation_ready'], result)
                        self.assertEqual('描述' in str(result.get('warnings', [])), warned, result.get('warnings'))

    def test_shared_repository_uses_existing_local_mapping(self):
        self.setup_record()
        draft = self.draft()
        self.publish_fixture(draft, 'alice')
        consumer = self.root / '.tw/local/consumer'
        consumer.mkdir(parents=True)
        import subprocess
        subprocess.run(['git', '-C', str(consumer), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(consumer), 'remote', 'add', 'origin', 'https://github.com/example/consumer.git'], check=True)
        state = coordination.load(self.url, issue=self.issue, root=consumer)
        self.assertIn('mapping', str(state['gaps']))
        (consumer / '.tw/local').mkdir(parents=True)
        import json
        (consumer / '.tw/local/repositories.json').write_text(json.dumps({'repositories': {'github.com/example/project': str(self.root)}}))
        state = coordination.load(self.url, issue=self.issue, root=consumer)
        self.assertEqual((state['design'], state['gaps']), (self.design, []))

    def test_description_mismatch_warns_without_changing_approval_decision(self):
        self.setup_record()
        self.publish_fixture(self.draft(), 'alice')
        self.issue['comments_data'].append({'html_url': self.url + '#change', 'body': 'Outdated display',
                                             'kind': 'change', 'user': {'login': 'alice'}})
        state = coordination.load(self.url, issue=self.issue, root=self.root)
        self.assertEqual(state['gaps'], [])
        self.assertIn('描述', str(state['warnings']))
        self.assertEqual(state['design'], self.design)


if __name__ == '__main__':
    unittest.main()
