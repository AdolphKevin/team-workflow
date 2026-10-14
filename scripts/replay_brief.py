#!/usr/bin/env python3
"""Replay real tasks through `tw brief` and report recall against independently chosen expectations.

Input JSON: {"queries": [{"id": "...", "task": "...", "paths": [...], "symbols": [...], "expected": ["rules/x.md", ...]}]}
`expected` must be decided before running, by someone who did not tune the retrieval.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/team-knowledge/scripts'))

from tw_runtime import brief  # noqa: E402
from tw_runtime.project import Project  # noqa: E402


def replay(project_root, queries, budget=6000, repositories=()):
    project = Project(Path(project_root), repositories)
    rows, totals = [], {'expected': 0, 'rendered': 0, 'listed': 0}
    for query in queries:
        result = brief.build(project, query['task'], query.get('paths', []), query.get('symbols', []), budget=budget)
        rendered = {e['label'] for e in result['entries'] if e['rendered']}
        listed = {e['label'] for e in result['entries']}
        expected = set(query.get('expected', []))
        totals['expected'] += len(expected)
        totals['rendered'] += len(expected & rendered)
        totals['listed'] += len(expected & listed)
        rows.append({'id': query.get('id'), 'chars': result['chars'], 'expected': sorted(expected),
                     'missing': sorted(expected - listed), 'only_indexed': sorted((expected & listed) - rendered),
                     'extra': sorted(listed - expected)})
    expected = totals['expected'] or 1
    return {'queries': len(rows), 'recall_rendered': round(totals['rendered'] / expected, 3),
            'recall_listed': round(totals['listed'] / expected, 3), 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='repository with .tw/')
    parser.add_argument('--queries', required=True, type=Path)
    parser.add_argument('--budget', type=int, default=6000)
    parser.add_argument('--repository', action='append', default=[])
    args = parser.parse_args()
    queries = json.loads(args.queries.read_text(encoding='utf-8'))['queries']
    print(json.dumps(replay(args.root, queries, args.budget, args.repository), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
