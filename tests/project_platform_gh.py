#!/usr/bin/env python3
"""Offline gh executable: only the exact read requests supplied by a test exist."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('api')
    parser.add_argument('endpoint')
    parser.add_argument('--hostname')
    parser.add_argument('--method')
    parser.add_argument('-H', action='append')
    parser.add_argument('-f', action='append', default=[])
    parser.add_argument('--paginate', action='store_true')
    parser.add_argument('--slurp', action='store_true')
    args = parser.parse_args()
    assert args.api == 'api' and args.hostname == 'github.com'
    key = args.endpoint
    if key == 'graphql':
        assert args.method == 'POST' and len(args.f) == 1
        query = args.f[0].removeprefix('query=')
        assert query.startswith('query { ') and 'mutation' not in query
        match = re.search(r'node\(id: ("(?:[^"\\]|\\.)*")\)', query)
        assert match is not None
        key += ':' + json.loads(match.group(1))
    else:
        assert args.method == 'GET' and not args.f
    with Path(os.environ['TW_PROJECT_GH_LOG']).open('a') as stream:
        stream.write(json.dumps({'endpoint': key, 'method': args.method,
                                 'paginate': args.paginate, 'slurp': args.slurp}) + '\n')
    routes = json.loads(Path(os.environ['TW_PROJECT_GH_RESPONSES']).read_text())
    assert key in routes, 'Unexpected API request: ' + key
    route = routes[key]
    if 'node_of' in route:
        # A PullRequest node built from the current REST fixture, so body edits stay consistent.
        source = routes[route['node_of']]['body']
        route = {'body': {'data': {'node': {'id': source['node_id'], 'url': source['html_url'], 'body': source['body'],
                                            'lastEditedAt': route['lastEditedAt']}}}}
    if route.get('status', 200) != 200:
        print(f'gh: fixture failure (HTTP {route["status"]})\nprivate diagnostic must stay hidden', file=sys.stderr)
        return 1
    if 'base64' in route:
        assert not args.paginate and not args.slurp
        sys.stdout.buffer.write(base64.b64decode(route['base64']))
    else:
        body = route['body']
        if isinstance(body, list):
            assert args.paginate and args.slurp
        print(json.dumps(body))
    return 0


if __name__ == '__main__':
    sys.exit(main())
