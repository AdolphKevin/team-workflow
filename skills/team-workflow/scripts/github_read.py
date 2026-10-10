"""Read-only GitHub transport. Credentials remain in the installed gh client."""
import json
import re
import subprocess
from urllib.parse import quote, unquote

from common import Invalid, require, text


def issue_ref(url):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)', text(url))
    require(bool(match) and match[2] not in ('.', '..'), 'Expected a github.com issue URL')
    return '/'.join(match.group(1, 2)), int(match[3])


def repository(value):
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_][A-Za-z0-9_.-]*', text(value))), 'Expected owner/repository')
    return value


def api(endpoint, paginate=False, binary=False):
    require(endpoint.startswith('repos/') and '..' not in endpoint.split('/'), 'Unsupported GitHub endpoint')
    argv = ['gh', 'api', '--method', 'GET', endpoint]
    if paginate:
        argv += ['--paginate', '--slurp']
    try:
        result = subprocess.run(argv, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid('GitHub read unavailable: ' + str(exc)) from exc
    # Do not expose gh's credential diagnostics or arbitrary downloaded HTML.
    require(result.returncode == 0, 'GitHub read failed: ' + endpoint.split('?')[0])
    if binary:
        return result.stdout
    try:
        data = json.loads(result.stdout)
        return [item for page in data for item in page] if paginate else data
    except (ValueError, TypeError) as exc:
        raise Invalid('Invalid GitHub response') from exc


def issue(url):
    repo, number = issue_ref(url)
    data = api(f'repos/{repo}/issues/{number}')
    require(not data.get('pull_request'), 'A pull request is not the canonical task issue')
    require(data.get('html_url') == url, 'Issue was redirected; use its canonical URL')
    data['comments_data'] = api(f'repos/{repo}/issues/{number}/comments?per_page=100', paginate=True)
    return data


def commit(repo, revision):
    repository(repo)
    require(bool(re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', text(revision))), 'Expected a full commit ID')
    result = api(f'repos/{repo}/commits/{revision}')
    require(result.get('sha') == revision, 'GitHub returned a different commit')
    return result


def reachable(url):
    """Resolve only supported stable GitHub references, never an arbitrary URL."""
    text(url)
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)/(commit|blob)/([a-f0-9]{40}|[a-f0-9]{64})(?:/([^?#]+))?(?:#L[0-9]+(?:-L[0-9]+)?)?', url)
    if match:
        repo, kind, revision, path = match.groups()
        commit(repo, revision)
        if kind == 'blob':
            require(bool(path), 'A source reference needs a file path')
            path = unquote(path)
            require(not path.startswith('/') and '..' not in path.split('/') and '\\' not in path, 'Invalid source reference path')
            result = api(f'repos/{repo}/contents/{quote(path, safe="/")}?ref={revision}')
            require(isinstance(result, dict) and result.get('type') == 'file', 'Reference is not an accessible file')
        else:
            require(path is None, 'Invalid commit reference')
        return
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)/(issues|pull)/(\d+)(?:#issuecomment-(\d+))?', url)
    if match:
        repo, kind, number, comment = match.groups()
        repository(repo)
        endpoint = f'repos/{repo}/issues/comments/{comment}' if comment else f'repos/{repo}/{"pulls" if kind == "pull" else "issues"}/{number}'
        data = api(endpoint)
        require(data.get('html_url') == url, 'Reference points to a different object')
        return
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)/actions/runs/(\d+)(?:/attempts/(\d+))?', url)
    if match:
        repo, run, attempt = match.groups()
        repository(repo)
        api(f'repos/{repo}/actions/runs/{run}' + (f'/attempts/{attempt}' if attempt else ''))
        return
    raise Invalid('Reference needs an accessible GitHub issue, comment, PR, Actions run or immutable commit/file URL')
