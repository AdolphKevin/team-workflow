#!/usr/bin/env python3
"""Read this project's GitHub records through gh; see the task-platform decision."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit

REPOSITORY = 'github.com/AdolphKevin/team-workflow'
SLUG = REPOSITORY.split('/', 1)[1]
WEB = 'https://github.com/'
MAX_ARCHIVE = 64 * 1024 * 1024


class Refused(Exception):
    """A missing or inconsistent platform fact, safe to show to the caller."""


def require(condition, message):
    if not condition:
        raise Refused(message)


def field(row, name, expected):
    require(isinstance(row, dict) and name in row and type(row[name]) is expected,
            f'GitHub 字段缺失或类型错误：{name}')
    return row[name]


def text(row, name):
    value = field(row, name, str)
    require(bool(value.strip()), f'GitHub 字段为空：{name}')
    return value


def positive(value):
    require(type(value) is int and value > 0, '编号与尝试次数必须是正整数')
    return value


def instant(value):
    require(isinstance(value, str) and re.match(r'^\d{4}-\d\d-\d\dT', value), '平台时间格式错误')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.utcoffset() is not None, '平台时间缺少时区')
    return result


def revision(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', value),
            '必须使用完整提交号')
    return value


def repository(value):
    require(isinstance(value, str) and re.fullmatch(r'github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value)
            and all(p not in ('.', '..') for p in value.split('/')), '仓库身份必须是 github.com/所有者/仓库')
    return value.split('/', 1)[1]


def web_url(value):
    parts = urlsplit(value)
    require(parts.scheme == 'https' and parts.netloc == 'github.com' and not parts.query,
            '仅支持不含查询参数的 GitHub HTTPS 对象地址')
    path = parts.path.strip('/').split('/')
    require(len(path) >= 4 and all(p and p not in ('.', '..') for p in path), 'GitHub 对象地址格式错误')
    repository('github.com/' + '/'.join(path[:2]))
    return parts, '/'.join(path[:2]), path[2:]


def canonical(row, requested):
    require(text(row, 'html_url') == requested, '对象已重定向，请使用规范地址：' + text(row, 'html_url'))


class GitHub:
    def __init__(self):
        self.raw = []

    def request(self, endpoint, *, paginate=False, binary=False, missing=False, query=None):
        argv = ['gh', 'api', '--hostname', 'github.com', '--method', 'POST' if query else 'GET',
                '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: 2022-11-28', endpoint]
        if paginate:
            argv += ['--paginate', '--slurp']
        if query:
            # A fixed GraphQL query, never a mutation; gh retains its own credentials.
            argv += ['-f', 'query=' + query]
        result = subprocess.run(argv, capture_output=True, timeout=45)
        if result.returncode:
            status = re.search(rb'\(HTTP (\d{3})\)', result.stderr)
            code = status.group(1).decode() if status else '未知'
            if missing and code in (('404', '410', '422') if missing == 'commit' else ('404', '410')):
                return None
            raise Refused(f'GitHub 只读请求失败（HTTP {code}）：{endpoint}')
        if binary:
            return result.stdout
        value = json.loads(result.stdout)
        self.raw.append({'endpoint': endpoint, 'response': value})
        return value

    def pages(self, endpoint, key=None):
        pages = self.request(endpoint, paginate=True)
        require(isinstance(pages, list) and pages, 'gh --paginate --slurp 未返回分页数组')
        rows, totals = [], []
        for page in pages:
            if key:
                rows += field(page, key, list)
                totals.append(field(page, 'total_count', int))
            else:
                require(isinstance(page, list), 'GitHub 列表页不是数组')
                rows += page
        ids = [positive(field(row, 'id', int)) for row in rows]
        require(len(ids) == len(set(ids)), '分页中出现重复对象，读取期间列表可能已变化')
        require(not totals or all(total == len(rows) for total in totals), '分页总数不一致或读取不完整')
        return rows


def item(row, kind):
    created = text(row, 'created_at')
    updated = text(row, 'updated_at')
    require(instant(updated) >= instant(created), '对象编辑时间早于创建时间')
    require('body' in row and (row['body'] is None or isinstance(row['body'], str)), '对象正文缺失或类型错误')
    return {'url': text(row, 'html_url'), 'author': text(field(row, 'user', dict), 'login'),
            'created_at': created, 'updated_at': updated, 'body': row['body'] if row['body'] is not None else '',
            'kind': kind}


def edited_item(api, row, kind, typename, created):
    # REST updated_at on a PR moves with any activity (reviews, pushes), and REST reviews have
    # no edit time at all. GraphQL lastEditedAt is the body's own edit time; null means never edited.
    node = text(row, 'node_id')
    query = ('query { node(id: ' + json.dumps(node) + ') { ... on ' + typename
             + ' { id url body lastEditedAt } } }')
    response = api.request('graphql', query=query)
    require(isinstance(response, dict), '正文编辑时间响应不是对象')
    require(not response.get('errors'), '无法读取正文最后编辑时间')
    metadata = field(field(response, 'data', dict), 'node', dict)
    body = row['body'] if row.get('body') is not None else ''
    require(text(metadata, 'id') == node
            and text(metadata, 'url') == text(row, 'html_url')
            and (metadata.get('body') or '') == body, '对象归属或正文在读取期间变化')
    require('lastEditedAt' in metadata, '缺少正文最后编辑时间')
    edited = metadata['lastEditedAt']
    require(edited is None or isinstance(edited, str), '正文最后编辑时间类型错误')
    # Draft edits before publication are part of the initially published body.
    updated = edited if edited is not None and instant(edited) > instant(created) else created
    return item(dict(row, created_at=created, updated_at=updated), kind)


def review_item(api, row):
    return edited_item(api, row, 'review', 'PullRequestReview', text(row, 'submitted_at'))


def comments(api, slug, number, expected=None):
    rows = api.pages(f'repos/{slug}/issues/{number}/comments?per_page=100')
    if expected is not None:
        require(type(expected) is int and len(rows) == expected, '评论数量变化或读取不完整')
    return rows


def linked_issue(body, slug, number):
    # Match the closing keywords, not an incidental mention of another Issue.
    target = rf'(?:\#{number}|{re.escape(slug)}\#{number}|https://github\.com/{re.escape(slug)}/issues/{number})'
    return bool(re.search(r'(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?[ \t]+'
                          + target + r'(?![\w/#-])', body))


def task(api, identity):
    parts, slug, path = web_url(identity)
    require(not parts.fragment and len(path) == 2 and path[0] == 'issues'
            and path[1].isdigit() and int(path[1]) > 0, '任务必须是规范 Issue 地址')
    number = int(path[1])
    issue = api.request(f'repos/{slug}/issues/{number}')
    canonical(issue, identity)
    require('pull_request' not in issue, '需求必须登记在 Issue，不能用 PR 代替')
    issue_comments = comments(api, slug, number, field(issue, 'comments', int))
    first = item(issue, 'task')
    rest = [item(row, 'comment') for row in issue_comments]
    bodies = '\n'.join([first['body'], *(row['body'] for row in rest)])
    direct = {int(n) for n in re.findall(r'https://github\.com/' + re.escape(slug)
              + r'/pull/(\d+)(?![\w/-])', bodies)}
    pulls = api.pages(f'repos/{slug}/pulls?state=all&per_page=100')
    selected = {positive(field(row, 'number', int)) for row in pulls
                if linked_issue(row['body'] or '', slug, number)} | direct
    for pull_number in sorted(selected):
        pull = api.request(f'repos/{slug}/pulls/{pull_number}')
        canonical(pull, WEB + f'{slug}/pull/{pull_number}')
        require(text(field(field(pull, 'base', dict), 'repo', dict), 'full_name') == slug,
                '关联 PR 属于其他仓库')
        rest.append(edited_item(api, pull, 'change', 'PullRequest', text(pull, 'created_at')))
        rest += [item(row, 'comment') for row in comments(api, slug, pull_number, field(pull, 'comments', int))]
        reviews = api.pages(f'repos/{slug}/pulls/{pull_number}/reviews?per_page=100')
        rest += [review_item(api, row) for row in reviews]
        inline = api.pages(f'repos/{slug}/pulls/{pull_number}/comments?per_page=100')
        require(len(inline) == field(pull, 'review_comments', int), '行内评论数量变化或读取不完整')
        rest += [item(row, 'comment') for row in inline]
    rest.sort(key=lambda row: (instant(row['created_at']), row['url']))
    require(len({row['url'] for row in [first, *rest]}) == 1 + len(rest), '任务中出现重复对象地址')
    state = text(issue, 'state')
    require(state in ('open', 'closed'), 'Issue 状态无法映射')
    return {'id': identity, 'url': first['url'], 'repository': 'github.com/' + slug, 'state': state,
            'owners': [text(row, 'login') for row in field(issue, 'assignees', list)],
            'items': [first, *rest], 'raw': api.raw}


def commit(api, repo, commit_id):
    revision(commit_id)
    # The commit is a validated full SHA, so GitHub's 422 here means it is unknown.
    row = api.request(f'repos/{repository(repo)}/commits/{commit_id}', missing='commit')
    if row is None:
        return {'exists': False, 'revision': commit_id, 'author': None, 'time': None}
    require(text(row, 'sha') == commit_id, '平台返回的提交号与请求不同')
    author = field(field(row, 'commit', dict), 'author', dict)
    timestamp = text(author, 'date')
    instant(timestamp)
    return {'exists': True, 'revision': commit_id,
            'author': text(author, 'name') + ' <' + text(author, 'email') + '>', 'time': timestamp}


def reference(api, url):
    parts, slug, path = web_url(url)
    kind, identifier = path[:2]
    endpoint, output, exact = None, None, True
    if kind in ('issues', 'pull') and identifier.isdigit() and len(path) == 2:
        if parts.fragment:
            fragment = parts.fragment
            if re.fullmatch(r'issuecomment-[1-9]\d*', fragment):
                endpoint = f'repos/{slug}/issues/comments/{fragment.split("-")[1]}'
            elif kind == 'pull' and re.fullmatch(r'discussion_r[1-9]\d*', fragment):
                endpoint = f'repos/{slug}/pulls/comments/{fragment.removeprefix("discussion_r")}'
            elif kind == 'pull' and re.fullmatch(r'pullrequestreview-[1-9]\d*', fragment):
                endpoint = f'repos/{slug}/pulls/{identifier}/reviews/{fragment.split("-")[1]}'
            else:
                raise Refused('无法识别评论地址，不能退回父对象')
            output = {'reachable': True, 'kind': 'comment'}
        else:
            endpoint = f'repos/{slug}/' + ('issues/' if kind == 'issues' else 'pulls/') + identifier
            output = {'reachable': True, 'kind': 'task' if kind == 'issues' else 'change'}
    elif kind == 'commit' and len(path) == 2 and not parts.fragment:
        endpoint = f'repos/{slug}/commits/{quote(identifier, safe="")}'
        output, exact = {'reachable': True, 'kind': 'commit'}, False
    elif kind == 'blob' and len(path) >= 3 and not parts.fragment:
        revision(identifier)
        endpoint = f'repos/{slug}/contents/{quote("/".join(path[2:]), safe="/")}?ref={identifier}'
        output = {'reachable': True, 'kind': 'file', 'revision': identifier}
    require(endpoint is not None, '不支持的 GitHub 引用类型')
    row = api.request(endpoint, missing=True)
    if row is None:
        return {'reachable': False, 'kind': output['kind']}
    if exact:
        canonical(row, url)
    if kind == 'commit':
        output['revision'] = revision(text(row, 'sha'))
        canonical(row, WEB + f'{slug}/commit/' + output['revision'])
    if kind == 'blob':
        require(text(row, 'type') == 'file' and text(row, 'path') == '/'.join(path[2:]), '引用不是所请求文件')
    return output


def select(rows, identifier, label):
    matches = [row for row in rows if field(row, 'id', int) == identifier]
    require(len(matches) == 1, f'{label}不属于指定运行或尝试')
    return matches[0]


def ci_result(api, locator, output):
    require(isinstance(locator, dict) and set(locator) == {'run_id', 'attempt', 'job_id', 'artifact_id'},
            'locator 必须包含 run_id、attempt、job_id、artifact_id 四个正整数')
    for value in locator.values():
        positive(value)
    output = Path(output)
    require(not output.is_symlink() and output.is_dir() and not any(output.iterdir()), 'output 必须是现有空目录')
    run_id, attempt = locator['run_id'], locator['attempt']
    run = api.request(f'repos/{SLUG}/actions/runs/{run_id}')
    require(field(run, 'id', int) == run_id and field(run, 'run_attempt', int) == attempt,
            '运行不存在或所选尝试不是最新尝试')
    require(text(field(run, 'repository', dict), 'full_name') == SLUG
            and text(run, 'path') == '.github/workflows/validate.yml', '运行不属于本仓 validate.yml')
    canonical(run, WEB + f'{SLUG}/actions/runs/{run_id}')
    source = revision(text(run, 'head_sha'))
    require(text(run, 'status') == 'completed' and text(run, 'conclusion') == 'success', '运行尚未成功完成')
    jobs = api.pages(f'repos/{SLUG}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100', 'jobs')
    job = select(jobs, locator['job_id'], '任务')
    require(field(job, 'run_id', int) == run_id and field(job, 'run_attempt', int) == attempt
            and text(job, 'head_sha') == source, '任务不属于该运行、尝试或提交')
    name = text(job, 'name')
    matrix = re.fullmatch(r'validate \(([^\s()/]+)\)', name)
    require(matrix is not None, '任务名称不对应 validate.yml 中的 validate 标识')
    require(text(job, 'status') == 'completed' and text(job, 'conclusion') == 'success', '任务尚未成功完成')
    started, finished = text(job, 'started_at'), text(job, 'completed_at')
    require(instant(started) <= instant(finished), '任务时间范围错误')
    artifacts = api.pages(f'repos/{SLUG}/actions/runs/{run_id}/artifacts?per_page=100', 'artifacts')
    artifact = select(artifacts, locator['artifact_id'], '产物')
    relation = field(artifact, 'workflow_run', dict)
    require(field(relation, 'id', int) == run_id and text(relation, 'head_sha') == source
            and field(relation, 'repository_id', int) == field(run['repository'], 'id', int),
            '产物不属于该仓库、运行或提交')
    require(text(artifact, 'name') == f'workflow-python-{matrix.group(1)}-attempt-{attempt}',
            '产物名称与任务的 Python 版本或尝试不一致')
    expired = field(artifact, 'expired', bool)
    require(not expired, '产物已过期')
    created = text(artifact, 'created_at')
    require(instant(started) <= instant(created) <= instant(finished), '产物不在所选任务的时间范围内')
    digest = text(artifact, 'digest')
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', digest), '平台未提供 SHA-256 产物摘要')
    require(0 < field(artifact, 'size_in_bytes', int) <= MAX_ARCHIVE, '产物超过 64 MiB 或大小无效')
    data = api.request(f'repos/{SLUG}/actions/artifacts/{locator["artifact_id"]}/zip', binary=True)
    require(len(data) <= MAX_ARCHIVE and 'sha256:' + hashlib.sha256(data).hexdigest() == digest,
            '下载内容与平台提供的摘要不一致')
    archive = f'artifact-{artifact["id"]}.zip'
    with (output / archive).open('xb') as stream:
        stream.write(data)
    return {'archive': archive, 'provenance': {
        'repository': 'github.com/' + run['repository']['full_name'], 'revision': source,
        'run': {'id': run['id'], 'attempt': run['run_attempt'], 'latest_attempt': run['run_attempt'],
                'succeeded': run['status'] == 'completed' and run['conclusion'] == 'success', 'url': run['html_url']},
        'job': {'id': job['id'], 'name': name, 'run_id': job['run_id'], 'attempt': job['run_attempt'],
                'started_at': started, 'finished_at': finished,
                'succeeded': job['status'] == 'completed' and job['conclusion'] == 'success'},
        'artifact': {'id': artifact['id'], 'run_id': relation['id'], 'revision': relation['head_sha'],
                     'digest': digest, 'created_at': created, 'expired': expired}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('task').add_argument('--id', required=True)
    command = commands.add_parser('commit')
    command.add_argument('--repo', required=True)
    command.add_argument('--revision', required=True)
    commands.add_parser('reference').add_argument('--url', required=True)
    command = commands.add_parser('ci-result')
    command.add_argument('--locator', required=True)
    command.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        api = GitHub()
        if args.operation == 'task':
            value = task(api, args.id)
        elif args.operation == 'commit':
            value = commit(api, args.repo, args.revision)
        elif args.operation == 'reference':
            value = reference(api, args.url)
        else:
            value = ci_result(api, json.loads(args.locator), args.output)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0
    except (Refused, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        # Never relay gh stdout/stderr, signed download URLs, or environment values.
        message = str(exc) if isinstance(exc, Refused) else '平台读取失败：字段、JSON、文件或命令超时异常'
        print(message.splitlines()[0], file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
