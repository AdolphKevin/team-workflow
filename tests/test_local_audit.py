"""A4: audit reports manual local material without counting managed directories as manual."""
import os
from unittest.mock import patch

from tw_fixtures import Case, tree_state, write


class LocalAudit(Case):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'config-home')})
        environment.start()
        self.addCleanup(environment.stop)
        self.initialize()

    def test_a4_audit_lists_manual_entries_with_exact_sizes_and_writes_nothing(self):
        write(self.root, '.tw/local/manual/first.txt', '1234567')
        write(self.root, '.tw/local/manual/nested/second.txt', 'abcde')
        write(self.root, '.tw/local/note.txt', 'note')
        for name in ('tasks', 'batches', 'imports', 'validation-active', 'agents', 'cache'):
            write(self.root, f'.tw/local/{name}/example.txt', 'managed')
        write(self.root, '.tw/local/repositories.json', '{}')
        write(self.root, '.tw/local/.maintenance-lock', '{}')
        before = tree_state(self.root)
        code, report = self.tw_json('audit')
        self.assertEqual(code, 0, report)
        self.assertEqual(report['local'].get('unmanaged'), [
            {'path': '.tw/local/manual', 'bytes': 12}, {'path': '.tw/local/note.txt', 'bytes': 4}])
        code, text, err = self.tw('audit')
        self.assertEqual(code, 0, err)
        self.assertIn('不归工具管理', text)
        self.assertIn('.tw/local/manual：12 字节', text)
        self.assertEqual(tree_state(self.root), before)

    def test_a4_absent_local_directory_has_no_manual_entries(self):
        code, report = self.tw_json('audit')
        self.assertEqual(code, 0, report)
        self.assertEqual(report['local'].get('unmanaged'), [])
        self.assertFalse((self.root / '.tw/local').exists())
