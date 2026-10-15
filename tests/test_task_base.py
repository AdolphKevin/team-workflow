"""A task's changes are measured from where it last met the default branch, like a pull request's diff."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_workflow  # noqa: F401  (puts the team runtime on sys.path)
import validation
import knowledge


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class TaskBase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        git(self.root, 'config', 'user.name', 'Fixture')
        (self.root / 'app.py').write_text('base\n')
        (self.root / '.tw').mkdir()
        (self.root / '.tw/lessons').mkdir()
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'base')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        git(self.root, 'checkout', '-qb', 'feature')
        (self.root / 'task.py').write_text('task change\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'task change')
        git(self.root, 'checkout', '-q', 'main')
        (self.root / 'tool.py').write_text('change made on main meanwhile\n')
        (self.root / '.tw/lessons/main-lesson.md').write_text('lesson added on main\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'main change')
        git(self.root, 'checkout', '-q', 'feature')
        git(self.root, 'merge', '-q', '--no-edit', 'main')
        self.task = {'base': self.base}

    def track_default(self):
        # What a clone sets up: the remote default branch, here pointing at main's tip.
        git(self.root, 'update-ref', 'refs/remotes/origin/main', git(self.root, 'rev-parse', 'main'))
        git(self.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')

    def test_changes_merged_from_the_default_branch_are_not_the_task_s(self):
        # Real case (Issue #5): after merging main, acceptance flagged main's files as outside every task scope.
        self.track_default()
        self.assertEqual(validation.changed_paths(self.root, self.task), ['task.py'])
        self.assertEqual(knowledge.changed_since(self.root, self.base), set())

    def test_task_knowledge_is_still_counted(self):
        self.track_default()
        (self.root / '.tw/lessons/task-lesson.md').write_text('written by the task\n')
        self.assertEqual(knowledge.changed_since(self.root, self.base), {'.tw/lessons/task-lesson.md'})

    def test_without_a_remote_default_branch_the_recorded_base_is_used(self):
        self.assertEqual(validation.changed_paths(self.root, self.task), ['task.py', 'tool.py'])
        self.assertEqual(knowledge.changed_since(self.root, self.base), {'.tw/lessons/main-lesson.md'})

    def test_a_default_branch_that_does_not_contain_the_base_is_ignored(self):
        git(self.root, 'checkout', '-q', '--orphan', 'unrelated')
        git(self.root, 'rm', '-rq', '--cached', '.')
        (self.root / 'other.txt').write_text('unrelated history\n')
        git(self.root, 'add', 'other.txt')
        git(self.root, 'commit', '-qm', 'unrelated')
        git(self.root, 'update-ref', 'refs/remotes/origin/main', git(self.root, 'rev-parse', 'HEAD'))
        git(self.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        git(self.root, 'checkout', '-qf', 'feature')
        git(self.root, 'clean', '-qfd')
        self.assertEqual(validation.changed_paths(self.root, self.task), ['task.py', 'tool.py'])


if __name__ == '__main__':
    unittest.main()
