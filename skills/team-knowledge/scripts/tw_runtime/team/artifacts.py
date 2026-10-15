"""Task-local request claims and complete, immutable output publication."""
import os
import re
import hashlib
import time
import uuid
from urllib.parse import urlsplit

from common import VERSION, Invalid, artifact, create, create_text, digest, ensure_local, inside, now, read, require, sha


def directory(root, task_id, request_id=None):
    request_id = request_id or uuid.uuid4().hex
    require(isinstance(request_id, str) and bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}', request_id)), 'Invalid request ID')
    return inside(root, f'.tw/local/tasks/{task_directory(task_id)}/requests/{request_id}', exists=False)


def task_directory(task_id):
    """Readable prefix plus a hash of the full identity, so foo-bar/baz#1 and foo/bar-baz#1 stay apart."""
    parts = urlsplit(task_id)
    issue = re.fullmatch(r'/([^/]+)/([^/]+)/issues/(\d+)', parts.path) if parts.scheme in ('http', 'https') else None
    if issue:
        slug = '-'.join(re.sub(r'[^a-z0-9]+', '-', part.lower()).strip('-') for part in issue.groups())
    else:
        name = parts.path.strip('/') if parts.scheme in ('http', 'https') else task_id
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40].rstrip('-') or 'task'
    return slug + '-' + hashlib.sha256(task_id.encode('utf-8')).hexdigest()[:8]


class Request:
    def __init__(self, root, task_id, inputs, request_id=None):
        self.root = root
        self.directory = directory(root, task_id, request_id)
        self.cached = None
        ensure_local(root)
        claim = {'task_id': task_id, 'input_digest': digest(inputs), 'pid': os.getpid(), 'started_at': now(),
                 'command': inputs.get('command'), 'phase': inputs.get('phase')}
        if inputs.get('command') == 'review':
            claim['submit'] = inputs.get('options', {}).get('submit', False)
        self.started = time.monotonic()
        if isinstance(inputs.get('task'), str) and re.fullmatch(r'[a-f0-9]{64}', inputs['task']):
            claim['task_digest'] = inputs['task']
        try:
            create(self.directory / 'request.json', claim)
        except FileExistsError:
            previous = read(self.directory / 'request.json')
            require(previous['input_digest'] == claim['input_digest'], 'Request ID already belongs to different inputs; use a new request ID')
            response = self.directory / 'response.json'
            if response.is_file():
                self.cached = read(response)
                self.validate(self.cached)
            else:
                active = True
                try:
                    os.kill(previous['pid'], 0)
                except ProcessLookupError:
                    active = False
                except PermissionError:
                    pass
                self.cached = {'ok': False, 'status': 'running' if active else 'interrupted',
                               'request_id': self.directory.name,
                               'problem': 'Request is still running' if active else 'Incomplete request; inspect its materials and use a new request ID'}

    def validate(self, result):
        for item in result.get('request_artifacts', []):
            path = inside(self.root, item['path'])
            require(path.is_file() and sha(path) == item['sha256'], 'Request artifact changed: ' + item['path'])

    def publish(self, name, value, out=None):
        path = inside(self.root, out, exists=False) if out else self.directory / name
        require(path.is_relative_to(self.root / '.tw/local'), 'Outputs must be under .tw/local/')
        try:
            create(path, value)
        except FileExistsError as exc:
            raise Invalid('Output already exists; existing evidence is never replaced') from exc
        return artifact(self.root, path)

    def finish(self, result):
        result = {**result, 'request_id': self.directory.name,
                  'request_directory': self.directory.relative_to(self.root).as_posix(),
                  'finished_at': now(), 'seconds': round(time.monotonic() - self.started, 3), 'version': VERSION}
        # Bind the files this request actually produced, including nested native reports.
        result['request_artifacts'] = [{'path': path.relative_to(self.root).as_posix(), 'sha256': sha(path)} for path in sorted(self.directory.rglob('*'))
            if path.is_file() and path.name != 'request.json' and not path.name.startswith('.')]
        if isinstance(result.get('artifact'), dict) and result['artifact'] not in result['request_artifacts']:
            result['request_artifacts'].append(result['artifact'])
        create(self.directory / 'response.json', result)
        return result

    def publish_text(self, name, value):
        path = inside(self.root, self.directory.relative_to(self.root).as_posix() + '/' + name, exists=False)
        create_text(path, value)
        return artifact(self.root, path)
