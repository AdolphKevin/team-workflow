#!/usr/bin/env python3
"""Team development workflow v2. check.py remains the read-only v1 material checker."""
import argparse
import json
from pathlib import Path
import sys

from common import (Invalid, VERSION, artifact, binding, inside, obj, profile_valid,
                    read, require, task_valid, tool_identity, write, create, digest, sha, LOCATIONS, location_settings)
import execution
import knowledge
import verification


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['project', 'snapshot', 'run', 'brief', 'knowledge', 'review-template',
                                      'verify', 'aggregate', 'migrate', 'evidence', 'version',
                                      'resume', 'handoff', 'progress', 'task-export', 'delivery-template', 'import-result'])
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--profile', type=Path, default=Path('.team-workflow.json'))
    p.add_argument('--task', type=Path)
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
    request = None
    token = LOCATIONS.set({'repositories': {}, 'inputs': {}})
    try:
        mappings = {'repositories': {}, 'inputs': {}}
        for kind, values in (('repositories', args.repository), ('inputs', args.input)):
            for value in values:
                name, separator, path = value.partition('=')
                require(separator and name and path and name not in mappings[kind], 'Expected unique name=/path mappings')
                mappings[kind][name] = path
        LOCATIONS.set(mappings)

        if args.command == 'version':
            result = tool_identity()
        elif args.command == 'aggregate':
            mapping = {key: (root / Path(path).expanduser()).resolve() for key, path in location_settings(root)['repositories'].items()}
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
            result = {**old, 'schema_version': 3, 'required_checks': {'code': old['required_checks'], 'docs': []},
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
            task = read(local(root, args.task)) if args.task else None
            if args.command == 'task-export' and args.issue:
                import github_read, handoffs
                task = handoffs.task_source(github_read.issue(args.issue))['task']
            if task:
                task_valid(task, profile, root)
            producing = args.command in ('run', 'brief', 'knowledge', 'review-template', 'task-export',
                                          'delivery-template', 'handoff', 'progress', 'import-result') or bool(args.out)
            if producing:
                from artifacts import Request
                inputs = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
                          if key not in ('root', 'request_id', 'repository', 'input', 'cs_skill')}
                for key in ('task', 'brief', 'knowledge', 'report', 'joint', 'progress', 'result', 'review'):
                    value = getattr(args, key)
                    if value:
                        inputs[key] = {'content': sha(local(root, value))}
                inputs['run'] = [sha(local(root, value)) for value in args.run]
                inputs['binding'] = binding(root, profile, task or {})
                task_id = task['id'] if task else args.issue or (read(local(root, args.result))['repository'] if args.result else profile['project'])
                request = Request(root, task_id, inputs, args.request_id)
                if request.cached is not None:
                    print(json.dumps(request.cached, ensure_ascii=False, indent=2))
                    return 0 if request.cached.get('ok', True) else 1

            def emit(data, name=None):
                return {'ok': data.get('ok', True), 'artifact': request.publish(name or args.command + '.json', data, args.out)}

            if args.command in ('resume', 'handoff', 'progress'):

                import handoffs
                skill = knowledge.skill_path(args.cs_skill)
                if args.command == 'resume':
                    result = handoffs.resume(root, profile, args.issue, skill)
                elif args.command == 'progress':
                    result = handoffs.progress_draft(root, profile, args.issue, read(local(root, args.progress)), request.directory.name)
                else:
                    result = handoffs.draft(root, profile, args.issue, read(local(root, args.progress)), skill)
                if request:
                    result = {**emit(result), 'scope': 'continuation-only'}
            elif args.command == 'import-result':
                import portable
                path, record = portable.import_result(root, profile, read(local(root, args.result)), request.directory / 'import')
                result = {'ok': True, 'scope': 'execution-only',
                          'artifact': request.publish('import.json', record, args.out) if args.out else artifact(root, path), 'result': record['result']}
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
                require(task is not None, 'This command needs --task or task-export --issue')
                if args.command == 'task-export':
                    result = emit(task, 'task.json')
                elif args.command == 'delivery-template':
                    report = {'schema_version': 2, 'task_id': task['id'],
                              'runs': [local(root, Path(value)).relative_to(root).as_posix() for value in args.run],
                              'review': local(root, args.review).relative_to(root).as_posix(),
                              'knowledge': local(root, args.knowledge).relative_to(root).as_posix()}
                    if args.issue:
                        report.update(schema_version=3, issue=args.issue)
                    result = emit(report, 'delivery.json')
                elif args.command == 'snapshot':
                    result = binding(root, profile, task)
                    if args.out:
                        result = emit(result)
                elif args.command == 'run':
                    manifest = read(local(root, args.joint)) if args.joint else None
                    before = verification.participant_binding(manifest) if manifest else None
                    if manifest:
                        require(manifest['task_id'] == task['id'] and manifest['joint'] == profile['project'], 'Joint owner/task mismatch')
                    path, record = execution.run(root, profile, task, args.check, args.portable, request.directory / 'execution', publish=False)
                    if manifest:
                        record['participants'] = before
                        record['participants_unchanged'] = before == verification.participant_binding(manifest)
                    create(path, record)
                    result = {'ok': record['source_unchanged'] and all(r['status'] == 'passed' for r in record['results'])
                              and record.get('participants_unchanged', True),
                              'scope': 'execution-only', 'artifact': request.publish('run.json', record, args.out) if args.out else artifact(root, path),
                              'checks': [{k: r[k] for k in ('id', 'status', 'detail')} for r in record['results']],
                              'source_unchanged': record['source_unchanged']}
                elif args.command == 'brief':
                    result = emit(knowledge.brief(root, task, knowledge.skill_path(args.cs_skill), args.path, args.symbol))
                elif args.command == 'knowledge':
                    require(bool(args.cs_task_id and args.disposition and args.reason and args.brief),
                            'knowledge needs --cs-task-id, --brief, --disposition and --reason')
                    result = emit(knowledge.finish(root, task, knowledge.skill_path(args.cs_skill),
                                       args.cs_task_id, local(root, args.brief), args.disposition, args.reason))
                elif args.command == 'review-template':
                    result = emit(verification.review_template(root, profile, task,
                                       local(root, args.brief), local(root, args.knowledge), args.issue))
                elif args.command == 'verify':
                    result = verification.verify(root, profile, task, read(local(root, args.report)), args.cs_skill)
                    result.pop('records')
        if request:
            result = request.finish(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 1
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'ok': False, 'scope': args.command, 'status': 'incomplete', 'problem': str(exc)}
        if args.command in ('verify', 'aggregate'):
            result['layers'] = getattr(exc, 'layers', dict.fromkeys(('materials', 'execution', 'review', 'knowledge'), 'not-evaluated'))
        if request and request.cached is None:
            try:
                result = request.finish(result)
            except (OSError, Invalid):
                pass
        print(json.dumps(result, ensure_ascii=False))
        return 1
    finally:
        LOCATIONS.reset(token)


if __name__ == '__main__':
    sys.exit(main())
