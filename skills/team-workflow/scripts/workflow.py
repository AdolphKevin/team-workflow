#!/usr/bin/env python3
"""Team development workflow v2. check.py remains the read-only v1 material checker."""
import argparse
import json
from pathlib import Path
import sys

from common import (Invalid, VERSION, artifact, binding, inside, obj, profile_valid,
                    read, require, task_valid, tool_identity, write)
import execution
import knowledge
import verification


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['project', 'snapshot', 'run', 'brief', 'knowledge', 'review-template',
                                      'verify', 'aggregate', 'migrate', 'evidence', 'version',
                                      'resume', 'handoff', 'import-result'])
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--profile', type=Path, default=Path('.team-workflow.json'))
    p.add_argument('--task', type=Path)
    p.add_argument('--out', help='New file under .team-workflow; existing files are never overwritten')
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
    require(not path.exists(), 'Output already exists; use a new filename to preserve evidence')
    write(path, data)
    return {'ok': True, 'artifact': artifact(root, path)}


def main(argv=None):
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'version':
            result = tool_identity()
        elif args.command == 'aggregate':
            mapping = {}
            for value in args.repository:
                key, path = value.split('=', 1)
                require(key not in mapping, 'Duplicate local repository mapping')
                mapping[key] = Path(path).expanduser().resolve()
            result = verification.aggregate(read(local(root, args.joint)), args.cs_skill, mapping)
        elif args.command == 'evidence':
            result = {'artifacts': [artifact(root, local(root, Path(name))) for name in args.path]}
        elif args.command == 'migrate':
            old = read(local(root, args.profile))
            # Use the legacy validator, retaining its requirements and semantics.
            import check
            validator = check.Check(root)
            validator.profile(old)
            require(not validator.problems, f'Invalid v1 profile: {validator.problems}')
            result = {**old, 'schema_version': 2, 'required_checks': {'code': old['required_checks'], 'docs': []},
                      'inputs': [], 'environment_versions': {}, 'checks': {}}
            for key, row in old['checks'].items():
                result['checks'][key] = {**row, 'cwd': '.', 'timeout': 300, 'format': 'command',
                                         'required_cases': [], 'required_env': []}
            result = {'profile': result, 'requires_review': True,
                      'notes': ['Commands retain command-only semantics. Select a native test format and required cases explicitly.',
                                'v1 delivery reports cannot be converted into execution evidence. Rerun checks.']}
            if args.out:
                result = emit_file(root, args.out, result)
        else:
            profile = profile_valid(read(local(root, args.profile)), root)
            if args.command in ('resume', 'handoff'):
                import handoffs
                skill = knowledge.skill_path(args.cs_skill)
                result = (handoffs.resume(root, profile, args.issue, skill) if args.command == 'resume' else
                          handoffs.draft(root, profile, args.issue, read(local(root, args.progress)), skill))
                if args.out:
                    status = result['ok']
                    result = {**emit_file(root, args.out, result), 'ok': status, 'scope': 'continuation-only'}
            elif args.command == 'import-result':
                import portable
                path, record = portable.import_result(root, profile, read(local(root, args.result)))
                result = {'ok': True, 'scope': 'execution-only', 'artifact': artifact(root, path), 'result': record['result']}
            elif args.command == 'project':
                result = {'ok': True, 'scope': 'project-configuration', 'workflow_version': VERSION,
                          'project': profile['project'], 'snapshot': binding(root, profile, {})['workspace']['digest']}
                try:
                    skill = knowledge.skill_path(args.cs_skill)
                    preflight = knowledge.call(skill, root, ['--check'], bootstrap=True)
                    knowledge.supported(preflight)
                    result['cs'] = {'status': 'ready', 'version': preflight.get('skill_version')}
                except Invalid as exc:
                    result['ok'] = False
                    result['cs'] = {'status': 'incomplete', 'reason': str(exc)}
            else:
                task = read(local(root, args.task))
                task_valid(task, profile, root)
                if args.command == 'snapshot':
                    result = binding(root, profile, task)
                    if args.out:
                        result = emit_file(root, args.out, result)
                elif args.command == 'run':
                    manifest = read(local(root, args.joint)) if args.joint else None
                    before = verification.participant_binding(manifest) if manifest else None
                    if manifest:
                        require(manifest['task_id'] == task['id'] and manifest['joint'] == profile['project'], 'Joint owner/task mismatch')
                    path, record = execution.run(root, profile, task, args.check, args.portable)
                    if manifest:
                        record['participants'] = before
                        record['participants_unchanged'] = before == verification.participant_binding(manifest)
                        write(path, record)
                    result = {'ok': record['source_unchanged'] and all(r['status'] == 'passed' for r in record['results'])
                              and record.get('participants_unchanged', True),
                              'scope': 'execution-only', 'artifact': artifact(root, path),
                              'checks': [{k: r[k] for k in ('id', 'status', 'detail')} for r in record['results']],
                              'source_unchanged': record['source_unchanged']}
                elif args.command == 'brief':
                    result = emit_file(root, args.out, knowledge.brief(root, task, knowledge.skill_path(args.cs_skill), args.path, args.symbol))
                elif args.command == 'knowledge':
                    require(bool(args.cs_task_id and args.disposition and args.reason and args.brief),
                            'knowledge needs --cs-task-id, --brief, --disposition and --reason')
                    result = emit_file(root, args.out, knowledge.finish(root, task, knowledge.skill_path(args.cs_skill),
                                       args.cs_task_id, local(root, args.brief), args.disposition, args.reason))
                elif args.command == 'review-template':
                    result = emit_file(root, args.out, verification.review_template(root, profile, task,
                                       local(root, args.brief), local(root, args.knowledge)))
                elif args.command == 'verify':
                    result = verification.verify(root, profile, task, read(local(root, args.report)), args.cs_skill)
                    result.pop('records')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 1
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'ok': False, 'scope': args.command, 'status': 'incomplete', 'problem': str(exc)}
        if args.command in ('verify', 'aggregate'):
            result['layers'] = getattr(exc, 'layers', dict.fromkeys(('materials', 'execution', 'review', 'knowledge'), 'not-evaluated'))
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
