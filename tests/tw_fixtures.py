"""Temporary git repositories for team-knowledge (`tw`) tests."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/team-knowledge/scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from tw_runtime import cli  # noqa: E402


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(base, name='orders', remote='git@github.com:acme/orders.git'):
    root = Path(base) / name
    root.mkdir(parents=True)
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.email', 'test@example.com')
    git(root, 'config', 'user.name', 'test')
    git(root, 'remote', 'add', 'origin', remote)
    return root


def write(root, name, text):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def commit(root, message='change'):
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')


def entry(title, body, **fields):
    lines = [f'title: {json.dumps(title, ensure_ascii=False)}']
    lines += [f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in fields.items()]
    return '---\n' + '\n'.join(lines) + f'\n---\n# {title}\n\n{body.strip()}\n'


def tree_state(root):
    """Every file under root with its bytes, to prove read-only commands write nothing."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in Path(root).rglob('*')
            if p.is_file() and '.git' not in p.relative_to(root).parts}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = make_repo(self.base)
        write(self.root, 'README.md', '# Orders\n')
        write(self.root, 'internal/orders/service.go', 'package orders\nfunc Create() {}\n')
        write(self.root, 'internal/brand/archive.go', 'package brand\nfunc Archive() {}\n')
        write(self.root, 'tests/test_orders.py', 'def test_inventory_rollback():\n    pass\n')
        self.head = commit(self.root, 'init')

    def tw(self, *args, root=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(['--root', str(root or self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def tw_json(self, *args, root=None):
        code, out, err = self.tw(*args, '--format', 'json', root=root)
        return code, json.loads(out) if out.strip() else {'stderr': err}

    def initialize(self, root=None, overview='订单服务负责下单与库存预留。'):
        root = root or self.root
        code, _, err = self.tw('init', '--apply', root=root)
        self.assertEqual(code, 0, err)
        write(root, '.tw/overview.md', entry('订单服务总览', overview, source=['self:README.md']))

    def verified(self, commit=None):
        return {'self': {'commit': commit or self.head, 'date': '2026-10-14'}}
