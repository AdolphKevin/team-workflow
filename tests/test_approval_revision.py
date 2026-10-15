"""Optional approved commit binding, using local Git objects and content fingerprints."""
import plan_fixtures as plans
import json
import subprocess
import sys
import unittest

import test_four_command_delivery as four
import test_designs as plans
from common import read, write
import designs
import validation


class ApprovalRevision(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure = base.setUp, base.git, base.check, base.configure

    def command(self, *args):
        result = subprocess.run([sys.executable, str(four.TW), '--root', str(self.root), 'team', *args],
                                capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout) if result.stdout else {'problem': result.stderr}

    def test_approval_draft_cli_records_full_revision_for_plan(self):
        self.configure('medium')
        revision = self.git('rev-parse', 'HEAD').strip()
        code, result = self.command('approval-draft', '--task', '.tw/local/task.json',
            '--design', '.tw/local/design.md', '--reviewer', 'carol', '--mode', 'plan', '--revision', revision)
        self.assertEqual(code, 0, result)
        approval = read(self.root / result['artifact']['path'])
        self.assertEqual(approval['revision'], revision)
        status = designs.approval_status(self.design, [approval], changed_paths=['app.py'])
        self.assertTrue(status['fully_approved'], status)

    def status_with_revision(self, revision):
        approval = designs.approval_draft(self.design, 'carol', mode='combined', revision=revision,
                                         code_digest=validation.source_digest(self.root, self.profile), run_refs=[])
        write(self.root / '.tw/local/approval.json', approval)
        write(self.root / '.tw/local/report.json', {'design': '.tw/local/design.md',
            'approvals': ['.tw/local/approval.json'], 'runs': []})
        return self.command('status', '--task', '.tw/local/task.json', '--report', '.tw/local/report.json')

    def test_combined_revision_must_match_bound_source_and_missing_commit_is_a_gap(self):
        self.configure()
        revision = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'app.py').write_text('def add(a,b): return a-b\n')
        code, result = self.status_with_revision(revision)
        self.assertEqual(code, 0, result)  # status reports readiness without performing a gated action.
        self.assertIn('批准的提交与绑定的源码不一致', str(result['gaps']))
        self.assertFalse(result['combined_complete'])
        code, missing = self.status_with_revision('f' * 40)
        self.assertEqual(code, 0, missing)
        self.assertIn('本地没有批准的提交', str(missing['gaps']))

    def test_plan_revision_format_only_and_old_records_unchanged(self):
        design = plans.example()
        original = designs.approval_draft(design, 'carol')
        expected = designs.approval_status(design, [original], changed_paths=[])
        self.assertNotIn('revision', original)
        for revision in ('a' * 40, 'B' * 64):
            with self.subTest(revision=revision):
                recorded = {**original, 'revision': revision}
                self.assertEqual(designs.approval_status(design, [recorded], changed_paths=[]), expected)
        for revision in ('abc123', 'g' * 40, 'a' * 41, '', None, 42):
            with self.subTest(revision=revision):
                status = designs.approval_status(design, [{**original, 'revision': revision}], changed_paths=[])
                self.assertFalse(status['ok'])
                self.assertIn('完整提交号', str(status['gaps']))

    def test_combined_revision_uses_content_with_modes_links_and_reserved_files(self):
        self.configure()
        (self.root / 'binary.dat').write_bytes(b'\x00\xff\x80')
        executable = self.root / 'script.sh'
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        (self.root / 'link').symlink_to('binary.dat')
        self.git('add', '.')
        self.git('commit', '-qm', 'source content fixture')
        revision = self.git('rev-parse', 'HEAD').strip()
        knowledge = self.root / '.tw/overview.md'
        knowledge.write_text(knowledge.read_text() + '\nKnowledge does not change source content.\n')
        # Policy, knowledge and index changes are outside the source content binding.
        self.git('add', '.tw/overview.md')
        code, result = self.status_with_revision(revision)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['combined_complete'], result)
        executable.chmod(0o644)
        code, result = self.status_with_revision(revision)
        self.assertEqual(code, 0, result)
        self.assertIn('批准的提交与绑定的源码不一致', str(result['gaps']))


if __name__ == '__main__':
    unittest.main()
