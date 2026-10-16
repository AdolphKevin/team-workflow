"""复验 U1、U2：命令参数与任务评审提交方式。"""
import json
import unittest

from tw_fixtures import Case
import test_trial_rework
import test_four_command_delivery
from common import read, write


class KnowledgeRoot(Case):
    def test_u1_all_knowledge_commands_accept_root_after_subcommand(self):
        self.initialize()
        cases = [('init', []), ('check', []), ('brief', ['--task', '核对知识', '--index']),
                 ('audit', []), ('read', ['--list']),
                 ('new', ['rule', '--title', '核对来源', '--scope', 'self:internal/**', '--source', 'self:README.md']),
                 ('cache', ['--clear']), ('version', [])]
        for command, options in cases:
            for placement in ('before', 'after'):
                args = [command, *options]
                if command == 'new':
                    args += ['--slug', 'root-' + placement]
                if command not in ('cache', 'version'):
                    args += ['--format', 'json']
                if placement == 'after':
                    args += ['--root', str(self.root)]
                with self.subTest(command=command, placement=placement):
                    try:
                        code, out, err = self.tw(*args)
                    except SystemExit as exc:
                        self.fail('知识命令参数尚待识别：' + command + '；退出码 ' + str(exc.code))
                    self.assertEqual(code, 0, err or out)
                    self.assertTrue(json.loads(out))

    def test_u1_subcommand_root_takes_precedence_like_team_root(self):
        missing = self.base / 'absent'
        try:
            code, out, err = self.tw('init', '--root', str(self.root), '--format', 'json', root=missing)
        except SystemExit as exc:
            self.fail('子命令 root 尚待识别；退出码 ' + str(exc.code))
        self.assertEqual(code, 0, err or out)
        code, out, err = self.tw('init', '--root', str(missing), '--format', 'json')
        self.assertEqual(code, 2)
        self.assertIn(str(missing), json.loads(out)['problem'])


class PlatformSubmission(unittest.TestCase):
    peer = test_trial_rework.PlatformTrial
    base = peer.base
    setUp, git, check, configure, response, post, prepare, command = (
        peer.setUp, peer.git, peer.check, peer.configure, peer.response, peer.post, peer.prepare, peer.command)
    current_path, current, draft_path, run_checks, field, completed = (
        peer.current_path, peer.current, peer.draft_path, peer.run_checks, peer.field, peer.completed)

    def post(self, body, kind='review', author='reviewer-account'):
        item = self.peer.post(self, body, kind, author)
        if kind == 'review' and '<!-- tw-review:binding:start -->' in body:
            item['updated_at'] = f'2099-01-01T00:00:{len(self.platform["items"]):02d}Z'
            self.response()
        return item

    def assert_platform_submission(self, action, path=None):
        self.assertIn(path or self.draft_path().relative_to(self.root).as_posix(), action)
        self.assertIn('变更请求评审', action)
        self.assertIn('tw team deliver', action)
        self.assertNotIn('--submit', action)

    def test_u2_run_and_status_choose_platform_publication(self):
        self.prepare('simple')
        code, status = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, status)
        for name, action in [('run', self.ran['next_action']), ('status', status['next_action']),
                             ('review-step', next(row['next_command'] for row in status['steps'] if row['id'] == 'review'))]:
            with self.subTest(source=name):
                self.assert_platform_submission(action)

    def test_u2_missing_approval_uses_publication_and_keeps_plan_approval_path(self):
        source = self.prepare('simple')
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        code, result = self.command('deliver', '--task', self.url, '--reason', '沿用已有知识。')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['steps'][-1]['result']['error_code'], 'approval-incomplete', result)
        self.assert_platform_submission(result['next_action'])
        self.assertIn('tw team approval-draft', result['next_action'])
        self.assertIn('--mode plan', result['next_action'])

    def test_u2_review_errors_use_the_actual_input_path_for_publication(self):
        self.prepare('simple')
        path = '.tw/local/named-review.md'
        (self.root / path).write_text(self.draft_path().read_text())
        code, result = self.command('review', '--task', self.url, '--submit', '--file', path)
        self.assertEqual(code, 1, result)
        self.assertEqual(result['error_code'], 'review-incomplete')
        self.assert_platform_submission(result['next_action'], path)

    def test_u2_status_recomputes_prior_repair_from_its_error_code(self):
        source = self.prepare('simple')
        self.post(source)
        code, submitted = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, submitted)
        code, failed = self.command('accept', '--task', self.url)
        self.assertEqual(code, 1, failed)
        self.assertEqual(failed['error_code'], 'approval-incomplete')
        response = self.root / failed['request_directory'] / 'response.json'
        prior = read(response)
        prior['source_next_action'] = prior['next_action'] = 'tw team review --task ' + self.url + ' --submit'
        write(response, prior)
        code, status = self.command('status', '--task', self.url)
        self.assertEqual(code, 0, status)
        self.assert_platform_submission(status['next_action'])
        self.assertEqual(read(response), prior)

    def test_u2_missing_local_registration_can_follow_platform_recovery(self):
        import reviews
        source = self.prepare('simple')
        source = self.field(source, '## 评审信息', '批准方案与代码', '是')
        self.draft_path().write_text(source)
        code, local = self.command('review', '--task', self.url, '--submit')
        self.assertEqual(code, 0, local)
        self.post(source)
        editor = reviews.locations(self.root, self.url)[1]
        state = read(editor)
        for row in [state['latest'], *state['submitted'].values()]:
            row.pop('submitted_at', None)
        write(editor, state)
        for name, key in [('request.json', 'started_at'), ('response.json', 'finished_at')]:
            path = self.root / local['request_directory'] / name
            value = read(path)
            value.pop(key)
            write(path, value)
        code, failed = self.command('deliver', '--task', self.url, '--reason', '沿用已有知识。')
        self.assertEqual(code, 1, failed)
        self.assert_platform_submission(failed['next_action'])
        self.assertIn('--from-platform', failed['next_action'])
        self.post(source)
        code, imported = self.command('review', '--task', self.url, '--from-platform')
        self.assertEqual(code, 0, imported)
        code, delivered = self.command('deliver', '--task', self.url, '--reason', '沿用已有知识。')
        self.assertEqual(code, 0, delivered)
        self.assertTrue(delivered['delivery_complete'])


class LocalSubmission(unittest.TestCase):
    base = test_four_command_delivery.FourCommandDelivery
    setUp, git, check, configure, command, start, run_checks, current_path, current, draft_path = (
        base.setUp, base.git, base.check, base.configure, base.command, base.start, base.run_checks,
        base.current_path, base.current, base.draft_path)

    def test_u2_local_task_keeps_local_submission(self):
        self.start()
        result = self.run_checks()
        self.assertIn('tw team review --task ' + self.task['id'] + ' --submit', result['next_action'])
        self.assertNotIn('变更请求评审', result['next_action'])


if __name__ == '__main__':
    unittest.main()
