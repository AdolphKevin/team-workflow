#!/usr/bin/env python3
"""Team workflow command line. Every record uses the current contract (schema_version 5)."""
import argparse
import json
from pathlib import Path
import sys

from common import Invalid, read, require, tool_identity, LOCATIONS
import versioning


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['project', 'snapshot', 'run', 'brief', 'knowledge', 'review-template',
                                      'verify', 'aggregate', 'evidence', 'version',
                                      'resume', 'handoff', 'progress', 'task-export', 'delivery-template', 'import-result',
                                      'status', 'agents', 'prepare', 'design-draft',
                                      'approval-draft', 'design-diff', 'schema', 'cleanup', 'knowledge-template',
                                      'guidance'])
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--profile', type=Path, default=Path('.team-workflow.json'))
    p.add_argument('--task', type=Path)
    p.add_argument('--with-task', action='append', default=[], type=Path, help='Additional tasks sharing one validation batch')
    p.add_argument('--design', type=Path)
    p.add_argument('--approval', action='append', default=[], type=Path)
    p.add_argument('--design-history', action='append', default=[], type=Path)
    p.add_argument('--dependency', action='append', default=[], type=Path, help='Verified predecessor inputs {section,task,report}')
    p.add_argument('--context', type=Path, help='Prepared context artifact; resolves task/design/brief inputs')
    p.add_argument('--acceptance', type=Path, help='Actual business acceptance result')
    p.add_argument('--final-brief', type=Path, help='Re-read knowledge after writeback; original brief is retained')
    p.add_argument('--phase', choices=['acceptance', 'delivery'], default='delivery')
    p.add_argument('--kind', choices=['design', 'implementation'], default='implementation')
    p.add_argument('--format', choices=['json', 'text'], default='json')
    p.add_argument('--apply', action='store_true', help='Apply an explicitly reviewed cleanup plan or guidance blocks')
    p.add_argument('--dry-run', action='store_true', help='Preview only (cleanup default)')
    p.add_argument('--evidence-repository', help='Declared external repository for --path evidence')
    p.add_argument('--out', help='New file under .team-workflow; existing files are never overwritten')
    p.add_argument('--request-id', help='Stable ID for retrying one material-producing request')
    p.add_argument('--input', action='append', default=[], help='Local external file mapping name=/path')
    p.add_argument('--run', action='append', default=[], help='Execution/import record for a delivery template')
    p.add_argument('--review', type=Path)
    p.add_argument('--check', action='append', help='Run only selected checks; verification still requires all mandatory checks')
    p.add_argument('--cs-skill', type=Path)
    p.add_argument('--cs-task-id')
    p.add_argument('--brief', type=Path)
    p.add_argument('--knowledge', type=Path)
    p.add_argument('--disposition', choices=['none', 'reused', 'updated', 'added'])
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
    p.add_argument('--ledger', help='Sub-agent ledger name under .team-workflow/agents')
    p.add_argument('--plan', type=Path, help='Sub-agent plan [{id, purpose}] that creates a new ledger')
    p.add_argument('--mark', help='Sub-agent ID whose ledger status changes')
    p.add_argument('--status', dest='agent_status', help='New sub-agent status')
    p.add_argument('--scope', choices=['project', 'global', 'all'], default='all', help='guidance targets')
    p.add_argument('--home', type=Path, help='Home directory holding per-user agent files (default: current user)')
    p.add_argument('--file', help='Project-relative rules file for guidance (default: AGENTS.md); CLAUDE.md imports it')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    root = args.root.resolve()
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
        profile_path = root / args.profile
        if args.command not in ('version', 'schema', 'guidance') and profile_path.is_file():
            versioning.ensure_tool_current(read(profile_path))
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
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'ok': False, 'scope': args.command, 'status': 'incomplete', 'problem': str(exc),
                  'error_code': 'invalid-or-incomplete-input',
                  'next_action': 'Inspect the named input and preserve prior evidence.'}
        if isinstance(exc, versioning.Outdated):
            result.update(error_code=exc.error_code, next_action=exc.next_action, version=exc.version)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        LOCATIONS.reset(token)


if __name__ == '__main__':
    sys.exit(main())
