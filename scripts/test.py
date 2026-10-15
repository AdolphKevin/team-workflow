#!/usr/bin/env python3
"""Run actual unittest cases; write JUnit and evidence snapshots at execution time."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
import xml.etree.ElementTree as ET


class Result(unittest.TextTestResult):
    def __init__(self, *args, case_ids, **kw):
        super().__init__(*args, **kw)
        self.case_ids = case_ids
        self.cases = {}

    def record(self, test, kind, message=''):
        test = getattr(test, 'test_case', test)
        case_id = getattr(test, '_runner_case_id', test.id())
        # unittest reports class/module fixture errors against a synthetic test.
        # Attribute those errors to the affected real cases, retaining their names.
        scope = case_id.partition(' (')[2].removesuffix(')')
        affected = [case_id] if case_id in self.case_ids else [
            name for name in self.case_ids if scope and name.startswith(scope + '.')]
        if not affected:
            affected = self.case_ids
        priority = {'passed': 0, 'skipped': 1, 'failure': 2, 'error': 3}
        for name in affected:
            previous = self.cases.get(name)
            outcome = max((previous['kind'], kind), key=priority.get) if previous else kind
            detail = '\n'.join(filter(None, (previous['message'] if previous else '', message)))
            self.cases[name] = {'id': name, 'kind': outcome, 'message': detail,
                                'result': {'failure': 'failed', 'error': 'failed',
                                           'skipped': 'skipped'}.get(outcome, 'passed')}

    def startTest(self, test):
        super().startTest(test)
        self.record(test, 'passed')

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'error', self._exc_info_to_string(err, test))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'failure', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'skipped', reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            kind = 'failure' if issubclass(err[0], test.failureException) else 'error'
            self.record(test, kind, self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'failure', 'Unexpected success')


def flatten(tests):
    for test in tests:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def run_cases(case_ids):
    """Run cases with standard unittest fixture setup and cleanups."""
    tests = unittest.defaultTestLoader.loadTestsFromNames(case_ids)
    # A failed import has a synthetic ID. Keep its requested case identity so
    # it cannot mark unrelated, successfully executed members of a shard wrong.
    for case_id, loaded in zip(case_ids, tests):
        for test in flatten(loaded):
            test._runner_case_id = case_id
    factory = lambda *args, **kw: Result(*args, case_ids=case_ids, **kw)
    result = unittest.TextTestRunner(verbosity=2, resultclass=factory).run(tests)
    for case_id in case_ids:
        if case_id not in result.cases:
            result.cases[case_id] = worker_error(case_id, 'Worker did not report a result')
    return [result.cases[name] for name in case_ids]


def worker_error(case_id, message):
    return {'id': case_id, 'kind': 'error', 'result': 'failed', 'message': message}


def worker(case_ids, report, root):
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--_worker', str(report)],
                               input=json.dumps(case_ids), cwd=root, text=True, capture_output=True)
    output = completed.stdout + completed.stderr
    # Wait for process exit, including atexit handlers, before accepting its
    # report. A result returned before an abnormal shutdown is not success.
    if completed.returncode:
        message = f'Worker exited with code {completed.returncode}; affected cases:\n' + '\n'.join(case_ids)
        return [worker_error(name, message) for name in case_ids], output + '\n' + message + '\n'
    rows = json.loads(report.read_text())
    if [row['id'] for row in rows] != case_ids:
        raise RuntimeError('Worker report does not match assigned cases')
    return rows, output


def run_parallel(tests, workers, root):
    groups = {}
    for test in tests:
        cls = type(test)
        module = sys.modules[cls.__module__]
        # Keep class/module fixtures together when distributing individual cases.
        if any(hasattr(module, name) for name in ('setUpModule', 'tearDownModule')):
            key = ('module', cls.__module__)
        elif any(getattr(getattr(cls, name), '__func__', getattr(cls, name)) is not
                 getattr(getattr(unittest.TestCase, name), '__func__', getattr(unittest.TestCase, name))
                 for name in ('setUpClass', 'tearDownClass')):
            key = cls
        else:
            key = test.id()
        groups.setdefault(key, []).append(test.id())
    shards = [[] for _ in range(min(workers, len(groups)))]
    for ids in sorted(groups.values(), key=len, reverse=True):
        min(shards, key=len).extend(ids)
    cases = {}
    # Threads only supervise child interpreters; all tests execute in processes.
    # Balanced shards reuse interpreter imports instead of paying for each case.
    # Per-run report paths also isolate concurrent invocations of this runner.
    with tempfile.TemporaryDirectory(prefix='tw-tests-') as directory, ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(worker, ids, Path(directory) / f'{index}.json', root): ids
                   for index, ids in enumerate(shards)}
        for future in as_completed(pending):
            ids = pending[future]
            try:
                rows, output = future.result()
                sys.stderr.write(output)
            except Exception:
                message = 'Worker failed; affected cases:\n' + '\n'.join(ids) + '\n' + traceback.format_exc()
                print(message, file=sys.stderr)
                rows = [worker_error(case_id, message) for case_id in ids]
            cases.update((row['id'], row) for row in rows)
    return cases


def source_snapshot(root):
    return [{'repository': 'self', 'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for base in (root / 'skills/team-knowledge/scripts', root / 'tests', root / 'scripts')
            for p in sorted(base.rglob('*.py'))]


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('workers must be at least 1')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junitxml', required=True, type=Path)
    parser.add_argument('--workers', type=positive_int, default=min(os.cpu_count() or 1, 8),
                        help='worker processes (default: min(CPU count, 8)); 1 runs sequentially')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sources = source_snapshot(root)
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    tests = unittest.defaultTestLoader.discover(str(root / 'tests'))
    discovered = list(flatten(tests))
    case_ids = [test.id() for test in discovered]
    if args.workers == 1:
        rows = run_cases(case_ids)
        results = {row['id']: row for row in rows}
    else:
        results = run_parallel(discovered, args.workers, root)
    cases = [results[case_id] for case_id in case_ids]
    before = {s['path']: s['sha256'] for s in sources}
    after = {s['path']: s['sha256'] for s in source_snapshot(root)}
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    failures = sum(case['kind'] == 'failure' for case in cases)
    errors = sum(case['kind'] == 'error' for case in cases)
    skipped = sum(case['kind'] == 'skipped' for case in cases)
    suite = ET.Element('testsuite', tests=str(len(cases)), failures=str(failures), errors=str(errors), skipped=str(skipped))
    for case in cases:
        classname, name = case['id'].rsplit('.', 1)
        row = ET.SubElement(suite, 'testcase', classname=classname, name=name)
        if case['kind'] != 'passed':
            detail = ET.SubElement(row, case['kind'], message=case['message'].splitlines()[-1] if case['message'] else '')
            detail.text = case['message']
    args.junitxml.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(args.junitxml, encoding='utf-8', xml_declaration=True)
    args.junitxml.with_suffix('.evidence.json').write_text(json.dumps({'verified_at': started, 'sources': sources,
                  'cases': [{'id': case['id'], 'result': case['result']} for case in cases],
                  'changed_during_run': changed}, indent=2) + '\n')
    print(f'Ran {len(cases)} tests in {time.monotonic() - timer:.3f}s '
          f'with {args.workers} worker(s): failures={failures}, errors={errors}, skipped={skipped}', file=sys.stderr)
    if changed:
        print('Source changed during run: ' + ', '.join(changed), file=sys.stderr)
    return 0 if cases and not (failures or errors or skipped or changed) else 1


if __name__ == '__main__':
    if sys.argv[1:2] == ['--_worker']:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / 'tests'))
        rows = run_cases(json.loads(sys.stdin.read()))
        Path(sys.argv[2]).write_text(json.dumps(rows))
        sys.exit(0)
    sys.exit(main())
