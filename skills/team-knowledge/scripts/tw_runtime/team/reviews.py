"""Editable review format 1; immutable bindings and source snapshots leave room for later rechecks."""
import design_files
import records
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import uuid
import xml.etree.ElementTree as ET

from artifacts import directory
from common import (Invalid, artifact, artifact_valid, create, create_text, digest, inside, now,
                    load_profile, read, sha, write)
import delivery
import scenario_acceptance
import review_history
import validation
from error_codes import Code

BIND_START = '<!-- tw-review:binding:start -->'
BIND_END = '<!-- tw-review:binding:end -->'


class ReviewError(Invalid):
    error_code = Code.REVIEW_INCOMPLETE

    def __init__(self, section, line, reason, *, error_code=None):
        super().__init__(f'第 {line} 行（{section}）：{reason}', section=section, line=line, error_code=error_code)


class ReviewNotSubmitted(Invalid):
    error_code = Code.REVIEW_NOT_SUBMITTED

    def __init__(self, root, task, missing_run=False):
        path = locations(root, task['id'])[0]
        self.review_file = path.relative_to(root).as_posix()
        selected = '--task ' + shlex.quote(task['id'])
        self.next_action = (('先生成草稿：tw team run ' + selected + '；' if missing_run or not path.exists() else '')
                            + submission_action(root, task['id'], self.review_file))
        super().__init__('尚未提交评审，评审文件：' + self.review_file
                         + ('；本任务尚缺运行记录。' if missing_run else ''))


def locations(root, task_id):
    base = directory(root, task_id).parent.parent
    return base / 'review.md', base / 'reviews' / 'editor.json'


def submission_action(root, task_id, review_file=None, *, recheck=False, register=False):
    """任务的评审提交方式在此选择，所有下一步共用。"""
    from tw_runtime.team import platform_script
    path = review_file or locations(root, task_id)[0].relative_to(root).as_posix()
    options = '--task ' + shlex.quote(task_id) + ' --root ' + shlex.quote(str(root))
    prepare = ('先核对当前运行并生成复核稿：tw team run ' + options
               + '；tw team review ' + options + '；') if recheck else ''
    if platform_script.is_task(root, task_id, required=False):
        imported = 'tw team review ' + options + ' --from-platform；' if register else ''
        return (prepare + '逐项核对并填写 ' + shlex.quote(str(path))
                + '，作为变更请求评审发布，再运行：' + imported + 'tw team deliver ' + options)
    if recheck:
        return prepare.rstrip('；')
    file_option = ' --file ' + shlex.quote(str(path)) if review_file else ''
    return (prepare + '填写后提交：tw team review --task ' + shlex.quote(task_id)
            + ' --submit' + file_option + ' --root ' + shlex.quote(str(root)))


def source_path(args, root, task_id):
    path = Path(args.file).expanduser() if args.file else locations(root, task_id)[0]
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def latest_platform_source(root, task_id):
    from tw_runtime.team import platform_script
    value = platform_script.task(root, task_id)
    rows = [row for row in value['items'] if row['kind'] == 'review' and BIND_START in row['body']]
    return max(rows, key=lambda row: platform_script.timestamp(row['updated_at']), default=None)


def platform_source(root, task_id):
    item = latest_platform_source(root, task_id)
    if item is None:
        raise ReviewNotSubmitted(root, {'id': task_id})
    _binding(root, task_id, item['body'], current_only=True)
    return item


def platform_is_newer(root, task_id, review_ref):
    """按提交时间选择评审；绑定核对由登记入口完成。"""
    from tw_runtime.team import platform_script
    item = latest_platform_source(root, task_id)
    if not review_ref:
        return True  # 登记入口会给出缺少平台评审的具体原因。
    if item is None:
        return False
    state = _state(root, task_id)
    entry = next((row for row in state['submitted'].values()
                  if row['review'] == review_ref), {})
    submitted_at = entry.get('submitted_at')
    if not submitted_at:
        # 旧登记沿用原始提交响应的完成时间；原评审与平台条目相同时可还原平台时间。
        review = read(artifact_valid(root, review_ref))
        markdown = entry.get('markdown')
        if (review.get('platform_url') == item['url'] and markdown
                and markdown['sha256'] == hashlib.sha256(item['body'].encode('utf-8')).hexdigest()):
            submitted_at = item['updated_at']
        else:
            from checklist import records
            submitted_at = next((response.get('finished_at') or claim.get('started_at')
                                 for claim, response in reversed(records(root, task_id))
                                 if response and response.get('artifact') == review_ref
                                 and (response.get('finished_at') or claim.get('started_at'))), None)
        if not submitted_at:
            error = Invalid('评审登记记录缺少提交时间：' + review_ref['path'] + '；请重新登记该评审。')
            error.next_action = ('tw team review --task ' + shlex.quote(task_id) + ' --from-platform'
                                 if review.get('platform_url') else submission_action(root, task_id, register=True))
            raise error
    return platform_script.timestamp(item['updated_at']) > platform_script.timestamp(submitted_at)


def source_text(args, root, task_id):
    if getattr(args, 'from_platform', False):
        return args.platform_review['body']
    return source_path(args, root, task_id).read_bytes().decode('utf-8')


def case_repair(root, task_id, review_ref=None):
    """Point back to editable input, preserving immutable submitted Markdown as evidence."""
    state = _state(root, task_id)
    entry = next((row for row in state['submitted'].values()
                  if review_ref and row['review']['sha256'] == review_ref['sha256']), None)
    original = (entry or {}).get('input_markdown')
    if original is None and review_ref:
        response = (root / review_ref['path']).parent / 'response.json'
        if response.is_file():
            candidate = read(response).get('review_file')
            if candidate and not candidate.startswith(('http://', 'https://')) and Path(candidate).is_relative_to(root):
                original = candidate
    path = Path(original) if original else locations(root, task_id)[0]
    path = (root / path).resolve() if not path.is_absolute() else path
    name = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    return {'review_file': name,
            'next_action': f'修正评审 Markdown {name} 中的“用例”字段后，' + submission_action(root, task_id, name)}


def published_approval(root, task_id, review):
    """A combined approval derived from published Markdown is itself shared consent."""
    if 'platform_author' not in review and 'platform_url' not in review:
        return None
    from tw_runtime.team import platform_script
    value = platform_script.task(root, task_id)
    item = next((row for row in value['items'] if row['kind'] == 'review'
                 and row['url'] == review.get('platform_url')), None)
    if item is None or item['author'] != review.get('platform_author'):
        raise ReviewError('平台评审', 1, '已提交评审的平台地址或作者无法核对，请重新提交。')
    entries = _state(root, task_id)['submitted'].values()
    entry = next((row for row in entries if read(artifact_valid(root, row['review'])) == review), None)
    if entry is None or artifact_valid(root, entry['markdown']).read_bytes().decode('utf-8') != item['body']:
        raise ReviewError('平台评审', 1, '平台评审原文与已提交材料不一致，请重新生成复核稿并提交。')
    return read(artifact_valid(root, entry['approval'])) if entry.get('approval') else None


def _state(root, task_id):
    path = locations(root, task_id)[1]
    if not path.exists():
        return {'data_version': 1, 'kind': 'review-editor', 'current': None, 'generations': {}, 'submitted': {}}
    value = read(path)
    if value.get('data_version') != 1 or value.get('kind') != 'review-editor':
        raise ReviewError('绑定', 1, '草稿状态版本不符，请保留原文件后重新运行 review。')
    return value


def history_inputs(root, task_id, group=None):
    state = _state(root, task_id)
    current = read(artifact_valid(root, state['current'])) if state['current'] else None
    previous = review_history.latest(root, state, current, group)
    return {key: previous.get(key) for key in ('review', 'markdown', 'source', 'binding')} if previous else None


def _field(key, value=''):
    parts = str(value).splitlines() or ['']
    return '- ' + key + '：' + parts[0] + ''.join('\n  ' + line for line in parts[1:])


def _protected(name, text):
    return f'<!-- tw-review:{name}:start -->\n{text.rstrip()}\n<!-- tw-review:{name}:end -->'


def preview_execution(root, profile, task, paths):
    """Display original failed/missing results without treating them as verified evidence."""
    from common import task_valid
    required = task_valid(task, profile, root)
    candidates = {key: [] for key in required}
    bindings = {}

    def current(key):
        if key not in bindings:
            bindings[key] = validation.check_binding(root, profile, profile['checks'][key], live=False)
        return bindings[key]

    for name in paths:
        record = read(inside(root, name))
        rows = record.get('results', []) if record.get('kind') == 'execution' else [record.get('result', {})]
        for row in rows:
            key = row.get('id')
            if key not in candidates:
                continue
            check = profile['checks'][key]
            if row.get('binding', {}).get('definition') != validation.execution_definition(check):
                continue
            out, _ = validation.original_files(root, check, row)
            native = out / check['report'][len('{output}/'):] if check.get('report') else None
            decoded = validation.decode(check, {'state': row['state'], 'exit_code': row['exit_code'],
                'stdout': (out / 'stdout.txt').read_text()}, native)
            status, cases, detail = decoded.status, decoded.cases, decoded.detail
            if not cases:
                try:
                    if check['format'] == 'junit':
                        for case in ET.parse(native).getroot().iter('testcase'):
                            cases[case.get('classname', '') + '::' + case.get('name', '')] = (
                                'failed' if case.find('failure') is not None or case.find('error') is not None
                                else 'skipped' if case.find('skipped') is not None else 'passed')
                    elif check['format'] == 'go-json':
                        for line in (out / 'stdout.txt').read_text().splitlines():
                            event = json.loads(line)
                            if event.get('Test') and event.get('Action') in ('pass', 'fail', 'skip'):
                                cases[event['Package'] + '::' + event['Test']] = {
                                    'pass': 'passed', 'fail': 'failed', 'skip': 'skipped'}[event['Action']]
                except (ET.ParseError, OSError, ValueError, TypeError, KeyError):
                    cases = {}  # A malformed native report cannot supply individual case outcomes.
            usable = status == 'passed' and validation.row_problem(root, profile, key, row, current, record) is None
            if record.get('kind') == 'imported-execution' and usable:
                import portable
                try:
                    portable.validate_import(root, profile, record, live=False)
                except Invalid:
                    usable = False
            candidates[key].append((record.get('started_at', ''), name,
                                    {**row, 'status': status, 'cases': cases, 'detail': detail}, usable))
    results, selected = {}, {}
    # Preserve the established selection of passing candidates whenever one is available.
    for key, rows in candidates.items():
        if rows:
            _, name, result, _ = max([row for row in rows if row[3]] or rows, key=lambda row: row[0])
            results[key], selected[key] = result, str(name)
    return {'results': results, 'selected_runs': selected, 'checks': sorted(required)}


def snapshot(args, root, profile, task, draft_id, allow_incomplete=False):
    from commands import report_input
    report = report_input(args, root, task, include_knowledge=False)
    template = delivery.review_template(root, profile, task, report)
    design, _, status, selected = delivery.design_material(root, profile, task, report)
    try:
        execution = validation.verify_runs(root, profile, task, report['runs'], live=False)
    except Invalid as exc:
        if not allow_incomplete:
            raise ReviewError('运行结果', 1, '运行尚不能用于正式评审：' + str(exc),
                              error_code=exc.error_code if exc.error_code in (Code.CHECK_CONFIG, Code.CHECK_RESULT)
                              else Code.REVIEW_RUN_INCOMPLETE) from exc
        execution = preview_execution(root, profile, task, report['runs'])
        execution['gap'] = str(exc)
    chosen = {key: artifact(root, inside(root, path)) for key, path in execution['selected_runs'].items()}
    bindings = {key: template[key] for key in ('task_id', 'task_digest', 'source_digest', 'validation_policy', 'sections', 'risks')}
    bindings.update({key: template[key] for key in ('scenario_rounds', 'scenario_files')})
    bindings.update(format_version=2, draft_id=draft_id,
                    runs=[artifact(root, inside(root, p)) for p in report['runs']], selected_runs=chosen)
    source = review_history.source_record(root, profile, task)
    if source['source_digest'] != bindings['source_digest']:
        raise ReviewError('绑定', 1, '生成评审期间源码已改变，请保持工作区稳定后重试。')
    value = {'data_version': 1, 'kind': 'review-draft-binding', 'bindings': bindings, 'template': template,
             'automatic': {}, 'generated': {}, 'at': now(), 'previous_review': None,
             'previous_markdown': None, 'source_snapshot': source, 'acceptance_results': {}, 'rechecks': []}
    value['approval_needed'] = (status.get('review_mode') == 'combined'
                                and not (status.get('fully_approved') and status.get('combined_complete')))
    if status.get('review_mode') == 'combined':
        from commands import local
        bindings['approval_plan'] = review_history.approval_plan(
            design, [design_files.read(local(root, path)) for path in args.design_history])
    from contracts import execution_environment
    sections = {row['id']: row for row in design['sections']}
    _, scenario_state = scenario_acceptance.current(root, profile, task, design, report['runs'])
    value['scenario_states'] = {row['id']: {'state': row['state'], 'fingerprint': row['fingerprint'],
        'result': row.get('result')} for row in scenario_state['scenarios']}
    for row in task['acceptance']:
        key = row['id']
        section = sections[key]
        requirement = section['data'].get('verification', {'cases': []})
        value['acceptance_results'][key] = {'checks': {check: {'run': chosen.get(check),
            **{name: execution['results'].get(check, {}).get(name) for name in ('status', 'cases', 'exit_code')}}
            for check in section['data']['checks']}}
        observations, evidence = [], []
        lines = ['- ' + gap for gap in execution_environment(profile, {**task, 'acceptance': [row]}, design)]
        if not requirement['cases']:
            lines.append('- 未指明用例，证据为整项检查通过')
        for check in section['data']['checks']:
            coverage = profile['checks'][check].get('coverage')
            if coverage:
                lines.append(f'- 检查 {check} 的覆盖声明：层级 {coverage["level"]}；入口 {"、".join(coverage["entrypoints"])}'
                             f'；环境 {coverage["environment"]}；替身 {"、".join(coverage["substitutes"]) or "无"}；隔离 {coverage["isolation"]}')
            result = execution['results'].get(check)
            if result is None:
                lines.append('- 检查 ' + check + '：没有对应的运行结果。')
                continue
            ref = chosen[check]
            words = {'passed': '通过', 'failed': '失败', 'skipped': '跳过', 'error': '错误',
                     'incomplete': '未完成', 'timeout': '超时', 'unavailable': '无法执行'}
            lines += [f'- 检查 {check}：{words.get(result["status"], result["status"])}；退出码 {result.get("exit_code")}',
                      '  - 运行：' + ref['path']]
            outcomes = result.get('cases', {})
            cases = sorted(case for case, outcome in outcomes.items() if outcome == 'passed')
            # Show the cases this acceptance names and every case that did not pass; summarise the rest.
            declared = set(requirement.get('cases', []))
            shown = sorted(case for case, outcome in outcomes.items() if case in declared or outcome != 'passed')
            lines += ['  - 用例 ' + case + '：' + words.get(outcomes[case], outcomes[case]) for case in shown]
            lines += ['  - 用例 ' + case + '：未执行' for case in sorted(declared - outcomes.keys())]
            if outcomes:
                counts = {}
                for outcome in outcomes.values():
                    counts[outcome] = counts.get(outcome, 0) + 1
                tally = '，'.join(words.get(key, key) + ' ' + str(counts[key]) for key in sorted(counts))
                lines.append(f'  - 共 {len(outcomes)} 项用例：{tally}' + ('' if declared else '；方案未登记对应用例'))
            else:
                lines.append('  - 未登记独立用例；以上为实际命令的退出结果。')
            if execution.get('gap'):
                lines.append('  - 此处仅展示原始结果，当前运行材料未通过验收核查；完整意见可提交，验收前仍需修复。')
            lines.append('  - 命令：' + ' '.join(str(v) for v in result.get('argv', [])))
            for item in result.get('artifacts', []):
                if item['path'].endswith('/stdout.txt'):
                    content = artifact_valid(root, item).read_text(errors='replace')
                    lines += ['  - 原始输出摘录：'] + ['    ' + line for line in content[:4000].splitlines()]
            observations.append({'kind': 'execution', 'run': ref, 'check': check, 'cases': cases})
            if ref not in evidence:
                evidence.append(ref)
        scene_rows = scenario_acceptance.selected(section, scenario_state)
        lines += scenario_acceptance.result_lines(scene_rows)
        observations.append({'kind': 'scenarios', 'rounds': template['scenario_rounds']})
        for ref in template['scenario_rounds'] + [ref for scene in scene_rows for ref in scene.get('result', {}).get('evidence', [])]:
            if ref not in evidence:
                evidence.append(ref)
        value['automatic'][key] = {'observations': observations, 'evidence': evidence}
        value['generated']['results-' + key] = '\n'.join(lines)
    return value, design, status, execution


def render(value):
    binding = value['bindings']
    prefill = value.get('prefill', {})

    def filled(section, key, default=''):
        return _field(key, prefill.get(section, {}).get(key, default))

    def recheck(section):
        return [_field('复核', '待复核')] if section in value.get('rechecks', []) else []

    lines = ['# 任务评审', '', '只填写下方评审字段；工具绑定、运行结果和风险列表保持原样。',
             '结论填写“通过”或“不通过”；证据文件可留空，补充时每行一个项目内路径。', '',
             BIND_START, records.comment(binding), BIND_END, '']
    if value.get('changes'):
        lines += ['## 变化', _protected('changes', value['generated']['changes']), '',
                  '预填内容尚未重新确认；每个复核字段均须由评审人改为“已复核”。', '']
    lines += ['## 评审信息', filled('评审信息', '评审人'), filled('评审信息', '知识冲突已处理')]
    if value.get('approval_needed'):
        lines += [filled('评审信息', '批准方案与代码'), filled('评审信息', '批准说明')] + recheck('评审信息')
    lines.append('')
    for name in ('规范 standards', '需求 spec'):
        lines += ['## ' + name] + [filled(name, key) for key in ('结论', '理由', '证据文件')] + recheck(name) + ['']
    for row in value['template']['acceptance']:
        key = row['id']
        lines += ['## 验收 ' + key]
        if key in value['automatic']:
            lines += [_protected('results-' + key, value['generated']['results-' + key])]
            lines += [filled('验收 ' + key, '用例')]
        name = '验收 ' + key
        lines += [filled(name, field) for field in ('结论', '理由', '证据文件')] + recheck(name)
        lines.append('')
    lines += ['## 问题清单', '状态使用 open、resolved、accepted、deferred；已知问题的身份字段保持原样。', '']
    issues = {'问题 ' + issue['id']: issue for issue in value['template']['findings']}
    for name in prefill:
        if name.startswith('问题 ') and name not in issues:
            issues[name] = {'id': '', 'owner': '', 'affects': [], 'blocks': [], 'state': '', 'summary': '', 'resolution': {}}
    for name, issue in issues.items():
        lines += ['### ' + name]
        for field, data in [('编号', issue['id']), ('负责人', issue['owner']), ('影响范围', ', '.join(issue['affects'])),
                            ('阻塞阶段', ', '.join(issue['blocks'])), ('状态', issue['state']), ('摘要', issue['summary'])]:
            lines.append(filled(name, field, data))
        resolution = issue['resolution']
        for field, key in [('处置理由', 'reason'), ('处置证据', 'evidence'), ('确认人', 'confirmed_by'),
                           ('确认依据', 'confirmation'), ('跟进任务', 'follow_up'), ('范围调整', 'scope_change')]:
            raw = resolution.get(key, '')
            lines.append(filled(name, field, '\n'.join(raw) if isinstance(raw, list) else raw))
        lines.append('')
    risk = '\n'.join('- ' + item for item in binding['risks']) or '- 无风险标签'
    lines += ['## 风险', _protected('risks', risk), '']
    return '\n'.join(lines)


def _extract(text, start, end, section):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ReviewError(section, 1, '工具区标记缺失或重复，须使用本任务生成的完整草稿。')
    left = text.index(start)
    right = text.index(end, left) + len(end)
    return text[left:right], left, right


def _sections(text, value):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    block, left, right = _extract(text, BIND_START, BIND_END, '绑定')
    expected = BIND_START + '\n' + records.comment(value['bindings']) + '\n' + BIND_END
    if block != expected:
        raise ReviewError('绑定', text[:left].count('\n') + 1, '工具填写的绑定区被改动，不能提交；请重新生成复核稿。')
    masked = text[:left] + re.sub(r'[^\n]', ' ', block) + text[right:]
    protected = dict(value['generated'])
    protected['risks'] = '\n'.join('- ' + item for item in value['bindings']['risks']) or '- 无风险标签'
    for key, raw in protected.items():
        start, end = f'<!-- tw-review:{key}:start -->', f'<!-- tw-review:{key}:end -->'
        block, left, right = _extract(masked, start, end, key)
        if block != _protected(key, raw):
            raise ReviewError(key, masked[:left].count('\n') + 1, '工具填写的运行结果或风险列表被改动。')
        masked = masked[:left] + re.sub(r'[^\n]', ' ', block) + masked[right:]
    sections, section, field = {}, None, None
    for number, line in enumerate(masked.splitlines(), 1):
        heading = re.match(r'^(#{2,3}) (.+)$', line)
        if heading:
            section = heading[2].strip()
            if section.startswith('人工观察 '):
                raise ReviewError(section, number, '人工执行按场景逐条记录，用 tw team scenarios submit 登记')
            if section in sections:
                raise ReviewError(section, number, '小节重复。')
            sections[section] = {'line': number, 'fields': {}}
            field = None
            continue
        if section is None:
            continue
        item = re.match(r'^- ([^：:]+)[：:][ \t]*(.*)$', line)
        if item:
            field = item[1].strip()
            fields = sections[section]['fields']
            if field in fields:
                raise ReviewError(section, number, '字段重复：' + field)
            fields[field] = {'line': number, 'value': item[2]}
        elif field is not None and line.strip():
            sections[section]['fields'][field]['value'] += '\n' + line.strip().removeprefix('- ').strip()
    required = ['评审信息', '规范 standards', '需求 spec', '问题清单', '风险']
    if value.get('changes'):
        required.append('变化')
    for key in required + ['验收 ' + row['id'] for row in value['template']['acceptance']]:
        if key not in sections:
            raise ReviewError(key, 1, '必需小节缺失。')
    return sections


def _value(sections, section, field, required=True):
    block = sections.get(section)
    if block is None:
        raise ReviewError(section, 1, '必需小节缺失。')
    item = block['fields'].get(field)
    value = item['value'].strip() if item else ''
    if required and (not value or '__REPLACE__' in value):
        raise ReviewError(section, item['line'] if item else block['line'], '请填写' + field + '。')
    return value


def _list(value):
    return [part.strip().removeprefix('- ').strip() for part in re.split('[,，\n]', value) if part.strip()]


def _evidence(root, raw, section, line):
    from commands import local
    refs = []
    for item in raw.splitlines():
        item = item.strip().removeprefix('- ').strip()
        if not item:
            continue
        try:
            ref = artifact(root, local(root, item))
            delivery.evidence(root, load_profile(root), ref)
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            raise ReviewError(section, line, '证据文件不可用：' + str(exc)) from exc
        refs.append(ref)
    return refs


def _conclusion(sections, name):
    raw = _value(sections, name, '结论')
    if raw not in ('通过', '不通过'):
        raise ReviewError(name, sections[name]['fields']['结论']['line'], '结论仅接受“通过”或“不通过”。')
    return {'status': 'passed' if raw == '通过' else 'failed', 'summary': _value(sections, name, '理由')}


def compile_review(root, value, sections):
    result = copy.deepcopy(value['template'])
    result['reviewer'] = _value(sections, '评审信息', '评审人')
    conflict = _value(sections, '评审信息', '知识冲突已处理')
    if conflict not in ('是', '否'):
        raise ReviewError('评审信息', sections['评审信息']['line'], '知识冲突已处理仅接受“是”或“否”。')
    result['knowledge_conflicts_resolved'] = conflict == '是'
    defaults = []
    for row in result['acceptance']:
        key, name = row['id'], '验收 ' + row['id']
        row.update(_conclusion(sections, name))
        if key in value['automatic']:
            row.update(copy.deepcopy(value['automatic'][key]))
            row['cases'] = [part.strip().removeprefix('- ').strip() for part in
                            re.split('[、\n]', _value(sections, name, '用例', False)) if part.strip()]
        for ref in row['evidence']:
            if ref not in defaults:
                defaults.append(ref)
        for ref in _evidence(root, _value(sections, '验收 ' + key, '证据文件', False), '验收 ' + key, sections['验收 ' + key]['line']):
            if ref not in row['evidence']:
                row['evidence'].append(ref)
            if ref not in defaults:
                defaults.append(ref)
    result['findings'] = []
    known = {row['id']: row for row in value['template']['findings']}
    for name, block in sections.items():
        if not name.startswith('问题 '):
            continue
        row = {'id': _value(sections, name, '编号'), 'owner': _value(sections, name, '负责人'),
               'affects': _list(_value(sections, name, '影响范围', False)),
               'blocks': _list(_value(sections, name, '阻塞阶段')),
               'state': _value(sections, name, '状态'), 'summary': _value(sections, name, '摘要'), 'resolution': {}}
        original = known.get(name.removeprefix('问题 '))
        if original:
            for key in ('id', 'owner', 'affects', 'blocks', 'summary'):
                if row[key] != original[key]:
                    raise ReviewError(name, block['line'], '已知问题的编号、负责人、影响范围、阻塞阶段及摘要必须保持原样。')
        if row['state'] != 'open':
            row['resolution'] = {'reason': _value(sections, name, '处置理由'),
                                 'evidence': [line.strip() for line in _value(sections, name, '处置证据').splitlines() if line.strip()]}
            for field, key in [('确认人', 'confirmed_by'), ('确认依据', 'confirmation'),
                               ('跟进任务', 'follow_up'), ('范围调整', 'scope_change')]:
                raw = _value(sections, name, field, False)
                if raw:
                    row['resolution'][key] = raw
        try:
            from contracts import issue
            issue(row)
        except Invalid as exc:
            raise ReviewError(name, block['line'], '问题处置不完整：' + str(exc)) from exc
        result['findings'].append(row)
    from contracts import reconcile
    try:
        reconcile(value['template']['findings'], result['findings'])
    except Invalid as exc:
        raise ReviewError('问题清单', sections['问题清单']['line'], '已知问题被移除或身份被改变：' + str(exc)) from exc
    for axis, name in [('standards', '规范 standards'), ('spec', '需求 spec')]:
        result[axis] = _conclusion(sections, name)
        refs = _evidence(root, _value(sections, name, '证据文件', False), name, sections[name]['line'])
        result[axis]['evidence'] = refs or copy.deepcopy(defaults)
    return result


def progress(text, value):
    try:
        sections = _sections(text, value)
    except ReviewError as exc:
        return {'completed': 0, 'total': 1, 'problem': str(exc)}
    fields = [('评审信息', '评审人'), ('评审信息', '知识冲突已处理')]
    for name in ['规范 standards', '需求 spec'] + ['验收 ' + row['id'] for row in value['template']['acceptance']]:
        fields += [(name, '结论'), (name, '理由')]
    completed = sum(bool(sections.get(name, {}).get('fields', {}).get(field, {}).get('value', '').strip()) for name, field in fields)
    pending = pending_rechecks(value, sections)
    return {'completed': completed, 'total': len(fields), 'pending_rechecks': pending}


def pending_rechecks(value, sections):
    required = list(value.get('rechecks', []))
    required += [name for name, block in sections.items() if '复核' in block['fields'] and name not in required]
    result = []
    for name in required:
        block = sections.get(name, {'line': 1, 'fields': {}})
        field = block['fields'].get('复核', {'line': block['line'], 'value': ''})
        if field['value'].strip() != '已复核':
            result.append({'section': name, 'line': field['line']})
    return result


def require_rechecks(value, sections):
    pending = pending_rechecks(value, sections)
    if pending:
        details = '；'.join('第 ' + str(row['line']) + ' 行（' + row['section'] + '）' for row in pending)
        raise ReviewError('逐项复核', pending[0]['line'], '以下小节尚未全部标为“已复核”：' + details)


def _same_group(left, right):
    return review_history.same_group(left, right)


def _usable_draft(left, right):
    return (_same_group(left['bindings'], right['bindings'])
            and (not right.get('approval_needed') or left.get('approval_needed', False)))


def _existing(root, task_id, target, state, current, fresh):
    raw = target.read_bytes().decode('utf-8')
    result = {'ok': True, 'review_file': target.relative_to(root).as_posix(),
              'binding': state['current'], 'binding_current': fresh,
              'recheck': bool((current or {}).get('changes')), 'review_current': False,
              'progress': progress(raw, current) if current else {'completed': 0, 'total': 1},
              'summary': '已有评审草稿，未覆盖；请填写并提交。',
              'next_action': submission_action(root, task_id, target.relative_to(root).as_posix())}
    if not fresh:
        result['next_action'] = '草稿绑定已变化，原文件未覆盖；先将 review.md 移到别处，再运行 tw team review --task <身份>。'
    if (current or {}).get('changes'):
        result['changes'] = current['changes']
    if state.get('current_archive'):
        result['archived_draft'] = state['current_archive']
    return result


def generate(args, root, profile, task, request):
    from cleanup import guard
    from materials import load
    target, state_path = locations(root, task['id'])
    candidate, _, _, candidate_execution = snapshot(args, root, profile, task, uuid.uuid4().hex, allow_incomplete=True)
    with guard(root):
        state = _state(root, task['id'])
        current = read(artifact_valid(root, state['current'])) if state['current'] else None
        group = load(root, task['id']) or {}
        previous = review_history.latest(root, state, current, group)
        submitted = state['submitted'].get((current or {}).get('bindings', {}).get('draft_id'), {})
        edited = target.exists() and sha(target) != submitted.get('default_sha')
        fresh = current and _usable_draft(current, candidate)
        if target.exists() and fresh and edited:
            result = _existing(root, task['id'], target, state, current, True)
            return {**result, 'artifact': request.publish('review-draft.json', result)}
        if previous and _usable_draft(previous['value'], candidate) and not edited:
            result = {'ok': True, 'review_current': True, 'recheck': False, 'binding_current': True,
                      'review_file': target.relative_to(root).as_posix() if target.exists() else previous['markdown']['path'],
                      'binding': previous['binding'], 'review': previous['review'],
                      'summary': '当前已提交的评审仍然有效，无需生成复核稿。',
                      'next_action': 'tw team accept --task ' + shlex.quote(task['id'])}
            failures = delivery.review_case_failures(previous['review_value'], candidate_execution)
            if failures:
                result.update(case_repair(root, task['id'], previous['review']), review_failures=failures,
                              summary='当前评审中的用例需要修正后重新提交。')
            return {**result, 'artifact': request.publish('review-status.json', result)}
        if target.exists() and fresh:
            result = _existing(root, task['id'], target, state, current, True)
            return {**result, 'artifact': request.publish('review-draft.json', result)}
        old = current if target.exists() and edited else previous['value'] if previous else current
        old_text = target.read_bytes().decode('utf-8') if target.exists() and edited else previous['text'] if previous else None
        if old is not None and old_text is not None:
            fields = _sections(old_text, old)
            baseline = previous['source_value'] if previous else old.get('source_snapshot')
            review_history.carry(candidate, old, fields, baseline)
        if previous:
            candidate.update(previous_review=previous['review'], previous_markdown=previous['markdown'],
                             previous_source=previous.get('source'))
        for key in candidate['automatic']:
            if candidate.get('prefill', {}).get('验收 ' + key, {}).get('用例', '').strip():
                name = 'results-' + key
                candidate['generated'][name] = candidate['generated'][name].replace('- 未指明用例，证据为整项检查通过\n', '')
        draft_id = candidate['bindings']['draft_id']
        raw = render(candidate)
        candidate['template_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        binding_path = target.parent / 'reviews' / draft_id / 'binding.json'
        create(binding_path, candidate)
        ref = artifact(root, binding_path)
        archived = None
        created = False
        try:
            if target.exists():
                backup = target.parent / 'reviews' / ('archived-' + uuid.uuid4().hex + '.md')
                target.rename(backup)
                archived = artifact(root, backup)
            create_text(target, raw)
            created = True
            state['current'] = ref
            state['generations'][draft_id] = ref
            state['current_archive'] = archived
            if archived:
                state.setdefault('archives', []).append(archived)
            write(state_path, state)
        except BaseException:
            if created and target.exists() and sha(target) == candidate['template_sha256']:
                target.unlink()
            if archived and not target.exists():
                inside(root, archived['path']).rename(target)
            raise
    result = {'ok': True, 'review_file': target.relative_to(root).as_posix(), 'binding_current': True,
              'binding': ref, 'recheck': bool(candidate.get('changes')), 'review_current': False,
              'progress': progress(raw, candidate),
              'summary': '复核稿已生成；预填内容均须逐项确认。' if candidate.get('changes') else '评审草稿已生成；请填写结论和理由，再提交。',
              'next_action': submission_action(root, task['id'], target.relative_to(root).as_posix())}
    if archived:
        result['archived_draft'] = archived
    if candidate.get('changes'):
        result['changes'] = candidate['changes']
    return {**result, 'artifact': request.publish('review-draft.json', result)}


def cached_draft(root, task_id, result):
    target, _ = locations(root, task_id)
    if not result.get('ok') or not target.is_file():
        return result
    state = _state(root, task_id)
    if state['current']:
        value = read(artifact_valid(root, state['current']))
        return {**result, 'progress': progress(target.read_text(), value)}
    return result


def _binding(root, task_id, text, *, current_only=False):
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    block, left, _ = _extract(normalized, BIND_START, BIND_END, '绑定')
    try:
        value = records.block(block, 'review')
        draft_id = value.get('draft_id', '')
        if not re.fullmatch('[a-f0-9]{32}', draft_id):
            raise ValueError('缺少草稿编号')
        state = _state(root, task_id)
        ref = state['generations'].get(draft_id)
        if ref is None:
            raise ValueError('该草稿不属于本任务')
        if current_only and ref != state['current']:
            raise Invalid('平台评审绑定的是此前的草稿', error_code=Code.REVIEW_BINDING_STALE)
        return read(artifact_valid(root, ref))
    except (Invalid, ValueError, TypeError, KeyError) as exc:
        raise ReviewError('绑定', normalized[:left].count('\n') + 1, '工具绑定核对有误：' + str(exc),
                          error_code=Code.REVIEW_BINDING_STALE if getattr(exc, 'error_code', None) == Code.REVIEW_BINDING_STALE else None) from exc


def require_current_runs(root, profile, bindings):
    for key, ref in bindings['selected_runs'].items():
        record = read(artifact_valid(root, ref))
        rows = record.get('results', []) if record.get('kind') == 'execution' else [record.get('result', {})]
        row = next((row for row in rows if row.get('id') == key), None)
        current = validation.check_binding(root, profile, profile['checks'][key], live=False)
        if (row is None or not record.get('source_unchanged', row.get('source_unchanged'))
                or not row.get('source_unchanged')
                or any(row.get('binding', {}).get(part) != val for part, val in current.items())):
            raise ReviewError('运行结果绑定', 1, '选中运行的源码或配置已变化，请重跑后生成复核稿。', error_code=Code.REVIEW_BINDING_STALE)


def submit(args, root, profile, task, request):
    item = getattr(args, 'platform_review', None) if getattr(args, 'from_platform', False) else None
    source = item['url'] if item else source_path(args, root, task['id'])
    try:
        raw = source_text(args, root, task['id'])
    except (OSError, UnicodeError) as exc:
        raise ReviewError('评审文件', 1, '无法读取 Markdown：' + str(exc), error_code=Code.REVIEW_FILE_UNREADABLE) from exc
    expected = getattr(args, 'review_source_ref', None)
    if expected and hashlib.sha256(raw.encode('utf-8')).hexdigest() != expected['sha256']:
        raise ReviewError('评审文件', 1, '读取期间 Markdown 已改变，请停止编辑后用新请求编号提交。')
    value = _binding(root, task['id'], raw, current_only=bool(item))
    sections = _sections(raw, value)
    require_rechecks(value, sections)
    fresh, design, status, execution = snapshot(args, root, profile, task, value['bindings']['draft_id'], allow_incomplete=True)
    if not _usable_draft(value, fresh):
        raise ReviewError('绑定', 1, '评审绑定的任务、方案、批准状态、源码、策略、章节或运行与当前材料不同。', error_code=Code.REVIEW_BINDING_STALE)
    require_current_runs(root, profile, fresh['bindings'])
    review = compile_review(root, value, sections)
    if item:
        review.update(platform_author=item['author'], platform_url=item['url'])
    approval_choice = _value(sections, '评审信息', '批准方案与代码', False) if value.get('approval_needed') else ''
    if approval_choice not in ('', '是', '否'):
        raise ReviewError('评审信息', sections['评审信息']['line'], '批准方案与代码只能填写“是”或“否”，也可留空。')
    try:
        delivery.check_review_format(root, profile, task, review, fresh['bindings']['sections'], design)
    except (Invalid, ValueError, TypeError, KeyError) as exc:
        message = str(exc)
        section = getattr(exc, 'section', None) or '验收 ' + task['acceptance'][0]['id']
        raise ReviewError(section, sections.get(section, {'line': 1})['line'], '评审核查未通过：' + message) from exc
    approved, refs = None, []
    from contracts import identity
    self_review = identity(review['reviewer']) == identity(design['roles']['implementation_owner'])
    if approval_choice == '是' and not self_review:
        import designs
        from commands import local
        refs = list({ref['path']: ref for ref in fresh['bindings']['selected_runs'].values()}.values()) or fresh['bindings']['runs']
        approved = designs.approval_draft(design, review['reviewer'],
            _value(sections, '评审信息', '批准说明', False), mode='combined',
            section_ids=status['required_sections'],
            deletion_ids=[row['id'] for row in status['deletions'] if row['required']],
            history=[design_files.read(local(root, path)) for path in args.design_history],
            code_digest=fresh['bindings']['source_digest'], run_refs=refs)
    import issue_history
    issue_history.capture(request, task, review, [row['id'] for row in design['sections']])
    source_ref = request.publish('review-source.json', fresh['source_snapshot'])
    markdown = request.publish_text('review.md', raw)
    result = {'ok': True, 'review_submitted': True, 'artifact': request.publish('review.json', review, args.out),
              'review_markdown': markdown, 'review_source': source_ref, 'draft_id': value['bindings']['draft_id'],
              'review_file': str(source), 'summary': '评审已提交；业务验收仍由 accept 核查。',
              'next_action': 'tw team deliver --task ' + shlex.quote(task['id']) + ' --reason <不需要更新知识的理由>',
              'knowledge_next_action': '要更新知识时先验收：tw team accept --task ' + shlex.quote(task['id'])}
    result['submitted_at'] = item['updated_at'] if item else now()
    if item:
        result['platform_review'] = {key: item[key] for key in ('url', 'updated_at')}
    if approved is not None:
        result.update(approval=request.publish('approval.json', approved), approval_runs=refs)
    elif approval_choice == '是' and self_review:
        result['approval_gap'] = '实施者的意见已保存，不能生成独立合并批准；请由未参与实施的人评审。'
    return result


def mark_submitted(root, task_id, result):
    """Called under the material/cleanup lock after successful submission publication."""
    target, state_path = locations(root, task_id)
    state = _state(root, task_id)
    value = read(artifact_valid(root, state['generations'][result['draft_id']]))
    original = result['review_markdown']['sha256']
    marker = original if Path(result['review_file']).resolve() == target.resolve() else value['template_sha256']
    original_path = Path(result['review_file'])
    original = (original_path.relative_to(root).as_posix() if original_path.is_relative_to(root) else str(original_path))
    entry = {'review': result['artifact'], 'markdown': result['review_markdown'], 'source': result['review_source'],
             'input_markdown': original if not result['review_file'].startswith(('http://', 'https://')) else None,
             'binding': state['generations'][result['draft_id']], 'default_sha': marker,
             'submitted_at': result['submitted_at']}
    if result.get('platform_review'):
        entry['platform_review'] = result['platform_review']
    if result.get('approval'):
        entry['approval'] = result['approval']
    state['submitted'][result['draft_id']] = entry
    state['latest'] = entry
    write(state_path, state)


def exclude_own_approval(args, root, task_id):
    """A submission retry consumes its original inputs, not the approval it just produced."""
    if not args.request_id:
        return
    state = _state(root, task_id)
    if not state['submitted']:
        return
    try:
        raw = source_text(args, root, task_id)
        value = _binding(root, task_id, raw)
        approved = state['submitted'].get(value['bindings']['draft_id'], {}).get('approval')
        if not approved or (root / approved['path']).parent != directory(root, task_id, args.request_id):
            return
        from commands import local
        explicit = (getattr(args, 'material_selection', None) or {}).get('explicit', {})
        if 'approval' not in explicit:
            args.approval = [path for path in args.approval if artifact(root, local(root, path)) != approved]
        if 'run' not in explicit:
            args.run = [Path(ref['path']) for ref in value['bindings']['runs']]
    except (Invalid, OSError, ValueError, TypeError, KeyError):
        return  # The normal submission path reports malformed Markdown and material errors.


def from_run(args, root, profile, task, result, request):
    """Prepare an editable review after real execution; the review draft is a separate request."""
    selection = getattr(args, 'material_selection', None) or {}
    group = selection.get('effective') or selection.get('value')
    if not group or not args.design or not args.brief:
        return result  # Legacy execution without start has no prepared review inputs.
    import hashlib
    from artifacts import Request
    from cleanup import guard
    child_args = copy.copy(args)
    child_args.command, child_args.submit, child_args.out = 'review', False, None
    refs = list(group['runs'])
    if result['artifact'] not in refs:
        refs.append(result['artifact'])
    child_args.run = [Path(ref['path']) for ref in refs]
    from scenario_rounds import pending_action
    _, scenario_state = scenario_acceptance.current(root, profile, task, design_files.read(Path(root) / args.design),
                                                   [ref['path'] for ref in refs])
    try:
        validation.verify_runs(root, profile, task, [ref['path'] for ref in refs], live=False)
    except Invalid as exc:
        result['review_gap'] = str(exc)
        result['next_action'] = pending_action(root, task['id'])
        return result
    if scenario_state['summary_counts']['pending'] or scenario_state['summary_counts']['failed']:
        result['next_action'] = pending_action(root, task['id'])
        return result
    inputs = {'command': 'review', 'task': digest(task), 'profile': digest(profile),
              'source': validation.source_digest(root, profile), 'runs': refs,
              'options': {'submit': False, 'automatic': True},
              'history': history_inputs(root, task['id'], group),
              'context': group['context'], 'approvals': group['approvals']}
    child_id = 'run-review-' + hashlib.sha256(request.directory.name.encode('utf-8')).hexdigest()[:32]
    with guard(root):
        child = Request(root, task['id'], inputs, child_id)
    if child.cached is not None:
        reviewed = child.cached
    else:
        try:
            reviewed = child.finish(generate(child_args, root, profile, task, child))
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            reviewed = child.finish({'ok': False, 'problem': str(exc),
                'next_action': 'tw team review --task ' + shlex.quote(task['id'])})
    result['review_draft'] = reviewed
    if reviewed.get('review_file'):
        result['review_file'] = reviewed['review_file']
    result['next_action'] = reviewed.get('next_action', 'tw team review --task ' + shlex.quote(task['id']))
    return result
