"""`tw`: read and check project knowledge in `.tw/`."""
import argparse
import json
from pathlib import Path
import sys

from . import Invalid, audit, brief, cache, check, init, install, new, read
from .project import Project


def parser():
    root = argparse.ArgumentParser(prog='tw', description=__doc__)
    root.add_argument('--root', default='.', help='项目内任意路径，默认当前目录')
    root.add_argument('--repository', action='append', default=[], metavar='别名=路径',
                      help='共享仓的本机路径；按别名覆盖检出目录和用户级 repositories.json')
    sub = root.add_subparsers(dest='command', required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument('--repository', dest='sub_repository', action='append', default=[], metavar='别名=路径',
                        help='共享仓的本机路径，也可写在子命令之后')

    p = sub.add_parser('init', help='预览或建立最小的 .tw/ 布局')
    p.add_argument('--apply', action='store_true', help='实际写入；不加时只预览')
    p.add_argument('--guidance', action='store_true', help='同时维护 AGENTS.md 的知识指引块和 CLAUDE.md 的引用')
    p.add_argument('--source', action='append', default=[], help='概览来源，可重复；默认取 README.md')
    p.add_argument('--format', choices=('text', 'json'), default='text')

    p = sub.add_parser('brief', parents=[shared], help='读取与任务相关的知识（只读）')
    p.add_argument('--task', required=True)
    p.add_argument('--path', action='append', default=[], help='相关文件或目录，可重复')
    p.add_argument('--symbol', action='append', default=[], help='精确符号名，可重复')
    p.add_argument('--entry', action='append', default=[], help='指定条目，如 rules/x.md 或 common:rules/x.md')
    p.add_argument('--tag', action='append', default=[])
    p.add_argument('--budget', type=int, default=6000, help='输出字符上限，默认 6000')
    p.add_argument('--index', action='store_true', help='只列出条目索引，不输出正文')
    p.add_argument('--format', choices=('markdown', 'json'), default='markdown')

    p = sub.add_parser('read', parents=[shared], help='读取条目、已登记原文或仓库文件的全文')
    p.add_argument('target', nargs='?')
    p.add_argument('--section', help='只读取这一节')
    p.add_argument('--online', action='store_true', help='允许读取外部链接')
    p.add_argument('--list', action='store_true', help='列出已登记的原文')
    p.add_argument('--format', choices=('text', 'json'), default='text')

    p = sub.add_parser('new', help='生成 rule、decision 或 lesson 的骨架')
    p.add_argument('kind', choices=('rule', 'decision', 'lesson'))
    p.add_argument('--slug', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--scope', action='append', default=[], required=True)
    p.add_argument('--source', action='append', default=[], required=True)
    p.add_argument('--tag', action='append', default=[])
    p.add_argument('--status', default='accepted', choices=('accepted', 'rejected'))
    p.add_argument('--verified-at-head', action='store_true', help='声明已在当前 HEAD 核对过，写入 verified')
    p.add_argument('--format', choices=('text', 'json'), default='text')

    p = sub.add_parser('check', parents=[shared], help='结构检查（零写入，不执行测试）')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--cached', action='store_true', help='检查暂存区中的版本')
    group.add_argument('--base', help='与该提交比较，提示本分支改动了哪些知识的 scope')
    p.add_argument('--format', choices=('text', 'json'), default='text')

    p = sub.add_parser('audit', parents=[shared], help='知识库健康报告（只读）')
    p.add_argument('--links', action='store_true', help='在线检查外部链接')
    p.add_argument('--top', type=int, default=10)
    p.add_argument('--format', choices=('markdown', 'json'), default='markdown')

    p = sub.add_parser('cache', help='重建或清除本地缓存')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--rebuild', action='store_true')
    group.add_argument('--clear', action='store_true')

    p = sub.add_parser('version', help='版本与安装完整性')
    p.add_argument('--check-install', action='store_true')
    p.add_argument('--home', help=argparse.SUPPRESS)
    p = sub.add_parser('team', parents=[shared], add_help=False, help='团队任务与交付命令')
    p.add_argument('--root', dest='team_root', help='团队命令的项目目录，也可写在团队子命令之后')
    p.add_argument('--help', '-h', dest='team_help', action='store_true')
    p.add_argument('args', nargs=argparse.REMAINDER)
    return root


def emit(value, text=None, fmt='text', *, error=False):
    if error and fmt != 'json':
        print(f'tw: {value["problem"]}', file=sys.stderr)
        return
    if fmt == 'json' or text is None:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(text)


def main(argv=None):
    args = parser().parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == 'team':
            root = Path(args.team_root) if args.team_root is not None else root
            team = Path(__file__).resolve().parent / 'team'
            sys.path.insert(0, str(team))
            import workflow
            argv = ['--help'] if args.team_help else list(args.args)
            if not any(v == '--root' or v.startswith('--root=') for v in argv):
                argv += ['--root', str(root)]
            for repository in args.repository + args.sub_repository:
                argv += ['--repository', repository]
            return workflow.main(argv)
        if args.command == 'init':
            project = Project(root, require_config=False)
            result = init.run(project.root, apply=args.apply, guidance=args.guidance, sources=args.source)
            emit(result, init.render(result), args.format)
            return 0
        if args.command == 'version':
            if args.check_install:
                result = install.check_install(args.home)
                emit(result)
                return 0 if result['ok'] and result['installed_ok'] else 1
            emit({'version': install.VERSION, 'skill': str(install.SKILL)})
            return 0
        repositories = args.repository + getattr(args, 'sub_repository', [])
        project = Project(root, repositories, cached=getattr(args, 'cached', False),
                          require_config=args.command not in ('check',))
        if args.command == 'brief':
            paths = brief.relative_paths(root, args.path)
            result = brief.build(project, args.task, paths, args.symbol, args.entry, args.tag, args.budget, args.index)
            emit(result, result['markdown'], 'json' if args.format == 'json' else 'text')
            return 0
        if args.command == 'read':
            result = read.run(project, args.target, args.section, args.online, args.list)
            text = result.get('text') or ''.join(f'- {d["id"]}：{d["title"]}（{d["source"]}）\n' for d in result.get('documents', []))
            emit(result, text or '（没有已登记的原文）\n', args.format)
            return 0
        if args.command == 'new':
            result = new.run(project.root, args.kind, args.slug, args.title, args.scope, args.source, args.tag,
                             args.status, args.verified_at_head)
            emit(result, f'已创建 {result["path"]}\n{result["next"]}\n', args.format)
            return 0
        if args.command == 'check':
            result = check.run(project, base=args.base)
            emit(result, check.render(result), args.format)
            return 0 if result['ok'] else 1
        if args.command == 'audit':
            result = audit.run(project, links=args.links, top=args.top)
            emit(result, audit.render(result), 'json' if args.format == 'json' else 'text')
            return 0
        if args.command == 'cache':
            emit(cache.rebuild(project) if args.rebuild else cache.clear(project))
            return 0
    except Invalid as exc:
        emit({'ok': False, 'problem': str(exc)}, fmt=getattr(args, 'format', 'text'), error=True)
        return 2
    except Exception as exc:
        emit({'ok': False, 'problem': str(exc)}, fmt=getattr(args, 'format', 'text'), error=True)
        return 1
    return 2
