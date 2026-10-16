"""A task's own design file is process material, not an implementation change that needs a task scope."""
import copy
import unittest

import test_four_command_delivery as four
import plan_fixtures as plans
from common import write
import designs
import validation


class DesignFileScope(unittest.TestCase):
    base = four.FourCommandDelivery
    setUp, git, check, configure, command, run_checks, submit = (
        base.setUp, base.git, base.check, base.configure, base.command, base.run_checks, base.submit)
    current_path, draft_path, current, field, completed = (
        base.current_path, base.draft_path, base.current, base.field, base.completed)

    def start_with_committed_design(self):
        # Real case (independent trial, Issue #5): the design is committed with the task as the docs say,
        # and delivery then refused it as a change outside every task scope.
        self.configure('medium')
        plans.write_design(self.root / 'docs/design.md', self.design)
        write(self.root / '.tw/local/plan-approval.json',
              designs.approval_draft(self.design, 'carol', 'Confirmed the business plan', mode='design'))
        code, result = self.command('start', '--task', '.tw/local/task.json', '--design', 'docs/design.md',
                                    '--approval', '.tw/local/plan-approval.json')
        self.assertEqual(code, 0, result)

    def test_own_design_file_is_left_out_of_the_changed_paths(self):
        self.configure('medium')
        plans.write_design(self.root / 'docs/design.md', self.design)
        other = copy.deepcopy(self.design)
        other['id'] = 'D-other'
        plans.write_design(self.root / 'docs/other.md', other)
        foreign = copy.deepcopy(self.design)
        foreign['task_id'] = 'TASK-elsewhere'
        plans.write_design(self.root / 'docs/foreign.md', foreign)
        (self.root / 'docs/notes.md').write_text('---\ndesign: "D-add"\n')
        changed = validation.changed_paths(self.root, self.task, design=self.design)
        self.assertNotIn('docs/design.md', changed)
        for path in ('docs/other.md', 'docs/foreign.md', 'docs/notes.md'):
            self.assertIn(path, changed)
        self.assertIn('docs/design.md', validation.changed_paths(self.root, self.task))

    def test_committed_own_design_does_not_block_acceptance(self):
        self.start_with_committed_design()
        self.run_checks()
        code, result = self.submit()
        self.assertEqual(code, 0, result)
        code, result = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 0, result)
        self.assertTrue(result['business_accepted'], result)

    def test_another_design_file_still_needs_a_task_scope(self):
        self.start_with_committed_design()
        other = copy.deepcopy(self.design)
        other['id'] = 'D-other'
        plans.write_design(self.root / 'docs/other.md', other)
        self.run_checks()
        code, result = self.submit()
        self.assertEqual(code, 0, result)
        code, result = self.command('accept', '--task', self.task['id'])
        self.assertEqual(code, 1, result)
        self.assertIn('docs/other.md', result['problem'])
        self.assertNotIn('docs/design.md', result['problem'])


if __name__ == '__main__':
    unittest.main()
