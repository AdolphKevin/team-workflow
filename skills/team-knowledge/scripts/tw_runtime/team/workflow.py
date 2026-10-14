#!/usr/bin/env python3
"""Team workflow command line. Project and team records use data_version 1."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tw_runtime import Invalid as RuntimeInvalid
from common import Invalid, read, require, skill_resource, tool_identity, INSTALL_HOME, LOCATIONS


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['project', 'snapshot', 'run', 'brief', 'review-template',
                                      'verify', 'aggregate', 'evidence', 'version',
                                      'resume', 'handoff', 'progress', 'task-export', 'delivery-template', 'import-result',
                                      'status', 'agents', 'prepare', 'design-draft',
                                      'approval-draft', 'design-diff', 'schema', 'cleanup',
                                      'guidance', 'issue-draft', 'metrics'])
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--task', type=Path)
    p.add_argument('--with-task', action='append', default=[], type=Path, help='Additional tasks sharing one validation batch')
    p.add_argument('--design', type=Path)
    p.add_argument('--approval', action='append', default=[], type=Path)
    p.add_argument('--design-history', action='append', default=[], type=Path)
    p.add_argument('--dependency', action='append', default=[], type=Path, help='Verified predecessor inputs {section,task,report}')
    p.add_argument('--context', type=Path, help='Prepared context artifact; resolves task/design/brief inputs')
    p.add_argument('--phase', choices=['acceptance', 'delivery'], default='delivery')
    p.add_argument('--acceptance', type=Path, help='delivery-template: business acceptance record from verify --phase acceptance')
    p.add_argument('--kind', choices=['design', 'implementation'], default='implementation')
    p.add_argument('--format', choices=['json', 'text'], default='json')
    p.add_argument('--apply', action='store_true', help='Apply an explicitly reviewed cleanup plan or guidance blocks')
    p.add_argument('--dry-run', action='store_true', help='Preview only (cleanup default)')
    p.add_argument('--evidence-repository', help='Declared external repository for --path evidence')
    p.add_argument('--out', help='New file under .tw/local; existing files are never overwritten')
    p.add_argument('--request-id', help='Stable ID for retrying one material-producing request')
    p.add_argument('--input', action='append', default=[], help='Local external file mapping name=/path')
    p.add_argument('--run', action='append', default=[], help='Execution/import record for a delivery template')
    p.add_argument('--review', type=Path)
    p.add_argument('--check', action='append', help='Run only selected checks; verification still requires all mandatory checks')
    p.add_argument('--allow-modified-tool', action='store_true',
                   help='Run verification with a modified installation; recorded as tool.override in results')
    p.add_argument('--brief', type=Path)
    p.add_argument('--reason')
    p.add_argument('--path', action='append', default=[])
    p.add_argument('--symbol', action='append', default=[])
    p.add_argument('--report', type=Path)
    p.add_argument('--joint', type=Path)
    p.add_argument('--issue', help='Canonical GitHub issue URL')
    p.add_argument('--progress', type=Path, help='Handoff input draft; never a second task store')
    p.add_argument('--result', type=Path, help='GitHub Actions result locator')
    p.add_argument('--portable', action='store_true', help='Capture result.json for a portable CI artifact')
    p.add_argument('--repository', action='append', default=[], help='Local checkout mapping owner/repo=/path; not shared task data')
    p.add_argument('--record', type=Path, help='JSON input for design or approval drafts')
    p.add_argument('--ledger', help='Sub-agent ledger name under .tw/local/agents')
    p.add_argument('--plan', type=Path, help='Sub-agent plan [{id, purpose}] that creates a new ledger')
    p.add_argument('--mark', help='Sub-agent ID whose ledger status changes')
    p.add_argument('--status', dest='agent_status', help='New sub-agent status')
    p.add_argument('--scope', choices=['project', 'global', 'all'], default='all', help='guidance targets')
    p.add_argument('--reviewer', help='issue-draft: the named person asked to review the design')
    p.add_argument('--grant', choices=['synthetic-login'],
                   help='prepare: record the user\'s permission for the agent to sign in to declared synthetic accounts')
    p.add_argument('--confirmed-by', help='prepare --grant: the user who gave the permission')
    p.add_argument('--since', help='metrics: only requests started at or after this ISO time')
    p.add_argument('--cleanup-scope', choices=['requests', 'all'], default='requests',
                   help='cleanup: finished task requests only, or also unreferenced batches, imports and stale leases')
    p.add_argument('--older-than', type=int, default=14, help='cleanup --cleanup-scope all: minimum age in days')
    p.add_argument('--allow-large-evidence', action='store_true',
                   help='evidence: accept a file above the size limit (compiled executables are never accepted)')
    p.add_argument('--home', type=Path, help='Home directory holding per-user agent files (default: current user)')
    p.add_argument('--file', help='Project-relative rules file for guidance (default: AGENTS.md); CLAUDE.md imports it')
    return p


def _terminated(signum, frame):
    # Unwind normally: running checks are killed with their process group and validation markers are removed.
    raise SystemExit(128 + signum)


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
    args = parser().parse_args(argv)
    root = args.root.resolve()
    if args.allow_modified_tool:
        import os
        from common import ALLOW_MODIFIED
        os.environ[ALLOW_MODIFIED] = '1'
    home_token = INSTALL_HOME.set(args.home)
    token = LOCATIONS.set({'repositories': {}, 'inputs': {}})
    import commands
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
            result.setdefault('next_action', 'Resolve the reported gap without replacing prior evidence.')
        print(commands.readable(result) if args.format == 'text' else json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 1
    except (RuntimeInvalid, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'ok': False, 'scope': args.command, 'status': 'incomplete', 'problem': str(exc),
                  'error_code': getattr(exc, 'error_code', 'invalid-or-incomplete-input'),
                  'next_action': getattr(exc, 'next_action', None) or 'Inspect the named input and preserve prior evidence.'}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except Exception as exc:
        import commands
        print(json.dumps({'scope': args.command, **commands.tool_defect(exc)}, ensure_ascii=False))
        return 1
    finally:
        LOCATIONS.reset(token)
        INSTALL_HOME.reset(home_token)


if __name__ == '__main__':
    sys.exit(main())
