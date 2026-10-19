#!/usr/bin/env python3
"""把 Playwright JSON report 转成 tw 的场景结果契约（results.jsonl），并把证据复制到结果目录内。

用法：
  to_scenarios.py --report <PW_OUT>/report.json --out <目录> --executor "<执行者>"
                  [--finding SOP-02-P01=Q3 ...] [--pending pending.json] [--session <会话>] [--skip-large]

约定：
- 场景编号 = 测试标题的第一个空白分隔词，例如 "SOP-02-P01 人工接管…" → SOP-02-P01。无编号的测试跳过并提示。
- passed → pass；skipped → skip；failed / timedOut / interrupted → fail，
  但错误信息以“受阻：”开头时 → blocked。每个测试取最后一次结果（不建议 retries）。
- 同一场景有多条测试时合并，状态取最差：fail > blocked > skip > pass。
- blocked 与 skip 必须用 --finding 指定问题编号（tw 契约要求）；pass 与 fail 至少要有一份证据。
- 证据复制到 <out>/evidence/<场景编号>/，结果文件里用相对路径引用；单个文件超过 64 MiB 会被 tw 拒绝，
  默认报错，--skip-large 则跳过该文件并提示。
- executed_at = 该测试的 startTime + duration，带 +00:00 时区，秒精度。
只用 Python 3.9+ 标准库。
"""
import argparse
import base64
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BLOCKED_PREFIX = '受阻：'
EVIDENCE_LIMIT_BYTES = 64 * 1024 * 1024
RANK = {'fail': 3, 'blocked': 2, 'skip': 1, 'pass': 0}
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
ACTUAL_LIMIT = 300
UNSAFE = re.compile(r'[^A-Za-z0-9._\u4e00-\u9fff-]+')


class ConvertError(Exception):
    pass


def strip_ansi(text):
    return ANSI.sub('', text or '')


def error_message(result):
    error = result.get('error') or {}
    message = error.get('message')
    if not message:
        for item in result.get('errors') or []:
            if item.get('message'):
                message = item['message']
                break
    message = strip_ansi(message or '').strip()
    if message.startswith('Error: '):
        message = message[len('Error: '):]
    return message


def first_line(text):
    for line in (text or '').splitlines():
        if line.strip():
            return line.strip()
    return ''


def truncate(text, limit=ACTUAL_LIMIT):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def scenario_id(title):
    parts = title.split()
    if not parts:
        return None
    head = parts[0]
    return head if re.match(r'^[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9-]+$', head) else None


def walk_specs(suite):
    for spec in suite.get('specs') or []:
        yield spec
    for child in suite.get('suites') or []:
        for spec in walk_specs(child):
            yield spec


def last_result(test):
    results = test.get('results') or []
    return results[-1] if results else None


def classify(result):
    status = result.get('status')
    if status == 'passed':
        return 'pass'
    if status == 'skipped':
        return 'skip'
    if status in ('failed', 'timedOut', 'interrupted'):
        return 'blocked' if error_message(result).startswith(BLOCKED_PREFIX) else 'fail'
    raise ConvertError('未知的测试状态：%r' % status)


def step_summary(result):
    done = []
    failed = None
    for step in result.get('steps') or []:
        title = step.get('title') or ''
        if step.get('error'):
            failed = title
            break
        done.append(title)
    return done, failed


def describe(result, status, test):
    """用步骤与错误信息拼出 actual（实际结果）。"""
    done, failed_step = step_summary(result)
    message = error_message(result)
    if status == 'pass':
        text = '已完成 %d 步：%s' % (len(done), '；'.join(done)) if done else '通过'
    elif status == 'skip':
        reasons = [a.get('description') for a in (test.get('annotations') or []) if a.get('type') == 'skip' and a.get('description')]
        text = '跳过：' + (reasons[0] if reasons else '未说明原因')
    elif status == 'blocked':
        text = first_line(message)
    else:
        where = ('第 %d 步「%s」' % (len(done) + 1, failed_step)) if failed_step else ('第 %d 步后' % len(done) if done else '')
        detail = first_line(message) or ('超时' if result.get('status') == 'timedOut' else '失败')
        text = (where + '失败：' + detail) if where else detail
    return truncate(text)


def executed_at(result):
    start = result.get('startTime')
    if not start:
        raise ConvertError('结果缺少 startTime')
    moment = datetime.fromisoformat(start.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment + timedelta(milliseconds=result.get('duration') or 0)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def safe_name(name, fallback):
    cleaned = UNSAFE.sub('-', name or '').strip('-.')
    return cleaned or fallback


def copy_evidence(result, dest, report_dir, skip_large, warnings):
    """把附件复制到 dest，返回相对 dest 父目录(out) 的 posix 路径列表。"""
    refs = []
    for index, item in enumerate(result.get('attachments') or [], 1):
        name = item.get('name') or 'attachment'
        source = None
        body = None
        if item.get('path'):
            source = Path(item['path'])
            if not source.is_absolute():
                source = report_dir / source
            if not source.is_file():
                warnings.append('附件不存在，已跳过：%s' % source)
                continue
            suffix = source.suffix
            size = source.stat().st_size
        elif item.get('body'):
            body = base64.b64decode(item['body'])
            suffix = guess_suffix(item.get('contentType'))
            size = len(body)
        else:
            continue
        if size > EVIDENCE_LIMIT_BYTES:
            note = '%s 超过 64 MiB（%.1f MiB）' % (source or name, size / 1024 / 1024)
            if not skip_large:
                raise ConvertError(note + '；tw 会拒绝，请截取片段或加 --skip-large 跳过')
            warnings.append(note + '，已跳过')
            continue
        stem = safe_name(Path(name).stem if source else name, 'attachment-%d' % index)
        target = dest / ('%02d-%s%s' % (index, stem, suffix))
        dest.mkdir(parents=True, exist_ok=True)
        if source is not None:
            shutil.copyfile(source, target)
        else:
            target.write_bytes(body)
        refs.append(target.relative_to(dest.parent.parent).as_posix())
    return refs


def guess_suffix(content_type):
    table = {
        'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'video/webm': '.webm',
        'text/plain': '.txt', 'text/markdown': '.md', 'application/json': '.json', 'application/zip': '.zip',
    }
    return table.get((content_type or '').split(';')[0].strip(), '')


def collect(report):
    """按场景汇总：返回 {sid: [(spec_title, test, result)]} 与无编号标题列表。"""
    grouped = {}
    unnamed = []
    for suite in report.get('suites') or []:
        for spec in walk_specs(suite):
            sid = scenario_id(spec.get('title') or '')
            if not sid:
                unnamed.append(spec.get('title') or '(无标题)')
                continue
            for test in spec.get('tests') or []:
                result = last_result(test)
                if result is None:
                    continue
                grouped.setdefault(sid, []).append((spec.get('title'), test, result))
    return grouped, unnamed


def convert(report, out, executor, findings, session=None, pending_ids=None, skip_large=False, report_dir=None):
    out = Path(out)
    report_dir = Path(report_dir) if report_dir else Path.cwd()
    grouped, unnamed = collect(report)
    warnings = ['测试标题没有场景编号，未纳入结果：%s' % title for title in unnamed]
    if not grouped:
        global_errors = [strip_ansi(item.get('message', '')).split('\n    at ')[0].strip() for item in report.get('errors') or []]
        if global_errors:
            raise ConvertError('本轮没有执行任何场景，Playwright 在开跑前报错：\n' + '\n'.join(global_errors))
        raise ConvertError('报告里没有带场景编号的测试')
    rows = []
    problems = []
    for sid in sorted(grouped):
        entries = grouped[sid]
        statuses = [(classify(result), title, test, result) for title, test, result in entries]
        worst = max(statuses, key=lambda item: RANK[item[0]])
        status = worst[0]
        evidence = []
        actuals = []
        latest = None
        for item_status, title, test, result in statuses:
            evidence.extend(copy_evidence(result, out / 'evidence' / sid, report_dir, skip_large, warnings))
            if item_status == status:
                actuals.append(describe(result, item_status, test) if len(statuses) == 1 else '%s：%s' % (title, describe(result, item_status, test)))
            moment = executed_at(result)
            latest = moment if latest is None or moment > latest else latest
        row = {
            'scenario': sid,
            'status': status,
            'actual': truncate('；'.join(actuals)),
            'executed_at': latest,
            'executor': executor,
            'evidence': evidence,
        }
        if session:
            row['session'] = session
        if sid in findings:
            row['finding'] = findings[sid]
        elif status in ('blocked', 'skip'):
            problems.append('%s 为 %s，请用 --finding %s=<问题编号> 指定问题' % (sid, status, sid))
        if status in ('pass', 'fail') and not evidence:
            problems.append('%s 为 %s 但没有任何证据附件，请在 spec 里截图或开启录屏' % (sid, status))
        if pending_ids is not None and sid not in pending_ids:
            problems.append('%s 不在 pending 清单里，核对场景编号或任务身份' % sid)
        rows.append(row)
    if pending_ids is not None:
        missing = sorted(set(pending_ids) - set(grouped))
        if missing:
            warnings.append('pending 中尚无结果的场景：%s' % ', '.join(missing))
    if problems:
        raise ConvertError('\n'.join(problems))
    return rows, warnings


def parse_findings(values):
    findings = {}
    for value in values or []:
        if '=' not in value:
            raise ConvertError('--finding 格式为 场景编号=问题编号：%s' % value)
        sid, finding = value.split('=', 1)
        if not sid.strip() or not finding.strip():
            raise ConvertError('--finding 格式为 场景编号=问题编号：%s' % value)
        findings[sid.strip()] = finding.strip()
    return findings


def load_pending(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    items = data.get('pending') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ConvertError('pending 文件应为 tw scenarios pending --format json 的输出')
    ids = []
    for item in items:
        if isinstance(item, dict) and item.get('id'):
            ids.append(item['id'])
        elif isinstance(item, str):
            ids.append(item)
    return ids


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--report', required=True, help='Playwright JSON reporter 输出')
    parser.add_argument('--out', required=True, help='结果目录（仓库外），写入 results.jsonl 与 evidence/')
    parser.add_argument('--executor', required=True, help='执行者，写入每条结果')
    parser.add_argument('--finding', action='append', default=[], help='场景编号=问题编号，可重复；blocked 与 skip 必填')
    parser.add_argument('--pending', help='tw scenarios pending --format json 的输出，用于核对编号')
    parser.add_argument('--session', help='可选的会话标识，写入 session 字段')
    parser.add_argument('--skip-large', action='store_true', help='跳过超过 64 MiB 的证据文件而不是报错')
    args = parser.parse_args(argv)
    try:
        report_path = Path(args.report)
        report = json.loads(report_path.read_text(encoding='utf-8'))
        findings = parse_findings(args.finding)
        pending_ids = load_pending(args.pending) if args.pending else None
        rows, warnings = convert(report, args.out, args.executor, findings, session=args.session,
                                 pending_ids=pending_ids, skip_large=args.skip_large, report_dir=report_path.parent)
    except (OSError, ValueError) as exc:
        print('读取输入失败：%s' % exc, file=sys.stderr)
        return 2
    except ConvertError as exc:
        print('转换失败：\n%s' % exc, file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'results.jsonl'
    target.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    for warning in warnings:
        print('提示：' + warning, file=sys.stderr)
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    summary = '，'.join('%s %d' % (key, counts[key]) for key in ('pass', 'fail', 'blocked', 'skip') if key in counts)
    print('已写入 %s：%d 个场景（%s）。' % (target, len(rows), summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
