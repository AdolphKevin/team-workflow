"""Approval drafts select the task's pending work or its complete combined consent."""
import copy
import unittest
from unittest.mock import patch

import test_pending_sections as pending
import test_four_command_delivery as four
import test_coordination as shared
from common import read, write
import coordination
import designs
import plan_fixtures as plans
from platform_fixtures import transport
from tw_runtime.team import platform_script


class LocalApprovalDefaults(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, command = base.setUp, base.git, base.check, base.configure, base.command
    revise = pending.PendingSections.revise

    def draft(self, *extra):
        return self.command('approval-draft', '--task', '.tw/local/task.json',
                            '--design', '.tw/local/design.md', '--reviewer', 'carol', *extra)

    def test_default_design_draft_covers_exactly_pending_sections(self):
        self.revise()
        code, result = self.draft('--approval', '.tw/local/approval.json', '--design-history', '.tw/local/before.md')
        self.assertEqual(code, 0, result)
        approval = read(self.root / result['artifact']['path'])
        self.assertEqual(set(approval['sections']), {'A1', 'T1'})

    def test_no_pending_design_and_current_combined_produce_no_record(self):
        self.configure('medium')
        write(self.root / '.tw/local/approved.json', designs.approval_draft(self.design, 'carol'))
        code, result = self.draft('--approval', '.tw/local/approved.json', '--mode', 'plan')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['summary'], '没有需要批准的章节')
        self.assertNotIn('artifact', result)
        self.assertNotIn('record', result)
        code, first = self.draft('--approval', '.tw/local/approved.json', '--mode', 'combined')
        self.assertEqual(code, 0, first)
        approval = read(self.root / first['artifact']['path'])
        self.assertEqual(set(approval['sections']), {'scope-global', 'A1', 'T1'})
        code, again = self.draft('--approval', first['artifact']['path'], '--mode', 'combined')
        self.assertEqual(code, 0, again)
        self.assertEqual(again['summary'], '没有需要批准的章节')
        self.assertNotIn('artifact', again)
        (self.root / 'app.py').write_text('def add(a,b): return sum([a,b])\n')
        code, changed = self.draft('--approval', first['artifact']['path'], '--mode', 'combined')
        self.assertEqual(code, 0, changed)
        self.assertEqual(set(read(self.root / changed['artifact']['path'])['sections']), {'scope-global', 'A1', 'T1'})

    def test_sections_flag_and_record_section_ids_override_default(self):
        self.revise()
        for flags, expected in [(['--sections', 'T1,A1'], {'A1', 'T1'}),
                                (['--sections', 'all'], {'scope-global', 'A1', 'T1'})]:
            code, result = self.draft('--approval', '.tw/local/approval.json', '--design-history', '.tw/local/before.md', *flags)
            self.assertEqual(code, 0, result)
            self.assertEqual(set(read(self.root / result['artifact']['path'])['sections']), expected)
        write(self.root / '.tw/local/input.json', {'reviewer': 'carol', 'section_ids': ['T1']})
        code, result = self.command('approval-draft', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md',
            '--design-history', '.tw/local/before.md', '--record', '.tw/local/input.json')
        self.assertEqual(code, 0, result)
        self.assertEqual(set(read(self.root / result['artifact']['path'])['sections']), {'T1'})

    def test_local_readable_approval_lists_selected_titles_in_document_order(self):
        self.configure('medium')
        self.design['sections'] = [self.design['sections'][0], self.design['sections'][2], self.design['sections'][1]]
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        code, result = self.draft('--sections', 'A1,T1')
        self.assertEqual(code, 0, result)
        self.assertIn('T1 Implement、A1 Result', result.get('summary', ''))

    def test_combined_default_binds_actual_runs_and_needs_new_consent_after_a_new_run(self):
        self.configure('simple')
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md')
        self.assertEqual(code, 0, started)
        code, run = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, run)
        code, first = self.draft('--mode', 'combined')
        self.assertEqual(code, 0, first)
        approval = read(self.root / first['artifact']['path'])
        self.assertEqual(approval['run_refs'], [run['artifact']])
        code, empty = self.draft('--mode', 'combined', '--approval', first['artifact']['path'])
        self.assertEqual(code, 0, empty)
        self.assertEqual(empty['summary'], '没有需要批准的章节')
        code, newer = self.command('run', '--task', self.task['id'])
        self.assertEqual(code, 0, newer)
        code, draft = self.draft('--mode', 'combined')
        self.assertEqual(code, 0, draft)
        current = read(self.root / draft['artifact']['path'])
        self.assertEqual(set(current['sections']), {'scope-global', 'A1', 'T1'})
        self.assertEqual(current['run_refs'], sorted([run['artifact'], newer['artifact']], key=lambda row: row['path']))

    def test_default_includes_requested_changes_deferred_sections_and_pending_deletions(self):
        self.configure('medium')
        removed = {'id': 'old-api', 'type': 'interface', 'title': 'Old interface', 'body': 'Original API',
                   'data': {}, 'depends_on': []}
        self.design['sections'].insert(1, removed)
        self.design['sections'][-1]['depends_on'] = ['old-api']
        before = copy.deepcopy(self.design)
        plans.write_design(self.root / '.tw/local/before.md', before)
        approved = designs.approval_draft(before, 'carol')
        self.design['revision'] = 2
        self.design['sections'].remove(removed)
        self.design['sections'][-1]['depends_on'] = []
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        changes = designs.approval_draft(self.design, 'carol', decision='changes-requested', section_ids=['A1'], history=[before])
        deferred = designs.approval_draft(self.design, 'carol', decision='deferred', section_ids=['scope-global'], history=[before])
        for name, approval in [('approved', approved), ('changes', changes), ('deferred', deferred)]:
            write(self.root / ('.tw/local/' + name + '.json'), approval)
        options = ['--design-history', '.tw/local/before.md', '--approval', '.tw/local/approved.json',
                   '--approval', '.tw/local/changes.json', '--approval', '.tw/local/deferred.json']
        code, started = self.command('start', '--task', '.tw/local/task.json', '--design', '.tw/local/design.md', *options)
        self.assertEqual(code, 0, started)
        self.assertEqual([row['id'] for row in started['pending_sections']], ['scope-global', 'old-api', 'A1', 'T1'])
        self.assertEqual(started['pending_sections'][1]['reason'], '未评审')
        code, result = self.draft(*options)
        self.assertEqual(code, 0, result)
        approval = read(self.root / result['artifact']['path'])
        self.assertEqual(set(approval['sections']), {'scope-global', 'A1', 'T1'})
        self.assertEqual([row['id'] for row in approval['deletions']], ['old-api'])
        code, result = self.draft(*options, '--sections', 'old-api')
        self.assertEqual(code, 0, result)
        approval = read(self.root / result['artifact']['path'])
        self.assertEqual(approval['sections'], {})
        self.assertEqual([row['id'] for row in approval['deletions']], ['old-api'])

    def test_explicit_pending_deletion_can_override_task_scope(self):
        self.configure('medium')
        removed = {'id': 'old-api', 'type': 'interface', 'title': 'Other API', 'body': 'Obsolete API',
                   'data': {}, 'depends_on': []}
        self.design['sections'] += [removed, {'id': 'T2', 'type': 'task', 'title': 'Other work',
            'body': 'Another task', 'data': {'acceptance': ['A1'], 'scope': ['other.py'], 'blocked_by': []},
            'depends_on': ['old-api']}]
        before = copy.deepcopy(self.design)
        plans.write_design(self.root / '.tw/local/before.md', before)
        write(self.root / '.tw/local/approved.json', designs.approval_draft(before, 'carol'))
        self.design['revision'] = 2
        self.design['sections'].remove(removed)
        self.design['sections'][-1]['depends_on'] = []
        plans.write_design(self.root / '.tw/local/design.md', self.design)
        options = ['--design-history', '.tw/local/before.md', '--approval', '.tw/local/approved.json']
        code, empty = self.draft(*options)
        self.assertEqual(code, 0, empty)
        self.assertEqual(empty['summary'], '没有需要批准的章节')
        code, result = self.draft(*options, '--sections', 'old-api')
        self.assertEqual(code, 0, result)
        approval = read(self.root / result['artifact']['path'])
        self.assertEqual(approval['sections'], {})
        self.assertEqual([row['id'] for row in approval['deletions']], ['old-api'])


class PlatformApprovalDefaults(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def test_platform_pending_default_and_visible_document_order(self):
        self.prepare()
        self.design['sections'] = [self.design['sections'][0], self.design['sections'][2], self.design['sections'][1]]
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            approval = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.assertIn('scope-global Addition、T1 Implement addition、A1 Addition result', approval['markdown'])
            self.publish_fixture(approval, 'carol')
            empty = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.assertEqual(empty['summary'], '没有需要批准的章节')
            self.assertNotIn('record', empty)
            before = copy.deepcopy(self.design)
            self.design['revision'] = 2
            self.design['sections'][-1]['body'] = 'New acceptance text'
            self.publish_fixture(plans.draft_design(self.root, self.url, self.design), 'alice')
            draft = coordination.draft_approval(self.url, {'reviewer': 'carol'})
            self.assertEqual(set(draft['record']['approval']['sections']), {'A1', 'T1'})
