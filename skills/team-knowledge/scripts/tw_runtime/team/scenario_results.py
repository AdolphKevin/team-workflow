"""JSON Lines 场景结果契约，逐行汇总输入问题。"""
from datetime import datetime, timezone
import json

from common import Invalid, artifact, evidence_file, inside
from error_codes import Code
from scenario_files import FileProblems

STATUSES = ('pass', 'fail', 'blocked', 'skip')
REQUIRED = {'scenario', 'status', 'actual', 'executed_at', 'executor', 'evidence'}
OPTIONAL = {'session', 'finding', 'note'}


def load(path, identifiers):
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise FileProblems([{'line': 1, 'problem': '读取结果文件：' + str(exc)}], Code.SCENARIO_RESULT) from exc
    rows, errors, seen = [], [], set()
    if not raw.strip():
        raise FileProblems([{'line': 1, 'problem': '结果文件至少填写一条场景结果'}], Code.SCENARIO_RESULT)
    instant = datetime.now(timezone.utc)
    for number, line in enumerate(raw.splitlines(), 1):
        def add(message):
            errors.append({'line': number, 'problem': message})
        try:
            row = json.loads(line)
        except ValueError as exc:
            add('每行填写一个 JSON 对象：' + str(exc))
            continue
        if not isinstance(row, dict):
            add('每行填写一个 JSON 对象')
            continue
        for key in sorted(REQUIRED - row.keys()):
            add('缺少字段：' + key)
        for key in sorted(row.keys() - REQUIRED - OPTIONAL):
            add('格式外字段：' + key)
        for key in ('scenario', 'actual', 'executor', *sorted(OPTIONAL & row.keys())):
            if not isinstance(row.get(key), str) or (key != 'note' and not row[key].strip()):
                add(key + ' 填写非空字符串' if key != 'note' else 'note 填写字符串')
        key = row.get('scenario')
        if isinstance(key, str):
            if key not in identifiers:
                add('scenario 引用本任务的场景编号：' + key)
            if key in seen:
                add('同一文件每个场景填写一条结果：' + key)
            seen.add(key)
        status = row.get('status')
        if status not in STATUSES:
            add('status 取 pass、fail、blocked 或 skip')
        if status in ('blocked', 'skip') and (not isinstance(row.get('finding'), str) or not row['finding'].strip()):
            add('blocked 与 skip 填写 finding 问题编号')
        try:
            value = row.get('executed_at')
            if not isinstance(value, str) or 'T' not in value:
                raise ValueError()
            executed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if executed.tzinfo is None or executed.utcoffset() is None or executed > instant:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            add('executed_at 填写带时区、截至当前时间的 ISO 时间')
        refs = []
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or status in ('pass', 'fail') and not evidence:
            add('evidence 填写相对结果文件目录的路径数组；pass 与 fail 至少一份证据')
        else:
            for name in evidence:
                try:
                    target = evidence_file(inside(path.parent, name))
                    refs.append(artifact(path.parent, target))
                except (Invalid, OSError, TypeError, ValueError) as exc:
                    add('evidence：' + str(exc))
        rows.append({**row, 'evidence': refs})
    if errors:
        raise FileProblems(errors, Code.SCENARIO_RESULT)
    return rows
