#!/usr/bin/env python3
"""Team workflow v5. Historical records require explicit adoption before current work."""
import argparse
import json
from pathlib import Path
import sys

from common import Invalid, artifact, inside, read, require, tool_identity, write, create, LOCATIONS
import versioning


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['project', 'snapshot', 'run', 'brief', 'knowledge', 'review-template',
                                      'verify', 'aggregate', 'migrate', 'evidence', 'version',
                                      'resume', 'handoff', 'progress', 'task-export', 'delivery-template', 'import-result',
                                      'status', 'stage-draft', 'agents', 'prepare', 'design-draft',
                                      'approval-draft', 'design-diff', 'schema', 'cleanup', 'upgrade', 'adopt', 'knowledge-template'])
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--profile', type=Path, default=Path('.team-workflow.json'))
    p.add_argument('--task', type=Path)
    p.add_argument('--with-task', action='append', default=[], type=Path, help='Additional v5 tasks sharing one validation batch')
    p.add_argument('--design', type=Path)
    p.add_argument('--approval', action='append', default=[], type=Path)
    p.add_argument('--design-history', action='append', default=[], type=Path)
    p.add_argument('--dependency', action='append', default=[], type=Path, help='Verified predecessor inputs {section,task,report}')
    p.add_argument('--context', type=Path, help='Prepared v5 context artifact; resolves task/design/brief inputs')
    p.add_argument('--acceptance', type=Path, help='Actual v5 business acceptance result')
    p.add_argument('--final-brief', type=Path, help='Re-read knowledge after writeback; original brief is retained')
    p.add_argument('--phase', choices=['acceptance', 'delivery'], default='delivery')
    p.add_argument('--kind', choices=['design', 'implementation'], default='implementation')
    p.add_argument('--format', choices=['json', 'text'], default='json')
    p.add_argument('--apply', action='store_true', help='Apply an explicitly reviewed cleanup plan or project upgrade')
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
    p.add_argument('--record', type=Path, help='JSON input for design, approval or legacy stage drafts')
    p.add_argument('--ledger', help='Sub-agent ledger name under .team-workflow/agents')
    p.add_argument('--plan', type=Path, help='Sub-agent plan [{id, purpose}] that creates a new ledger')
    p.add_argument('--mark', help='Sub-agent ID whose ledger status changes')
    p.add_argument('--status', dest='agent_status', help='New sub-agent status')
    return p


def local(root, value):
    require(value is not None, 'Missing input path')
    value = Path(value)
    if value.is_absolute():
        require(value.resolve().is_relative_to(root), 'Input must be inside the project')
        value = value.relative_to(root)
    return inside(root, value.as_posix())


def emit_file(root, out, data):
    require(out is not None and out.startswith('.team-workflow/'), '--out must be under .team-workflow/')
    path = inside(root, out, exists=False)
    try:
        create(path, data)
    except FileExistsError as exc:
        raise Invalid('Output already exists; use a new filename to preserve evidence') from exc
    return {'ok': True, 'artifact': artifact(root, path)}


def main(argv=None):
    args = parser().parse_args(argv)
    root = args.root.resolve()
    token = LOCATIONS.set({'repositories': {}, 'inputs': {}})
    import workflow_v4
    try:
        mappings = {'repositories': {}, 'inputs': {}}
        for kind, values in (('repositories', args.repository), ('inputs', args.input)):
            for value in values:
                name, separator, path = value.partition('=')
                require(separator and name and path and name not in mappings[kind], 'Expected unique name=/path mappings')
                mappings[kind][name] = path
        LOCATIONS.set(mappings)
        profile_path = root / args.profile
        version_info = None
        if args.command not in ('version', 'schema', 'migrate') and profile_path.is_file():
            version_info = versioning.ensure_tool_current(read(profile_path))
        import adoption
        historical = adoption.historical_input(args, root)
        if args.command not in ('adopt', 'status', 'schema', 'version', 'upgrade', 'migrate', 'project'):
            require(historical is None, 'Historical task requires adopt before current execution')
            require(not profile_path.is_file() or read(profile_path).get('schema_version') == 5,
                    'Upgrade the project and adopt its tasks before current execution')
        if args.command == 'version':
            result = tool_identity()
        elif args.command == 'adopt':
            result = adoption.draft(args, root)
        elif args.command == 'status' and historical is not None:
            result = adoption.status(historical)
        elif args.command == 'upgrade':
            result = versioning.upgrade(root, read(local(root, args.profile)),
                                        read(local(root, args.record)) if args.record else None)
            if args.apply and result['ok'] and result['status'] != 'current':
                write(profile_path, result.pop('profile'))
                result['applied'] = True
                result['next_action'] = 'Read the installed skill again, review the configuration diff, then adopt historical tasks.'
        elif args.command == 'agents':
            import stages
            require(bool(args.ledger), 'agents needs --ledger')
            require(not args.mark or bool(args.agent_status), '--mark needs --status')
            result = stages.agents(root, args.ledger, read(local(root, args.plan)) if args.plan else None,
                                   args.mark, args.agent_status, args.reason)
        elif args.command == 'stage-draft':
            raise Invalid('Historical stages are read-only; adopt the task and use current design/progress drafts')
        elif args.command == 'migrate':
            import check
            old = read(local(root, args.profile))
            validator = check.Check(root)
            validator.profile(old)
            require(not validator.problems, f'Invalid v1 profile: {validator.problems}')
            profile = {**old, 'schema_version': 3, 'required_checks': {'code': old['required_checks'], 'docs': []},
                       'inputs': [], 'environment_versions': {}, 'checks': {}}
            for key, row in old['checks'].items():
                profile['checks'][key] = {**row, 'cwd': '.', 'timeout': 300, 'format': 'command',
                                         'required_cases': [], 'required_env': []}
            result = {'profile': profile, 'requires_review': True,
                      'notes': ['Historical configuration conversion only. Run upgrade, declare actual coverage and adopt tasks before execution.']}
            if args.out:
                result = emit_file(root, args.out, result)
        else:
            result = workflow_v4.dispatch(args, root)
        if args.command == 'project' and version_info:
            result['version'] = version_info
            if version_info['status'] == 'project-outdated':
                result.update(ok=False, error_code='project-outdated', next_action=version_info['next_action'],
                              problem='Project configuration is older than the current workflow; preview upgrade, then adopt its tasks.')
        if not result.get('ok', True):
            result.setdefault('problem', '; '.join(str(v) for v in result.get('gaps', [])) or 'The operation is incomplete.')
            result.setdefault('next_action', 'Resolve the reported gap without replacing prior evidence.')
        print(workflow_v4.readable(result) if args.format == 'text' else json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 1
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'ok': False, 'scope': args.command, 'status': 'incomplete', 'problem': str(exc),
                  'error_code': 'invalid-or-incomplete-input',
                  'next_action': 'Inspect the named input; use adopt for historical tasks and preserve prior evidence.'}
        if isinstance(exc, versioning.Outdated):
            result.update(error_code=exc.error_code, next_action=exc.next_action, version=exc.version)
        if args.command in ('verify', 'aggregate'):
            result['layers'] = getattr(exc, 'layers', dict.fromkeys(('materials', 'execution', 'review', 'knowledge'), 'not-evaluated'))
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        LOCATIONS.reset(token)


if __name__ == '__main__':
    sys.exit(main())
