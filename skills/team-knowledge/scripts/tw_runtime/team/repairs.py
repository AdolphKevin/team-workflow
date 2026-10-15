"""Concrete recovery commands for the seven user-facing workflow operations."""
from tw_runtime.team import platform_script as platform_read
import shlex
from pathlib import Path

from common import inside, sha

COMMANDS = {'start', 'run', 'review', 'accept', 'deliver', 'verify', 'status'}


def task_option(args):
    selection = getattr(args, 'material_selection', None) or {}
    identity = selection.get('task_id') or args.issue or args.task
    return '--task ' + (shlex.quote(str(identity)) if identity else '<任务文件>')


def command(args, name, extra=''):
    return ('tw team ' + name + ' ' + task_option(args) + (' ' + extra if extra else '')
            + ' --root ' + shlex.quote(str(args.root.resolve())))


def action(args, problem, existing=None, error_code=None, checks=None):
    if args.command not in COMMANDS:
        return existing
    old = existing or ''
    selection = getattr(args, 'material_selection', None) or {}
    identity = selection.get('task_id') or args.issue or args.task
    if identity:
        old = old.replace('<身份>', shlex.quote(str(identity)))
    group = selection.get('effective') or selection.get('value') or {}
    if error_code == 'current-materials-incomplete' and group:
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
    if error_code == 'close-authorization-incomplete':
        source = args.report or (group.get('delivery_report') or {}).get('path')
        if source:
            source = (args.root / Path(source)).resolve()
            request_id = getattr(args, 'actual_request_id', None) or args.request_id or 'new'
            target = args.root.resolve() / '.tw/local' / ('delivery-repaired-' + request_id + '.json')
            return ('保留原报告：cp -n ' + shlex.quote(str(source)) + ' ' + shlex.quote(str(target))
                    + '；在新副本中补齐 confirmed_by 和 reference，再执行：'
                    + command(args, 'verify', '--report ' + shlex.quote(str(target))))
    if args.command == 'review' and any(text in problem for text in ('已变化', '已过期', '运行尚不能', '无法读取 Markdown')):
        return '先核对当前运行并生成复核稿：' + command(args, 'run') + '；' + command(args, 'review')
    if args.command == 'run' and checks:
        names = [row['id'] for row in checks if row.get('status') != 'passed']
        extra = ' '.join('--check ' + shlex.quote(name) for name in names)
        return (old + '；' if old else '') + '修复后重跑：' + command(args, 'run', extra)
    if 'tw team ' in old or 'npx ' in old:
        return old
    if 'implementation owner' in problem:
        return '请由未参与实施的人实际评审或观察，填写后提交：' + command(args, 'review', '--submit')
    if any(text in problem for text in ('still running', 'Validation is active', 'active validation')):
        return '等待已有检查结束后核对：' + command(args, 'status', '--format text')
    if error_code == 'tool-defect':
        return (old + '；' if old else '') + '保留请求目录并核对安装：tw team project'
    if args.command == 'start' or not identity:
        return '补齐任务和方案后开工：' + command(args, 'start', '--design <方案文件>')
    if 'Request ID' in problem or 'request ID' in problem:
        extra = '--submit' if args.command == 'review' and args.submit else ''
        return '保留原请求，省略 --request-id 使用新编号重试：' + command(args, args.command, extra)
    if args.command == 'review':
        return '按所列小节修正后提交：' + command(args, 'review', '--submit' if args.submit else '')
    if args.command in ('accept', 'deliver', 'verify'):
        if 'approval' in problem.lower() or '批准' in problem:
            return ('补齐批准后重试；简单任务填写评审中的批准字段：' + command(args, 'review', '--submit')
                    + '；中等以上任务先取得方案批准：' + command(args, 'approval-draft', '--reviewer <姓名> --mode plan'))
        if 'report' in problem.lower() or '交付报告' in problem or args.command == 'verify':
            return '用当前材料重新交付：' + command(args, 'deliver', '--reason <不需要更新知识的理由>')
        return '修复所列问题后重跑检查并复核：' + command(args, 'run') + '；' + command(args, 'review')
    if args.command == 'status':
        return '补齐材料后重新核对：' + command(args, 'start', '--design <方案文件>')
    return '修正所列输入后使用新请求编号：' + command(args, args.command)


def annotate(args, result):
    if args.command in COMMANDS and not result.get('ok', True):
        result['next_action'] = action(args, result.get('problem', ''), result.get('next_action'),
                                       result.get('error_code'), result.get('checks'))
    return result
