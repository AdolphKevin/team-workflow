"""G3：实际命令的证据字节与各交付文字中的双通道摘录。"""
import hashlib
import unittest

import test_four_command_delivery as fixtures
from common import read
from test_workflow import write_config


class RawOutput(unittest.TestCase):
    base = fixtures.FourCommandDelivery
    setUp, git, check, command, configure, start, run_checks = (
        base.setUp, base.git, base.check, base.command, base.configure, base.start, base.run_checks)
    current_path, current, draft_path, field, completed, submit = (
        base.current_path, base.current, base.draft_path, base.field, base.completed, base.submit)

    def test_empty_stdout_and_stderr_bytes_survive_capture_and_delivery(self):
        self.start()
        raw = b'first\r\nlast\xff\r\n'
        self.check('import os; os.write(2, ' + repr(raw) + ')')
        write_config(self.root, self.profile)
        ran = self.run_checks()
        record = read(self.root / ran['artifact']['path'])
        for channel, expected in (('stdout', b''), ('stderr', raw)):
            ref = next(ref for ref in record['results'][0]['artifacts'] if ref['path'].endswith('/' + channel + '.txt'))
            self.assertEqual((self.root / ref['path']).read_bytes(), expected)
            self.assertEqual(ref['sha256'], hashlib.sha256(expected).hexdigest())
        draft = self.draft_path().read_text()
        self.assertIn('原始输出摘录', draft)
        self.assertIn('stderr', draft)
        self.assertIn('last', draft)
        self.assertNotIn('(empty)', draft)
        self.assertEqual(self.submit()[0], 0)
        code, delivered = self.command('deliver', '--task', self.task['id'], '--reason', '现有知识已覆盖')
        self.assertEqual(code, 0, delivered)
        self.assertIn('stderr', delivered['summary_markdown'])
        self.assertIn('last', delivered['summary_markdown'])

    def test_both_empty_streams_show_no_output_only_in_display(self):
        self.start()
        self.check('pass')
        write_config(self.root, self.profile)
        ran = self.run_checks()
        record = read(self.root / ran['artifact']['path'])
        for ref in record['results'][0]['artifacts']:
            self.assertEqual((self.root / ref['path']).read_bytes(), b'')
        self.assertIn('（无输出）', self.draft_path().read_text())
