"""Explicit project command execution and native result decoding."""
import html
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

from common import (Invalid, artifact, binding, inside, now, require, task_valid,
                    tool_identity, write)


def redact(value):
    secrets = [v for k, v in os.environ.items() if re.search(r'(?i)(token|secret|password|credential|dsn|api_key)', k) and len(v) >= 4]
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, '<REDACTED>').replace(html.escape(secret), 'REDACTED')
    value = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*', r'\1REDACTED', value)
    value = re.sub(r'(://[^\s/:]+:)[^\s/@]+@', r'\1REDACTED@', value)
    return value


def execute(argv, cwd, timeout):
    start = time.monotonic()
    p = None
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=(os.name == 'posix'))
        try:
            out, err = p.communicate(timeout=timeout)
            state = 'finished'
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
            out, err = p.communicate()
            state = 'timeout'
        return {'state': state, 'exit_code': p.returncode, 'seconds': round(time.monotonic()-start, 3),
                'stdout': redact(out.decode(errors='replace')), 'stderr': redact(err.decode(errors='replace'))}
    except OSError as exc:
        return {'state': 'unavailable', 'exit_code': None, 'seconds': round(time.monotonic()-start, 3),
                'stdout': '', 'stderr': redact(str(exc))}
    except BaseException:
        if p and p.poll() is None:
            if os.name == 'posix':
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
            p.communicate()
        raise


def go_cases(output):
    cases, packages, running, seen_packages = {}, {}, set(), set()
    for line in output.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        require(isinstance(row, dict) and 'Action' in row and 'Package' in row, 'Invalid Go test event')
        seen_packages.add(row['Package'])
        action = row['Action']
        if row.get('Test'):
            key = row['Package'] + '::' + row['Test']
            if action == 'run':
                running.add(key)
            if action in ('pass', 'fail', 'skip'):
                state = {'pass': 'passed', 'fail': 'failed', 'skip': 'skipped'}[action]
                cases[key] = worse(cases.get(key, 'passed'), state)
                running.discard(key)
        elif action in ('pass', 'fail', 'skip'):
            packages[row['Package']] = action
    require(not running, 'Go result ends before test completion')
    require(packages and seen_packages == packages.keys() and all(v != 'fail' for v in packages.values()), 'Go package failure or incomplete result')
    return cases


def worse(a, b):
    order = {'passed': 0, 'skipped': 1, 'failed': 2}
    return max((a, b), key=order.get)


def junit_cases(path):
    root = ET.parse(path).getroot()
    require(root.tag in ('testsuites', 'testsuite'), 'Expected JUnit testsuite(s)')
    cases = {}
    for case in root.iter('testcase'):
        key = case.get('classname', '') + '::' + case.get('name', '')
        require(case.get('name'), 'JUnit test has no name')
        state = 'failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
        cases[key] = worse(cases.get(key, 'passed'), state)
    for suite in root.iter('testsuite'):
        if suite.get('tests') is not None:
            require(int(suite.get('tests')) == len(list(suite.iter('testcase'))), 'JUnit case count does not match declared total')
        require(suite.find('error') is None and suite.find('failure') is None, 'JUnit suite error')
        for key in ('errors', 'failures'):
            require(float(suite.get(key, '0')) == 0, 'JUnit suite declares failures')
    return cases


def decode(check, result, report_path=None):
    if result['state'] != 'finished':
        return result['state'], {}, result['state']
    if result['exit_code'] != 0:
        return 'failed', {}, f'Command exit {result["exit_code"]}'
    if check['format'] == 'command':
        return 'passed', {}, 'Command completed; behavior is assessed separately in review'
    try:
        cases = go_cases(result['stdout']) if check['format'] == 'go-json' else junit_cases(report_path)
        require(bool(cases), 'Zero test cases')
        require(all(v != 'failed' for v in cases.values()), 'A test case failed')
        required = check['required_cases'] or list(cases)
        for key in required:
            require(cases.get(key) == 'passed', f'Required case missing or not passed: {key}')
            # Selecting a Go parent must not hide a skipped child.
            if check['format'] == 'go-json':
                require(all(v == 'passed' for k, v in cases.items() if k.startswith(key + '/')), f'Required child did not pass: {key}')
        return 'passed', cases, 'Required test cases executed and passed'
    except (Invalid, OSError, ValueError, TypeError, ET.ParseError) as exc:
        return 'incomplete', {}, str(exc)


def output_path(root, directory, value):
    require(value.startswith('{output}/'), 'Expected an output artifact')
    relative = value[len('{output}/'):]
    path = inside(directory, relative, exists=False)
    require(path.resolve().is_relative_to(root.resolve()), 'Output escapes project')
    return path


def run(root, profile, task, selected=None, portable=False):
    required = task_valid(task, profile, root)
    selected = selected if selected is not None else required
    require(set(selected) <= profile['checks'].keys(), 'Unknown selected check')
    tools_before = tool_identity()
    before = binding(root, profile, task)
    if portable:
        from portable import source_state, capture_result
        portable_before = source_state(root, profile)
    run_id = uuid.uuid4().hex
    directory = inside(root, '.team-workflow/runs/' + run_id, exists=False)
    directory.mkdir(parents=True, exist_ok=False)
    started = now()
    versions = {'python': sys.version.split()[0]}
    for key, argv in profile['environment_versions'].items():
        result = execute(argv, root, 15)
        versions[key] = {k: v for k, v in result.items() if k != 'seconds'}
    results = []
    for key in selected:
        check = profile['checks'][key]
        out = directory / key
        out.mkdir()
        argv = [x.replace('{output}', str(out)) for x in check['argv']]
        # Secrets belong in environment variables, never argv or version records.
        require(all(redact(x) == x for x in argv), 'Pass credentials via environment, not command arguments')
        missing = [name for name in check['required_env'] if not os.environ.get(name)]
        result = ({'state': 'unavailable', 'exit_code': None, 'seconds': 0, 'stdout': '',
                   'stderr': 'Missing required environment names: ' + ', '.join(missing)} if missing
                  else execute(argv, inside(root, check['cwd']), check['timeout']))
        # Native reports and declared artifacts are redacted before keeping them.
        declared = ([check['report']] if check.get('report') else []) + check.get('artifacts', [])
        artifacts, artifact_errors = [], []
        for value in declared:
            path = output_path(root, out, value)
            try:
                require(not path.is_symlink(), 'Output artifacts cannot be symlinks')
                content = path.read_text(encoding='utf-8')
                path.write_text(redact(content), encoding='utf-8')
                artifacts.append(artifact(root, path))
            except (OSError, UnicodeError, Invalid) as exc:
                artifact_errors.append(str(exc))
        report = output_path(root, out, check['report']) if check.get('report') else None
        status, cases, detail = decode(check, result, report)
        if artifact_errors and status == 'passed':
            status, detail = 'incomplete', '; '.join(artifact_errors)
        for channel in ('stdout', 'stderr'):
            path = out / (channel + '.txt')
            path.write_text(result[channel] or '(empty)\n', encoding='utf-8')
            artifacts.append(artifact(root, path))
        results.append({'id': key, 'argv': argv, 'cwd': check['cwd'], 'status': status,
                        'state': result['state'], 'exit_code': result['exit_code'], 'seconds': result['seconds'],
                        'cases': cases, 'detail': detail, 'artifacts': artifacts})
    after = binding(root, profile, task)
    tools_after = tool_identity()
    finished = now()
    if portable:
        portable_after = source_state(root, profile)
        for row in results:
            capture_result(directory / row['id'], profile['checks'][row['id']], row,
                           portable_before, portable_after, versions, started, finished, tools_before, tools_after)
    record = {'schema_version': 2, 'kind': 'execution', 'id': run_id, 'project': profile['project'],
              'task_id': task['id'], 'started_at': started, 'finished_at': finished, 'tools': tools_before,
              'binding': before, 'source_unchanged': before == after and tools_before == tools_after, 'environment_versions': versions,
              'required_checks': required, 'results': results}
    write(directory / 'run.json', record)
    return directory / 'run.json', record
