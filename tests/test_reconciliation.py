"""Restart published design history without reusing approvals for old revision numbers."""
import contextlib
import copy
import hashlib
import io
import json
import unittest

import test_markdown_records as fixtures
import test_workflow
from common import digest, read
import coordination
import designs
import workflow


class Reconciliation(unittest.TestCase):
    base = fixtures.MarkdownRecordCases
    setUp, git, check, prepare, body, github, publish_fixture, setup_record, draft = (
        base.setUp, base.git, base.check, base.prepare, base.body, base.github,
        base.publish_fixture, base.setup_record, base.draft)

    def command(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = workflow.main([*args, '--root', str(self.root), '--issue', self.url])
        return code, json.loads(out.getvalue())

    def old_history(self):
        self.setup_record()
        test_workflow.write_config(self.root, self.profile)
        previous = None
        for revision in (1, 2):
            self.design['revision'] = revision
            raw = designs.render(self.design).replace('- 验证：自动',
                '- 验证：自动；层级 journey；入口 app.add；环境 isolated-test；替身 无；隔离 isolated；隔离依据 无；用例 无')
            self.path.write_text(raw)
            self.git('add', 'docs/design.md')
            self.git('commit', '-qm', 'old verification syntax fixture')
            state = coordination.load(self.url, root=self.root)
            ref = {'id': self.design['id'], 'revision': revision, 'repository': 'github.com/example/project',
                   'path': 'docs/design.md', 'commit': self.git('rev-parse', 'HEAD').strip(),
                   'sha256': hashlib.sha256(raw.encode()).hexdigest()}
            record = {'data_version': 1, 'kind': 'design-record', 'task': self.url,
                      'creator': 'alice', 'requirements': state['requirements'],
                      'history_digest': state['history_digest'], 'previous': previous, 'design': ref}
            draft = coordination._draft_result('design', self.url, record)
            self.publish_fixture(draft, 'alice')
            previous = {'url': self.issue['comments_data'][-1]['html_url'], 'digest': digest(record)}
            state = coordination.load(self.url, root=self.root)
            approval = designs.approval_draft(self.design, 'old-reviewer', mode='design')
            row = {'data_version': 1, 'kind': 'approval-record', 'task': self.url,
                   'requirements': state['requirements'], 'history_digest': state['history_digest'],
                   'previous': state['approval_previous'], 'approval': approval}
            self.publish_fixture(coordination._draft_result('approval', self.url, row), 'old-reviewer')
        self.design['revision'] = 1
        self.path.write_text(designs.render(self.design))
        self.git('add', 'docs/design.md')
        self.git('commit', '-qm', 'current verification syntax fixture')

    def test_restart_ignores_old_designs_and_approvals_until_new_consent(self):
        self.old_history()
        before = coordination.load(self.url, root=self.root)
        self.assertIsNone(before['design'])
        self.assertIn('design-draft --reconcile', '；'.join(before['gaps']))
        for command, options in [('start', []), ('design-draft', ['--record', str(self.path)])]:
            with self.subTest(command=command):
                code, unreadable = self.command(command, *options)
                self.assertEqual(code, 1, unreadable)
                self.assertIn('design-draft --reconcile', unreadable['problem'])
        code, result = self.command('design-draft', '--record', str(self.path), '--reconcile', '改用当前验证格式')
        self.assertEqual(code, 0, result)
        drafted = read(self.root / result['artifact']['path'])
        self.assertEqual(drafted['record']['resolution'], {'history_digest': before['history_digest'], 'reason': '改用当前验证格式'})
        self.assertIsNone(drafted['record']['previous'])
        self.publish_fixture(drafted, 'alice')
        state = coordination.load(self.url, root=self.root)
        self.assertEqual((state['history'], state['approvals'], state['approval_records'], state['gaps']), ([], [], [], []))
        code, pending = self.command('start')
        self.assertEqual(code, 0, pending)
        self.assertFalse(pending['implementation_ready'], pending)
        self.assertEqual(pending['gaps'], [])
        code, result = self.command('approval-draft', '--reviewer', 'new-reviewer')
        self.assertEqual(code, 0, result)
        self.publish_fixture(read(self.root / result['artifact']['path']), 'new-reviewer')
        code, ready = self.command('start')
        self.assertEqual(code, 0, ready)
        self.assertTrue(ready['implementation_ready'], ready)
        self.assertEqual(ready['gaps'], [])

    def test_readable_history_can_restart_and_approval_cli_can_reconcile(self):
        self.setup_record()
        test_workflow.write_config(self.root, self.profile)
        self.publish_fixture(self.draft(), 'alice')
        first = coordination.draft_approval(self.url, {'reviewer': 'carol'})
        self.publish_fixture(first, 'carol')
        self.publish_fixture(first, 'carol')
        state = coordination.load(self.url, root=self.root)
        code, result = self.command('approval-draft', '--reviewer', 'carol', '--reconcile', '确认重复批准')
        self.assertEqual(code, 0, result)
        draft = read(self.root / result['artifact']['path'])
        self.assertEqual(draft['record']['resolution']['history_digest'], state['history_digest'])
        self.publish_fixture(draft, 'carol')
        self.assertEqual(coordination.load(self.url, root=self.root)['gaps'], [])
        code, result = self.command('design-draft', '--record', str(self.path), '--reconcile', '重启可读历史')
        self.assertEqual(code, 0, result)
        self.publish_fixture(read(self.root / result['artifact']['path']), 'alice')
        state = coordination.load(self.url, root=self.root)
        self.assertEqual((state['history'], state['approvals'], state['gaps']), ([], [], []))
