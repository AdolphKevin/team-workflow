import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'skills/playwright-acceptance/scripts'))

import to_scenarios  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'playwright_acceptance'
REPORT = FIXTURES / 'report.json'
FINDINGS = ['--finding', 'SOP-02-P02=Q3', '--finding', 'SOP-02-P04=Q4']


def load_report():
    return json.loads(REPORT.read_text(encoding='utf-8'))


def run(out, extra=()):
    args = ['--report', str(REPORT), '--out', str(out), '--executor', 'tester-a', *FINDINGS, *extra]
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = to_scenarios.main(args)
    return code, stderr.getvalue()


def read_rows(out):
    return [json.loads(line) for line in (Path(out) / 'results.jsonl').read_text(encoding='utf-8').splitlines()]


class HelperTests(unittest.TestCase):
    def test_scenario_id_is_first_token(self):
        self.assertEqual(to_scenarios.scenario_id('SOP-02-P01 人工接管'), 'SOP-02-P01')
        self.assertEqual(to_scenarios.scenario_id('REG-7 回归'), 'REG-7')
        self.assertIsNone(to_scenarios.scenario_id('没有编号的用例'))
        self.assertIsNone(to_scenarios.scenario_id(''))

    def test_classify_blocked_prefix_and_ansi(self):
        self.assertEqual(to_scenarios.classify({'status': 'passed'}), 'pass')
        self.assertEqual(to_scenarios.classify({'status': 'skipped'}), 'skip')
        self.assertEqual(to_scenarios.classify({'status': 'timedOut', 'error': {'message': 'Test timeout'}}), 'fail')
        blocked = {'status': 'failed', 'error': {'message': 'Error: \x1b[31m受阻：人机验证\x1b[39m'}}
        self.assertEqual(to_scenarios.classify(blocked), 'blocked')
        with self.assertRaises(to_scenarios.ConvertError):
            to_scenarios.classify({'status': 'weird'})

    def test_executed_at_is_end_time_with_timezone(self):
        value = to_scenarios.executed_at({'startTime': '2026-10-19T06:14:02.860Z', 'duration': 2500})
        self.assertEqual(value, '2026-10-19T06:14:05+00:00')
        parsed = datetime.fromisoformat(value)
        self.assertIsNotNone(parsed.tzinfo)


class ConvertTests(unittest.TestCase):
    def test_statuses_actual_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'round-1'
            code, stderr = run(out)
            self.assertEqual(code, 0, stderr)
            rows = {row['scenario']: row for row in read_rows(out)}
            self.assertEqual(sorted(rows), ['SOP-02-P01', 'SOP-02-P02', 'SOP-02-P03', 'SOP-02-P04'])
            self.assertIn('没有编号的用例', stderr)

            p01 = rows['SOP-02-P01']
            self.assertEqual(p01['status'], 'pass')
            self.assertEqual(p01['executor'], 'tester-a')
            self.assertEqual(p01['executed_at'], '2026-10-19T06:14:05+00:00')
            self.assertIn('已完成 3 步', p01['actual'])
            self.assertIn('发送 123456789', p01['actual'])
            self.assertEqual(p01['evidence'], ['evidence/SOP-02-P01/01-home.png', 'evidence/SOP-02-P01/02-video.webm'])
            for ref in p01['evidence']:
                self.assertTrue((out / ref).is_file(), ref)
            self.assertNotIn('finding', p01)

            p02 = rows['SOP-02-P02']
            self.assertEqual(p02['status'], 'blocked')
            self.assertEqual(p02['finding'], 'Q3')
            self.assertTrue(p02['actual'].startswith('受阻：客户离线'))
            self.assertEqual(p02['evidence'], ['evidence/SOP-02-P02/01-error-context.md'])

            p03 = rows['SOP-02-P03']
            self.assertEqual(p03['status'], 'fail')
            self.assertIn('第 2 步「核对会话列表」失败', p03['actual'])
            self.assertNotIn('\x1b', p03['actual'])
            self.assertIn('toBeVisible', p03['actual'])
            self.assertEqual(p03['evidence'], ['evidence/SOP-02-P03/01-list.png'])
            self.assertEqual((out / p03['evidence'][0]).read_bytes(), b'png')

            p04 = rows['SOP-02-P04']
            self.assertEqual(p04['status'], 'skip')
            self.assertEqual(p04['finding'], 'Q4')
            self.assertEqual(p04['evidence'], [])
            self.assertIn('测试店铺没有离线客户', p04['actual'])

            for row in rows.values():
                self.assertFalse(set(row) - to_scenarios_keys())

    def test_blocked_without_finding_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = to_scenarios.main(['--report', str(REPORT), '--out', str(out), '--executor', 'x', '--finding', 'SOP-02-P04=Q4'])
            self.assertEqual(code, 2)
            self.assertIn('SOP-02-P02', stderr.getvalue())
            self.assertFalse((out / 'results.jsonl').exists())

    def test_pass_without_evidence_fails(self):
        report = load_report()
        spec = report['suites'][0]['specs'][0]
        spec['tests'][0]['results'][0]['attachments'] = []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(to_scenarios.ConvertError) as ctx:
                to_scenarios.convert(report, Path(tmp) / 'r', 'x', {'SOP-02-P02': 'Q3', 'SOP-02-P04': 'Q4'}, report_dir=FIXTURES)
            self.assertIn('SOP-02-P01', str(ctx.exception))

    def test_pending_cross_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            code, stderr = run(out, ['--pending', str(FIXTURES / 'pending.json'), '--session', 'round-1'])
            self.assertEqual(code, 0, stderr)
            self.assertIn('SOP-02-P05', stderr)
            self.assertTrue(all(row['session'] == 'round-1' for row in read_rows(out)))
        report = load_report()
        report['suites'][0]['specs'][0]['title'] = 'SOP-99-X01 不在清单'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(to_scenarios.ConvertError) as ctx:
                to_scenarios.convert(report, Path(tmp) / 'r', 'x', {'SOP-02-P02': 'Q3', 'SOP-02-P04': 'Q4'},
                                     pending_ids=['SOP-02-P01', 'SOP-02-P02', 'SOP-02-P03', 'SOP-02-P04'], report_dir=FIXTURES)
            self.assertIn('SOP-99-X01', str(ctx.exception))

    def test_multiple_tests_per_scenario_take_worst(self):
        report = load_report()
        specs = report['suites'][0]['specs']
        specs[1]['title'] = 'SOP-02-P01 第二条路径'
        with tempfile.TemporaryDirectory() as tmp:
            rows, _ = to_scenarios.convert(report, Path(tmp) / 'r', 'x', {'SOP-02-P01': 'Q3', 'SOP-02-P04': 'Q4'}, report_dir=FIXTURES)
            row = {r['scenario']: r for r in rows}['SOP-02-P01']
            self.assertEqual(row['status'], 'blocked')
            self.assertIn('第二条路径', row['actual'])
            self.assertEqual(len(row['evidence']), 3)
            self.assertEqual(row['executed_at'], '2026-10-19T06:14:11+00:00')

    def test_large_evidence(self):
        report = load_report()
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / 'big.webm'
            with big.open('wb') as handle:
                handle.truncate(to_scenarios.EVIDENCE_LIMIT_BYTES + 1)
            spec = report['suites'][0]['specs'][0]
            spec['tests'][0]['results'][0]['attachments'].append({'name': 'big', 'contentType': 'video/webm', 'path': str(big)})
            findings = {'SOP-02-P02': 'Q3', 'SOP-02-P04': 'Q4'}
            with self.assertRaises(to_scenarios.ConvertError):
                to_scenarios.convert(report, Path(tmp) / 'a', 'x', findings, report_dir=FIXTURES)
            rows, warnings = to_scenarios.convert(report, Path(tmp) / 'b', 'x', findings, report_dir=FIXTURES, skip_large=True)
            self.assertTrue(any('64 MiB' in w for w in warnings))
            self.assertEqual(len({r['scenario']: r for r in rows}['SOP-02-P01']['evidence']), 2)

    def test_global_setup_error_is_reported(self):
        report = {'config': {}, 'suites': [], 'errors': [{'message': 'Error: 环境检查未通过，本轮未执行任何场景：\n- 录屏需要 ffmpeg'}], 'stats': {}}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(to_scenarios.ConvertError) as ctx:
                to_scenarios.convert(report, Path(tmp) / 'r', 'x', {})
            self.assertIn('环境检查未通过', str(ctx.exception))

    def test_bad_finding_format(self):
        with self.assertRaises(to_scenarios.ConvertError):
            to_scenarios.parse_findings(['SOP-02-P02'])
        with self.assertRaises(to_scenarios.ConvertError):
            to_scenarios.parse_findings(['=Q3'])


class StandaloneTests(unittest.TestCase):
    """TW-SOP-1 I1 / SOP-01：经命令入口核对文件与退出码。"""

    def run_cli(self, out, extra=(), pending=None, report=None):
        report = load_report() if report is None else report
        for spec in report['suites'][0]['specs']:
            for test in spec['tests']:
                for result in test['results']:
                    for attachment in result.get('attachments', []):
                        if attachment.get('path'):
                            attachment['path'] = str(FIXTURES / attachment['path'])
        report_path = out.parent / 'report.json'
        report_path.write_text(json.dumps(report), encoding='utf-8')
        args = [sys.executable, str(ROOT / 'skills/playwright-acceptance/scripts/to_scenarios.py'),
                '--report', str(report_path), '--out', str(out), '--executor', 'standalone-tester', *extra]
        if pending is not None:
            pending_path = out.parent / 'pending.json'
            pending_path.write_text(json.dumps(pending), encoding='utf-8')
            args.extend(['--pending', str(pending_path)])
        return subprocess.run(args, capture_output=True, text=True)

    def test_pending_accepts_tw_sop_verify_and_top_level_arrays(self):
        ids = ['SOP-02-P01', 'SOP-02-P02', 'SOP-02-P03', 'SOP-02-P04']
        formats = [
            {'pending': [{'id': sid} for sid in ids]},
            {'ok': True, 'pending': [{'scenario': sid, 'reason': 'new'} for sid in ids],
             'guarded': [], 'blocked': []},
            ids,
            [{'id': sid} for sid in ids],
            [{'scenario': sid} for sid in ids],
            [ids[0], {'id': ids[1]}, {'scenario': ids[2]}, ids[3]],
        ]
        for pending in formats:
            with self.subTest(pending=pending), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'r'
                result = self.run_cli(out, FINDINGS, pending=pending)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([row['scenario'] for row in read_rows(out)], ids)

    def test_pending_without_ids_explains_all_formats_and_writes_no_results(self):
        for pending in ({'pending': [{'name': 'x'}]}, {'pending': []}, [], {},
                        {'pending': 'wrong'}, [None, 7, {}, '', '  ', {'id': 7}, {'scenario': []}]):
            with self.subTest(pending=pending), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'r'
                result = self.run_cli(out, FINDINGS, pending=pending)
                self.assertEqual(result.returncode, 2, result.stderr)
                for accepted in ('tw', 'id', 'sop-verify', 'scenario', '顶层', '数组'):
                    self.assertIn(accepted, result.stderr)
                self.assertFalse((out / 'results.jsonl').exists())

    def test_blocked_finding_uses_trimmed_first_error_line(self):
        report = load_report()
        result = report['suites'][0]['specs'][1]['tests'][0]['results'][0]
        result['error']['message'] = 'Error: \x1b[31m受阻：  测试店铺未登录  \n    at test (demo.mjs:1)\x1b[39m'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            result = self.run_cli(out, ['--finding-from-reason', '--finding', 'SOP-02-P04=Q4'], report=report)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = {row['scenario']: row for row in read_rows(out)}
            self.assertEqual(rows['SOP-02-P02']['finding'], '测试店铺未登录')
            self.assertEqual(rows['SOP-02-P02']['status'], 'blocked')
            self.assertEqual(rows['SOP-02-P04']['finding'], 'Q4')

    def test_blocked_without_reason_text_requests_reason_or_explicit_finding(self):
        report = load_report()
        result = report['suites'][0]['specs'][1]['tests'][0]['results'][0]
        result['error']['message'] = 'Error: 受阻：  \n    at test (demo.mjs:1)'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            result = self.run_cli(out, ['--finding-from-reason', '--finding', 'SOP-02-P04=Q4'], report=report)
            self.assertEqual(result.returncode, 2)
            self.assertIn('SOP-02-P02', result.stderr)
            self.assertIn('受阻：', result.stderr)
            self.assertIn('--finding SOP-02-P02=', result.stderr)
            self.assertFalse((out / 'results.jsonl').exists())

    def test_failed_conversion_leaves_result_directory_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / 'fresh' / 'r'
            fresh.parent.mkdir()
            result = self.run_cli(fresh)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(fresh.exists())
            self.assertEqual(sorted(p.name for p in fresh.parent.iterdir()), ['report.json'])
            existing = Path(tmp) / 'existing' / 'r'
            existing.mkdir(parents=True)
            (existing / 'results.jsonl').write_text('earlier\n', encoding='utf-8')
            result = self.run_cli(existing)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(sorted(p.name for p in existing.iterdir()), ['results.jsonl'])
            self.assertEqual((existing / 'results.jsonl').read_text(encoding='utf-8'), 'earlier\n')
            self.assertEqual(sorted(p.name for p in existing.parent.iterdir()), ['r', 'report.json'])

    def test_skip_finding_uses_skip_annotation_description(self):
        report = load_report()
        test = report['suites'][0]['specs'][3]['tests'][0]
        test['annotations'] = [{'type': 'issue', 'description': '其他注解'},
                               {'type': 'skip', 'description': '本轮不覆盖退款'}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            result = self.run_cli(out, ['--finding-from-reason'], report=report)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = {row['scenario']: row for row in read_rows(out)}
            self.assertEqual(rows['SOP-02-P04']['finding'], '本轮不覆盖退款')
            self.assertEqual(rows['SOP-02-P04']['status'], 'skip')
            self.assertNotIn('finding', rows['SOP-02-P01'])
            self.assertNotIn('finding', rows['SOP-02-P03'])

    def test_skip_without_description_requests_reason_or_explicit_finding(self):
        for annotations in ([], [{'type': 'skip'}], [{'type': 'skip', 'description': '  '}],
                            [{'type': 'issue', 'description': '与跳过无关'}]):
            with self.subTest(annotations=annotations), tempfile.TemporaryDirectory() as tmp:
                report = load_report()
                report['suites'][0]['specs'][3]['tests'][0]['annotations'] = annotations
                out = Path(tmp) / 'r'
                result = self.run_cli(out, ['--finding-from-reason'], report=report)
                self.assertEqual(result.returncode, 2, result.stderr)
                for hint in ('SOP-02-P04', 'test.skip', '原因', '--finding'):
                    self.assertIn(hint, result.stderr)
                self.assertFalse((out / 'results.jsonl').exists())

    def test_explicit_findings_override_reasons_and_missing_skip_description(self):
        for annotations in ([{'type': 'skip', 'description': '本轮不覆盖退款'}], []):
            with self.subTest(annotations=annotations), tempfile.TemporaryDirectory() as tmp:
                report = load_report()
                report['suites'][0]['specs'][3]['tests'][0]['annotations'] = annotations
                out = Path(tmp) / 'r'
                result = self.run_cli(out, ['--finding-from-reason', *FINDINGS], report=report)
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = {row['scenario']: row for row in read_rows(out)}
                self.assertEqual(rows['SOP-02-P02']['finding'], 'Q3')
                self.assertEqual(rows['SOP-02-P04']['finding'], 'Q4')

    def test_without_option_keeps_exact_finding_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r'
            result = self.run_cli(out)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, '转换失败：\n'
                             'SOP-02-P02 为 blocked，请用 --finding SOP-02-P02=<问题编号> 指定问题\n'
                             'SOP-02-P04 为 skip，请用 --finding SOP-02-P04=<问题编号> 指定问题\n')
            self.assertFalse((out / 'results.jsonl').exists())


def to_scenarios_keys():
    return {'scenario', 'status', 'actual', 'executed_at', 'executor', 'evidence', 'session', 'finding', 'note'}


if __name__ == '__main__':
    unittest.main()
