#!/usr/bin/env python3
"""Capture this repository's real regressions, or verify their Actions artifact."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/team-workflow/scripts'))
from common import git, read, write
import execution
import portable


def profile():
    return {'schema_version': 3, 'project': 'team-workflow', 'context': ['AGENTS.md'],
            'knowledge': {'provider': 'cs', 'entry': '.codestable/wiki/INDEX.md'},
            'checks': {'regression': {'argv': ['python3', 'scripts/test.py', '--junitxml', '{output}/tests.xml'],
                'cwd': '.', 'timeout': 300, 'purpose': 'Workflow contract regressions; excludes real member acceptance',
                'format': 'junit', 'report': '{output}/tests.xml', 'artifacts': ['{output}/tests.evidence.json'],
                'required_cases': [], 'required_env': []}},
            'required_checks': {'code': ['regression'], 'docs': []}, 'risk_checks': {}, 'inputs': [],
            'environment_versions': {'python': ['python3', '--version']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-locator', type=Path)
    args = parser.parse_args()
    if args.import_locator:
        path, result = portable.import_result(ROOT, profile(), read(args.import_locator))
        portable.validate_import(ROOT, profile(), result)
        print(json.dumps({'ok': True, 'receipt': str(path), 'result': result['result']}, indent=2))
        return 0
    task = {'schema_version': 2, 'id': 'release-regression', 'base': git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
            'goal': 'Execute the release behavior regressions', 'non_goals': ['real member acceptance'],
            'kind': 'code', 'risks': [], 'acceptance': [{'id': 'A1', 'expectation': 'Every regression executes and passes', 'checks': ['regression']}]}
    path, record = execution.run(ROOT, profile(), task, portable=True)
    output = path.parent / 'regression'
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('directory=' + str(output) + '\n')
    result = record['results'][0]
    passed = record['source_unchanged'] and result['status'] == 'passed'
    print(json.dumps({'record': str(path), 'directory': str(output), 'status': result['status'],
                      'detail': result['detail'], 'source_unchanged': record['source_unchanged']}, indent=2))
    if not passed:
        for channel in ('stdout', 'stderr'):
            # Execution already redacted these original outputs before saving them.
            print(f'--- regression {channel} ---', file=sys.stderr)
            print((output / (channel + '.txt')).read_text(), file=sys.stderr)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
