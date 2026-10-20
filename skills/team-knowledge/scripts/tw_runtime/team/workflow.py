#!/usr/bin/env python3
"""Team workflow command line. Project and team records use data_version 1."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tw_runtime import Invalid as RuntimeInvalid
from common import Invalid, read, require, skill_resource, tool_identity, INSTALL_HOME, LOCATIONS


class TeamParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        value = super().parse_args(args, namespace)
        # Subparsers parse into a separate namespace; append without losing mappings before the command.
        value.repository = value.repository + getattr(value, 'sub_repository', []) + getattr(value, 'action_repository', [])
        for field in ('sub_repository', 'action_repository'):
            if hasattr(value, field):
                delattr(value, field)
        return value


def parser():
    p = TeamParser(prog='tw team', description=__doc__)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--repository', action='append', default=[], help='本机仓库映射 host/group/repo=/path')
    # Shared dispatch and request fingerprints retain their explicit defaults, without exposing unrelated options.
    p.set_defaults(task=None, issue=None, context=None, design=None, brief=None, approval=[], design_history=[],
                   dependency=[], with_task=[], run=[], review=None, report=None, progress=None, record=None,
                   acceptance=None, phase='delivery', kind='implementation', check=None, path=[], symbol=[],
                   reason=None, grant=None, confirmed_by=None, home=None, input=[], allow_modified_tool=False,
                   submit=False, from_platform=False, file=None, reviewer=None, confirmation=None, approval_mode=None, revision=None,
                   reconcile=None, sections=None)
    sub = p.add_subparsers(dest='command', required=True)

    locations = argparse.ArgumentParser(add_help=False)
    locations.add_argument('--root', type=Path, default=argparse.SUPPRESS)
    locations.add_argument('--repository', dest='sub_repository', action='append', default=[],
                           metavar='REPOSITORY', help='本机仓库映射 host/group/repo=/path')
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument('--format', choices=['json', 'text'], default='json')
    task = argparse.ArgumentParser(add_help=False)
    task.add_argument('--task',
                      help='任务文件或已开工的任务身份（本地编号、完整 Issue 地址）')
    task.add_argument('--issue', help='规范任务地址')
    task.add_argument('--context', type=Path, help='Prepared context artifact; resolves task/design/brief inputs')
    inputs = argparse.ArgumentParser(add_help=False)
    inputs.add_argument('--input', action='append', default=[], help='Local external file mapping name=/path')
    override = argparse.ArgumentParser(add_help=False)
    override.add_argument('--allow-modified-tool', action='store_true',
                          help='Run with a modified installation; verification records tool.override')
    home = argparse.ArgumentParser(add_help=False)
    home.add_argument('--home', type=Path, help='Home directory for installation checks or user agent files')
    request = argparse.ArgumentParser(add_help=False, parents=[override])
    request.add_argument('--out', help='New file under .tw/local; existing files are never overwritten')
    request.add_argument('--request-id', help='Stable ID for retrying one material-producing request')
    query = argparse.ArgumentParser(add_help=False)
    query.add_argument('--path', action='append', default=[])
    query.add_argument('--symbol', action='append', default=[])
    design = argparse.ArgumentParser(add_help=False)
    design.add_argument('--design', type=Path)
    history = argparse.ArgumentParser(add_help=False)
    history.add_argument('--design-history', action='append', default=[], type=Path)
    approvals = argparse.ArgumentParser(add_help=False, parents=[design, history])
    approvals.add_argument('--approval', action='append', default=[], type=Path)
    runs = argparse.ArgumentParser(add_help=False)
    runs.add_argument('--run', action='append', default=[], help='Execution/import record')
    dependencies = argparse.ArgumentParser(add_help=False)
    dependencies.add_argument('--dependency', action='append', default=[], type=Path,
                              help='Verified predecessor inputs {section,task,report}')
    report = argparse.ArgumentParser(add_help=False, parents=[approvals, runs, dependencies])
    report.add_argument('--brief', type=Path)
    report.add_argument('--review', type=Path)

    def command(name, summary, *parents):
        return sub.add_parser(name, help=summary, description=summary, parents=[locations, output, *parents])

    command('project', '核对项目配置、知识结构与安装', home, override)
    c = command('platform', '核对项目平台脚本的格式与已知提交')
    c.add_argument('--check', action='store_true')
    c.add_argument('--id', dest='platform_id', help='真实任务的规范地址')
    c.add_argument('--commit', help='本地已知提交，默认 HEAD')
    c.add_argument('--reference', help='待核对的链接，默认任务地址')
    c.add_argument('--locator', help='ci-result 的不透明 JSON 定位信息；声明该操作时必填')
    command('snapshot', '读取源码与任务的内容指纹', task, inputs)
    c = command('run', '执行项目登记的检查并保存结果', task, inputs, request, design)
    c.add_argument('--with-task', action='append', default=[], type=Path,
                   help='Additional tasks sharing one validation batch')
    c.add_argument('--check', action='append', help='Run selected checks; verification still requires mandatory checks')
    c.add_argument('--portable', action='store_true', help='Capture result.json for a portable CI artifact')
    command('brief', '保存本任务的项目知识简报', task, inputs, request, query)
    c = command('review', '生成 Markdown 评审或提交填写后的评审', task, inputs, request, approvals, runs, dependencies)
    c.add_argument('--brief', type=Path)
    submission = c.add_mutually_exclusive_group()
    submission.add_argument('--submit', action='store_true', help='核查 Markdown 并保存正式评审材料')
    submission.add_argument('--from-platform', action='store_true', help='读取变更请求最新的绑定评审并提交')
    c.add_argument('--file', type=Path, help='提交别处的 Markdown；默认使用任务目录中的 review.md')
    c = command('accept', '生成报告并核查业务验收材料', task, inputs, request, report, home)
    c.add_argument('--report', type=Path, help='Use an existing acceptance report instead of generating one')
    c = command('verify', '核查最终交付材料', task, inputs, request, home)
    c.add_argument('--report', type=Path)
    c = command('deliver', '依次核查业务验收、知识处置与最终交付', task, inputs, request, home)
    c.add_argument('--reason', help='没有知识改动时，说明不需要更新知识的理由')
    c = command('aggregate', '汇总多仓库的联合验证结果', inputs)
    c.add_argument('--joint', type=Path)
    c = command('evidence', '生成实际证据文件的引用', inputs)
    c.add_argument('--path', action='append', default=[])
    c.add_argument('--evidence-repository', help='Declared external repository for --path evidence')
    c.add_argument('--allow-large-evidence', action='store_true',
                   help='Accept a file above the size limit; compiled executables are never accepted')
    command('version', '读取工具版本与安装信息', home)
    c = command('handoff', '生成团队任务的实施或方案交接草稿', task, inputs, request, dependencies, home)
    c.add_argument('--progress', type=Path, help='Handoff input draft; never a second task store')
    c.add_argument('--kind', choices=['design', 'implementation'], default='implementation')
    c = command('progress', '生成平台任务的进度评论草稿', task, inputs, request)
    c.add_argument('--progress', type=Path, help='Progress input draft; never a second task store')
    command('task-export', '导出任务材料供后续步骤使用', task, inputs, request)
    c = command('delivery-template', '生成最终交付报告草稿', task, inputs, request, report)
    c.add_argument('--acceptance', type=Path, help='Business acceptance record produced by verification')
    c = command('import-result', '导入有来源证明的持续集成执行结果', inputs, request)
    c.add_argument('--result', type=Path, help='平台产物定位信息')
    c = command('status', '查看任务材料与下一步，成功核对后登记显式替换', task, inputs, design, history, runs)
    c.add_argument('--report', type=Path)
    c = command('agents', '查看或更新代理工作台账')
    c.add_argument('--ledger', help='Sub-agent ledger name under .tw/local/agents')
    c.add_argument('--plan', type=Path, help='Sub-agent plan [{id, purpose}] that creates a new ledger')
    c.add_argument('--mark', help='Sub-agent ID whose ledger status changes')
    c.add_argument('--status', dest='agent_status', help='New sub-agent status')
    c.add_argument('--reason')
    c = command('start', '建立开工上下文或核对接续条件与下一步', task, inputs, request, query, approvals, dependencies, home, runs)
    c.add_argument('--report', type=Path)
    c.add_argument('--grant', choices=['synthetic-login'], help='Record permission to sign in to declared synthetic accounts')
    c.add_argument('--confirmed-by', help='The user who gave the permission for --grant')
    c = command('design-draft', '生成本地或平台方案草稿', task, inputs, request, design)
    c.add_argument('--record', type=Path, help='已提交的 Markdown 方案原文；格式见 references/designs.md')
    c.add_argument('--reconcile', help='对账原因；绑定当前平台历史并从第 1 版重新开始')
    c = command('approval-draft', '生成具名评审人的方案批准草稿', task, inputs, request, approvals, runs)
    c.add_argument('--record', type=Path, help='JSON input for the approval draft')
    c.add_argument('--reviewer', help='批准人的姓名；替代 --record')
    c.add_argument('--confirmation', help='批准说明，可省略')
    c.add_argument('--mode', dest='approval_mode', choices=['plan', 'combined'], help='方案批准或方案与代码合并批准')
    c.add_argument('--revision', help='批准时变更请求的完整提交号')
    c.add_argument('--sections', help='逗号分隔的章节编号，或 all 选择全部现有章节')
    c.add_argument('--reconcile', help='对账原因；绑定当前平台历史重新确认批准')
    command('design-diff', '核对方案变化及受影响的章节', task, inputs, request, design, history)
    c = command('scenarios', '核对场景文件、导入用例与核对覆盖')
    actions = c.add_subparsers(dest='scenario_action', required=True)
    action_locations = argparse.ArgumentParser(add_help=False)
    action_locations.add_argument('--root', type=Path, default=argparse.SUPPRESS)
    action_locations.add_argument('--repository', dest='action_repository', action='append', default=[])
    action = actions.add_parser('check', help='核对场景文件', parents=[action_locations, output])
    action.add_argument('file', type=Path)
    action = actions.add_parser('import-cases', help='导入测试用例', parents=[action_locations, output])
    action.add_argument('--task', required=True)
    action.add_argument('file', type=Path)
    action = actions.add_parser('coverage', help='核对用例覆盖', parents=[action_locations, output])
    action.add_argument('--task', required=True)
    action.add_argument('--pairs', required=True, type=Path)
    action = actions.add_parser('pending', help='列出待执行场景', parents=[action_locations, output])
    action.add_argument('--task', required=True)
    action = actions.add_parser('submit', help='登记场景执行结果', parents=[action_locations, output])
    action.add_argument('--task', required=True)
    action.add_argument('--results', required=True, type=Path)
    action = actions.add_parser('carry', help='登记待判定场景的沿用（理由与改动范围）', parents=[action_locations, output])
    action.add_argument('--task', required=True)
    action.add_argument('--results', required=True, type=Path)
    command('schema', '列出团队材料模板与字段说明')
    c = command('cleanup', '预览或应用本机材料清理计划')
    c.add_argument('--apply', action='store_true', help='Apply an explicitly reviewed cleanup plan')
    c.add_argument('--dry-run', action='store_true', help='Preview only; also the default')
    c.add_argument('--plan', type=Path)
    c.add_argument('--cleanup-scope', choices=['requests', 'all'], default='requests')
    c.add_argument('--older-than', type=int, default=14, help='Minimum age in days for cleanup-scope all')
    c = command('guidance', '预览或更新项目和本机的流程指引', home)
    c.add_argument('--scope', choices=['project', 'global', 'all'], default='all')
    c.add_argument('--apply', action='store_true', help='Apply the reviewed guidance blocks')
    c.add_argument('--file', help='Project-relative rules file; defaults to AGENTS.md')
    c = command('issue-draft', '生成任务正文、方案评论和评审请求草稿', design)
    c.add_argument('--task', type=Path)
    c.add_argument('--with-task', action='append', default=[], type=Path)
    c.add_argument('--reviewer', help='The named person asked to review the design')
    c = command('metrics', '只读汇总任务的本机运行统计')
    c.add_argument('--task', type=Path)
    c.add_argument('--issue', help='规范任务地址')
    c.add_argument('--since', help='Only requests started at or after this ISO time')
    return p


def _terminated(signum, frame):
    # Unwind normally: running checks are killed with their process group and validation markers are removed.
    raise SystemExit(128 + signum)


def emit(result, fmt):
    import commands
    def public(value):
        if isinstance(value, dict):
            return {key: public(item) for key, item in value.items() if key != 'source_next_action'}
        if isinstance(value, list):
            return [public(item) for item in value]
        return value
    result = public(result)
    print(commands.readable(result) if fmt == 'text' else json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    import signal
    import threading
    previous = (signal.signal(signal.SIGTERM, _terminated)
                if threading.current_thread() is threading.main_thread() else None)
    try:
        return _main(argv)
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(arguments)
    args.command_arguments = arguments
    root = args.root.resolve()
    if args.allow_modified_tool:
        import os
        from common import ALLOW_MODIFIED
        os.environ[ALLOW_MODIFIED] = '1'
    home_token = INSTALL_HOME.set(args.home)
    token = LOCATIONS.set({'repositories': {}, 'inputs': {}})
    import commands
    from tw_runtime.team import platform_script as platform_read
    platform_read.clear_cache()
    platform_token = platform_read.PROJECT_ROOT.set(root)
    try:
        mappings = {'repositories': {}, 'inputs': {}}
        for kind, values in (('repositories', args.repository), ('inputs', args.input)):
            for value in values:
                name, separator, path = value.partition('=')
                require(separator and name and path and name not in mappings[kind], 'Expected unique name=/path mappings')
                mappings[kind][name] = path
        LOCATIONS.set(mappings)
        skill_resource()
        if args.command == 'version':
            result = tool_identity()
        elif args.command == 'platform':
            require(args.check and args.platform_id, 'platform 需要 --check --id <任务身份>')
            result = platform_read.check(root, args.platform_id, args.commit, args.reference, args.locator)
        elif args.command == 'guidance':
            import guidance
            result = guidance.run(root, args.scope, args.apply, args.home, args.file)
        elif args.command == 'agents':
            import agents
            require(bool(args.ledger), 'agents needs --ledger')
            require(not args.mark or bool(args.agent_status), '--mark needs --status')
            result = agents.agents(root, args.ledger, read(commands.local(root, args.plan)) if args.plan else None,
                                   args.mark, args.agent_status, args.reason)
        else:
            result = commands.dispatch(args, root)
        if not result.get('ok', True):
            result.setdefault('problem', '; '.join(str(v) for v in result.get('gaps', [])) or 'The operation is incomplete.')
            import repairs
            repairs.annotate(args, result)
            result.setdefault('next_action', 'Resolve the reported gap without replacing prior evidence.')
    except (RuntimeInvalid, OSError, ValueError, TypeError, KeyError) as exc:
        import repairs
        result = repairs.failure(args, exc, scope=args.command)
    except Exception as exc:
        import commands
        result = {'scope': args.command, **commands.tool_defect(exc)}
    finally:
        platform_read.PROJECT_ROOT.reset(platform_token)
        LOCATIONS.reset(token)
        INSTALL_HOME.reset(home_token)
    emit(result, args.format)
    return 0 if result.get('ok', True) else 1


if __name__ == '__main__':
    sys.exit(main())
