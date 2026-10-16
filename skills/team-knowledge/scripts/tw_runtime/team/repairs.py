"""Concrete recovery commands for the seven user-facing workflow operations."""
from tw_runtime.team import platform_script as platform_read
import shlex
from pathlib import Path

from common import inside, sha
from error_codes import Code, fields

COMMANDS = {'start', 'run', 'review', 'accept', 'deliver', 'verify', 'status'}


def task_option(args):
    selection = getattr(args, 'material_selection', None) or {}
    identity = selection.get('task_id') or args.issue or args.task
    return '--task ' + (shlex.quote(str(identity)) if identity else '<任务文件>')


def project_command(root, name, options=''):
    return 'tw team ' + name + (' ' + options if options else '') + ' --root ' + shlex.quote(str(root.resolve()))


def task_command(root, task_id, name, extra=''):
    return project_command(root, name, '--task ' + shlex.quote(str(task_id)) + (' ' + extra if extra else ''))


def command(args, name, extra=''):
    return project_command(args.root, name, task_option(args) + (' ' + extra if extra else ''))


def review_submission(args, *, recheck=False):
    import reviews
    selection = getattr(args, 'material_selection', None) or {}
    identity = selection.get('task_id') or args.issue or args.task
    return reviews.submission_action(args.root.resolve(), str(identity), getattr(args, 'file', None), recheck=recheck)


def rerun_command(args, checks):
    names = [row['id'] for row in checks or [] if row.get('status') != 'passed']
    return command(args, 'run', ' '.join('--check ' + shlex.quote(name) for name in names))


def repeat_command(args):
    arguments = getattr(args, 'command_arguments', None)
    if arguments is None:
        extra = '--report ' + shlex.quote(str(args.report)) if args.report else ''
        return command(args, args.command, extra)
    business, skip = [], False
    for value in arguments:
        if skip:
            skip = False
        elif value in ('--request-id', '--out'):
            skip = True
        elif not value.startswith(('--request-id=', '--out=')):
            business.append(value)
    return shlex.join(['tw', 'team', *business])


CODE_ACTIONS = {
    Code.DESIGN_SNAPSHOT: lambda args, checks: '用当前格式的方案重新开工：' + command(args, 'start', '--design <当前格式方案.md>'),
    Code.SCENARIO_ACCEPTANCE: lambda args, checks: '按清单完成场景验收：' + command(args, 'scenarios pending'),
    Code.TESTER_CASES: lambda args, checks: '导入测试同事的用例集：' + command(args, 'scenarios import-cases', '<文件>'),
    Code.SCENARIO_RESULT: lambda args, checks: '修正结果文件中列出的行，再运行 ' + command(args, 'scenarios submit', '--results <文件>'),
    Code.SCENARIO_RESULTS_INCOMPLETE: lambda args, checks: '按列出的场景补齐结果后重新提交：' + command(args, 'scenarios submit', '--results <文件>'),
    Code.SCENARIO_FILE: lambda args, checks: '修正场景文件中列出的问题后重跑 ' + project_command(args.root, 'scenarios check', '<文件>'),
    Code.CASE_LIST: lambda args, checks: '修正用例文件中列出的问题后重跑 ' + command(args, 'scenarios import-cases', '<文件>'),
    Code.SCENARIO_COVERAGE: lambda args, checks: '按列出的用例补齐配对或场景后重跑 ' + command(args, 'scenarios coverage', '--pairs <配对文件>'),
    Code.ACCEPTANCE_ENTRY: lambda args, checks: '修正 .tw/config.json 的 acceptance_entries 入口声明，再运行原命令。',
    Code.PROJECT_UNINITIALIZED: lambda args, checks: '先预览项目初始化：tw init --root '
        + shlex.quote(str(args.root.resolve())) + '；确认预览后写入：tw init --root '
        + shlex.quote(str(args.root.resolve())) + ' --apply',
    Code.CHECK_CONFIG: lambda args, checks: '修正 .tw/config.json 中的 checks 登记，再运行原命令。',
    Code.CHECK_RESULT: lambda args, checks: '重跑检查，重新取得原始结果：' + rerun_command(args, checks),
    Code.APPROVAL_COMMIT: lambda args, checks: '把批准时的提交取到本地，再运行原命令。',
    Code.APPROVAL_SOURCE: lambda args, checks: '修正批准源码中的文件链接，以修正后的提交重新运行检查与评审，再取得当前材料的批准。',
    Code.ACCEPTANCE_STALE: lambda args, checks: '用当前材料重新验收：' + command(args, 'accept'),
    Code.ACCEPTANCE_MISSING: lambda args, checks: '先取得本任务的业务验收记录，再填写交付报告的 acceptance：' + command(args, 'accept'),
    Code.PLATFORM_CHANGED: lambda args, checks: '保留材料参数，以新请求重新核查平台记录：' + repeat_command(args),
    Code.BRIEF_INPUT: lambda args, checks: '生成本任务的知识简报：' + command(args, 'brief'),
    Code.DESIGN_HISTORY: lambda args, checks: '补齐方案历史后重新开工：' + command(args, 'start', '--design-history <历史方案文件>'),
}


def action(args, existing=None, error_code=None, checks=None, scenario_states=None):
    """依次采用代码对应的修复、来源下一步、命令默认下一步。"""
    if error_code == Code.SCENARIO_ACCEPTANCE and scenario_states and scenario_states.get('blocked') and not any(
            scenario_states.get(key) for key in ('failed', 'pending')):
        return '在评审的问题小节填写处置后，' + review_submission(args)
    if error_code in CODE_ACTIONS:
        return CODE_ACTIONS[error_code](args, checks)
    if args.command not in COMMANDS:
        return existing
    old = existing or ''
    selection = getattr(args, 'material_selection', None) or {}
    identity = selection.get('task_id') or args.issue or args.task
    if identity:
        old = old.replace('<身份>', shlex.quote(str(identity)))
    group = selection.get('effective') or selection.get('value') or {}
    if error_code == Code.CURRENT_MATERIALS and group:
        if platform_read.is_task(args.root.resolve(), str(identity), required=False):
            return '保留原证据，按 Issue 身份重新读取平台材料：' + command(args, 'start')
        def valid(ref):
            try:
                return bool(ref and sha(inside(args.root.resolve(), ref['path'])) == ref['sha256'])
            except (OSError, KeyError, TypeError, ValueError):
                return False
        task, design = group.get('task'), group.get('design')
        if valid(task) and valid(design):
            extra = '--design ' + shlex.quote(design['path'])
            for key, option in [('approvals', '--approval'), ('design_history', '--design-history')]:
                extra += ''.join(' ' + option + ' ' + shlex.quote(ref['path']) for ref in group[key] if valid(ref))
            recovery = ('tw team start --task ' + shlex.quote(task['path']) + ' ' + extra
                        + ' --root ' + shlex.quote(str(args.root.resolve())))
            return '保留原证据，用现存任务和方案重新开工：' + recovery
    if error_code == Code.CLOSE_AUTHORIZATION:
        source = args.report or (group.get('delivery_report') or {}).get('path')
        if source:
            source = (args.root / Path(source)).resolve()
            request_id = getattr(args, 'actual_request_id', None) or args.request_id or 'new'
            target = args.root.resolve() / '.tw/local' / ('delivery-repaired-' + request_id + '.json')
            return ('保留原报告：cp -n ' + shlex.quote(str(source)) + ' ' + shlex.quote(str(target))
                    + '；在新副本中补齐 confirmed_by 和 reference，再执行：'
                    + command(args, 'verify', '--report ' + shlex.quote(str(target))))
    if args.command == 'review' and error_code in (Code.REVIEW_BINDING_STALE, Code.REVIEW_FILE_UNREADABLE, Code.REVIEW_RUN_INCOMPLETE):
        return review_submission(args, recheck=True)
    if error_code == Code.REVIEW_INCOMPLETE and identity:
        return '按所列位置修正 Markdown 后，' + review_submission(args)
    if args.command == 'run' and checks:
        return (old + '；' if old else '') + '修复后重跑：' + rerun_command(args, checks)
    if error_code == Code.INDEPENDENCE:
        return '请由未参与实施的人实际评审或观察，' + review_submission(args)
    if error_code == Code.VALIDATION_ACTIVE:
        return '等待已有检查结束后核对：' + command(args, 'status', '--format text')
    if error_code == Code.REQUEST_ACTIVE:
        return '等待当前请求结束后核对：' + command(args, 'status', '--format text')
    if error_code == Code.TOOL_DEFECT:
        return (old + '；' if old else '') + '保留请求目录并核对安装：tw team project'
    if error_code in (Code.REQUEST_CONFLICT, Code.REQUEST_INPUT, Code.REQUEST_INTERRUPTED) and args.command != 'start' and identity:
        if args.command == 'review' and args.submit:
            return '保留原请求，按任务的评审提交方式继续：' + review_submission(args)
        return '保留原请求，省略 --request-id 使用新编号重试：' + command(args, args.command)
    if args.command in ('accept', 'deliver', 'verify'):
        if error_code == Code.APPROVAL_INCOMPLETE:
            return ('补齐批准后重试；简单任务填写评审中的批准字段：' + review_submission(args)
                    + '；中等以上任务先取得方案批准：' + command(args, 'approval-draft', '--reviewer <姓名> --mode plan'))
        if error_code == Code.REPORT_INCOMPLETE:
            return '用当前材料重新交付：' + command(args, 'deliver', '--reason <不需要更新知识的理由>')
    if old:
        return old
    if error_code == Code.TASK_INPUT:
        return '修正任务输入后重新开工：' + command(args, 'start', '--design <方案文件>')
    if args.command == 'start' or not identity:
        return '补齐任务和方案后开工：' + command(args, 'start', '--design <方案文件>')
    if args.command == 'review':
        return ('按所列小节修正后，' + review_submission(args) if args.submit else command(args, 'review'))
    if args.command in ('accept', 'deliver', 'verify'):
        if args.command == 'verify':
            return '用当前材料重新交付：' + command(args, 'deliver', '--reason <不需要更新知识的理由>')
        return '修复所列问题后重跑检查并复核：' + command(args, 'run') + '；' + command(args, 'review')
    if args.command == 'status':
        return '补齐材料后重新核对：' + command(args, 'start', '--design <方案文件>')
    return '修正所列输入后使用新请求编号：' + command(args, args.command)


def annotate(args, result):
    if (args.command in COMMANDS or result.get('error_code') in CODE_ACTIONS) and not result.get('ok', True):
        source = result.get('source_next_action', result.get('next_action'))
        if source is not None or result.get('error_code') == Code.TOOL_DEFECT or args.command == 'run' and result.get('checks'):
            result.setdefault('source_next_action', source)
        result['next_action'] = action(args, source,
                                       result.get('error_code'), result.get('checks'), result.get('scenario_states'))
    return result


def failure(args, exc, **extra):
    return annotate(args, {'ok': False, 'status': 'incomplete', 'problem': str(exc), **fields(exc),
                           'next_action': getattr(exc, 'next_action', None), **extra})


def recorded_action(root, task_id, command_name, claim, response, group=None):
    """进行中状态按已存代码重算修复指引，原请求记录继续保留。"""
    from workflow import parser
    args = parser().parse_args([command_name, '--root', str(root), '--task', task_id])
    args.submit = bool(claim.get('submit'))
    args.phase = claim.get('phase') or args.phase
    args.actual_request_id = response.get('request_id')
    args.material_selection = {'task_id': task_id, 'value': group}
    if group and group.get('delivery_report'):
        args.report = Path(group['delivery_report']['path'])
    source = response.get('review_file')
    if source and not source.startswith(('http://', 'https://')):
        args.file = Path(source)
    return annotate(args, dict(response)).get('next_action')
