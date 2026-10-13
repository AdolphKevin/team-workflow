"""Explicit project command execution and native result decoding."""
import html
import json
import os
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

from common import Invalid, inside, require


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
