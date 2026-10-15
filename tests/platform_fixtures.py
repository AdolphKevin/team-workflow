"""Adapt the existing provider fixture data to the normalized project-script boundary."""
import copy
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

CONFIG = {'argv': ['python3', 'unused-fixture.py'], 'operations': ['task', 'commit', 'reference', 'ci-result']}


def task_data(issue, comments=None):
    identity = issue['html_url']
    parts = urlsplit(identity)
    repository = parts.netloc + '/' + '/'.join(parts.path.strip('/').split('/')[:2])
    def item(row, index, kind):
        created = row.get('created_at') or (datetime(2026, 10, 12, tzinfo=timezone.utc) + timedelta(seconds=index)).isoformat()
        return {'url': row['html_url'], 'author': row.get('user', {}).get('login', 'fixture'),
                'body': row.get('body') or '', 'created_at': created, 'updated_at': row.get('updated_at', created), 'kind': kind}
    return {'id': identity, 'url': identity, 'repository': repository,
            'state': issue.get('state', 'open'), 'owners': [v['login'] for v in issue.get('assignees', [])],
            'items': [item(issue, 0, 'task')] + [item(row, index + 1, 'comment')
                for index, row in enumerate(comments if comments is not None else issue.get('comments_data', []))],
            'raw': copy.deepcopy(issue)}


def transport(api):
    def call(root, operation, *arguments):
        def argument(name):
            return arguments[arguments.index(name) + 1]
        if operation == 'task':
            identity = argument('--id')
            path = urlsplit(identity).path.strip('/')
            endpoint = 'repos/' + path
            issue = api(endpoint)
            comments = api(endpoint + '/comments?per_page=100', paginate=True)
            return task_data(issue, comments)
        if operation == 'commit':
            repository = argument('--repo').removeprefix('github.com/')
            value = api(f'repos/{repository}/commits/{argument("--revision")}')
            return {'exists': True, 'revision': value['sha'], 'author': 'Fixture <test@example.invalid>',
                    'time': '2026-10-12T00:00:00Z'}
        if operation == 'reference':
            identity = argument('--url')
            parts = urlsplit(identity)
            path = parts.path.strip('/').split('/')
            repository, kind, identifier = '/'.join(path[:2]), path[2], path[3]
            if parts.fragment.startswith('issuecomment-'):
                endpoint = f'repos/{repository}/issues/comments/{parts.fragment[13:]}'
            elif kind in ('commit', 'blob'):
                endpoint = f'repos/{repository}/commits/{identifier}'
            else:
                endpoint = f'repos/{repository}/{kind}/{identifier}'
            api(endpoint)
            return {'reachable': True, 'kind': {'issues': 'task', 'pull': 'change', 'blob': 'file'}.get(kind, 'commit')}
        if operation == 'ci-result':
            locator = json.loads(argument('--locator'))
            repository = locator['repository'].removeprefix('github.com/')
            run = api(f'repos/{repository}/actions/runs/{locator["run_id"]}')
            job = api(f'repos/{repository}/actions/jobs/{locator["job_id"]}')
            artifact = api(f'repos/{repository}/actions/artifacts/{locator["artifact_id"]}')
            data = api(f'repos/{repository}/actions/artifacts/{locator["artifact_id"]}/zip', binary=True)
            (Path(argument('--output')) / 'archive.zip').write_bytes(data)
            return {'archive': 'archive.zip', 'provenance': {
                'repository': locator['repository'], 'revision': run['head_sha'],
                'run': {'id': locator['run_id'], 'attempt': locator['attempt'], 'latest_attempt': run['run_attempt'],
                        'succeeded': run['status'] == 'completed' and run['conclusion'] == 'success',
                        'url': f'https://github.com/{repository}/actions/runs/{locator["run_id"]}'},
                'job': {'id': locator['job_id'], 'name': job['name'], 'run_id': job['run_id'], 'attempt': job['run_attempt'],
                        'started_at': job['started_at'], 'finished_at': job['completed_at'],
                        'succeeded': job['status'] == 'completed' and job['conclusion'] == 'success'},
                'artifact': {'id': locator['artifact_id'], 'run_id': artifact['workflow_run']['id'],
                             'revision': artifact['workflow_run']['head_sha'], 'digest': artifact['digest'],
                             'created_at': artifact['created_at'], 'expired': artifact['expired']}}}
        raise AssertionError('Unexpected fixture operation: ' + operation)
    return call
