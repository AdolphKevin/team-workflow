#!/usr/bin/env python3
"""Run actual unittest cases; write JUnit and evidence snapshots at execution time."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


class Result(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self.cases[test.id()] = {'id': test.id(), 'result': 'passed'}

    def addError(self, test, err):
        super().addError(test, err)
        self.cases[test.id()] = {'id': test.id(), 'result': 'failed'}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.cases[test.id()] = {'id': test.id(), 'result': 'failed'}

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.cases[test.id()] = {'id': test.id(), 'result': 'skipped'}

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.cases[test.id()] = {'id': test.id(), 'result': 'failed'}

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cases = {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junitxml', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sources = [{'repository': 'self', 'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
               for base in (root / 'skills/team-workflow/scripts', root / 'tests', root / 'scripts')
               for p in sorted(base.glob('*.py'))]
    started = datetime.now(timezone.utc).isoformat()
    tests = unittest.defaultTestLoader.discover(str(root / 'tests'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(tests)
    changed = [s['path'] for s in sources if hashlib.sha256((root / s['path']).read_bytes()).hexdigest() != s['sha256']]
    suite = ET.Element('testsuite', tests=str(result.testsRun), failures=str(len(result.failures)), errors=str(len(result.errors)))
    for case in result.cases.values():
        classname, name = case['id'].rsplit('.', 1)
        row = ET.SubElement(suite, 'testcase', classname=classname, name=name)
        if case['result'] == 'failed':
            ET.SubElement(row, 'failure', message='See runner output')
        elif case['result'] == 'skipped':
            ET.SubElement(row, 'skipped')
    args.junitxml.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(args.junitxml, encoding='utf-8', xml_declaration=True)
    args.junitxml.with_suffix('.evidence.json').write_text(json.dumps({'verified_at': started, 'sources': sources,
                  'cases': list(result.cases.values()), 'changed_during_run': changed}, indent=2) + '\n')
    return 0 if result.wasSuccessful() and result.testsRun > 0 and not changed and not result.skipped else 1


if __name__ == '__main__':
    sys.exit(main())
