"""Task-local request claims and complete, immutable output publication."""
import os
from pathlib import Path
import re
import uuid

from common import Invalid, artifact, create, digest, git, inside, now, read, require, sha


def directory(root, task_id, request_id=None):
    request_id = request_id or uuid.uuid4().hex
    require(isinstance(request_id, str) and bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}', request_id)), 'Invalid request ID')
    return inside(root, f'.team-workflow/tasks/{digest(task_id)[:24]}/requests/{request_id}', exists=False)


class Request:
    def __init__(self, root, task_id, inputs, request_id=None):
        self.root = root
        self.directory = directory(root, task_id, request_id)
        self.cached = None
        try:
            ignored = git(root, 'check-ignore', '--no-index', '--', '.team-workflow/local.json').strip()
        except Invalid as exc:
            raise Invalid('Ignore .team-workflow/ before generating local materials') from exc
        require(bool(ignored), 'Ignore .team-workflow/ before generating local materials')
        claim = {'task_id': task_id, 'input_digest': digest(inputs), 'pid': os.getpid(), 'started_at': now()}
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
        require(path.is_relative_to(self.root / '.team-workflow'), 'Outputs must be under .team-workflow/')
        try:
            create(path, value)
        except FileExistsError as exc:
            raise Invalid('Output already exists; existing evidence is never replaced') from exc
        return artifact(self.root, path)

    def finish(self, result):
        result = {**result, 'request_id': self.directory.name,
                  'request_directory': self.directory.relative_to(self.root).as_posix()}
        # Bind the files this request actually produced, including nested native reports.
        result['request_artifacts'] = [{'path': path.relative_to(self.root).as_posix(), 'sha256': sha(path)} for path in sorted(self.directory.rglob('*'))
            if path.is_file() and path.name != 'request.json' and not path.name.startswith('.')]
        if isinstance(result.get('artifact'), dict) and result['artifact'] not in result['request_artifacts']:
            result['request_artifacts'].append(result['artifact'])
        create(self.directory / 'response.json', result)
        return result
