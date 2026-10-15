"""Validated, read-only calls to a project's platform script; no provider implementation."""
import copy
import ipaddress
from contextvars import ContextVar
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

from common import Invalid, create, digest, obj, read, require, sha, strings, text
from tw_runtime.project import platform_problems

_CACHE = {}
PROJECT_ROOT = ContextVar('platform_project_root', default=None)


def clear_cache():
    _CACHE.clear()


def project_root(root=None):
    return Path(root or PROJECT_ROOT.get() or Path.cwd()).resolve()


def task_url(value):
    parts = urlsplit(text(value))
    require(parts.scheme in ('http', 'https') and bool(parts.hostname) and not parts.username and not parts.password,
            '任务身份必须是 http(s) 地址')
    return value


def is_task(root, identity, *, required=True):
    if not isinstance(identity, str) or not identity.startswith(('http://', 'https://')):
        return False
    task_url(identity)
    try:
        configuration(root)
    except Invalid:
        if required:
            raise
        return False
    return True


def repository(value):
    text(value)
    host, separator, path = value.partition('/')
    require(separator and '://' not in value and not re.search(r'\s', value)
            and not any(char in host for char in '@[]?#') and all(part not in ('', '.', '..') for part in value.split('/')),
            '仓库身份必须是 git 远端规范化后的 主机/路径')
    if ':' in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise Invalid('仓库主机须为规范化名称或 IPv6 地址，不含账号和端口') from exc
    return value


def timestamp(value):
    require(isinstance(value, str) and bool(re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:', value)),
            '时间必须是带时区的 ISO 8601 字符串')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise Invalid('时间必须是带时区的 ISO 8601 字符串') from exc
    require(result.utcoffset() is not None, '时间必须带时区')
    return result


def revision(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', value)),
            '提交号必须是 40 或 64 位十六进制')
    return value


def _argument(arguments, name):
    require(arguments.count(name) == 1 and arguments.index(name) + 1 < len(arguments), '平台操作缺少参数 ' + name)
    return arguments[arguments.index(name) + 1]


def _identifier(value):
    require((type(value) is int and value > 0) or (isinstance(value, str) and bool(value.strip())),
            '来源编号必须是正整数或非空字符串')


def provenance(value):
    obj(value, {'repository', 'revision', 'run', 'job', 'artifact'})
    repository(value['repository']); revision(value['revision'])
    run, job, artifact = value['run'], value['job'], value['artifact']
    obj(run, {'id', 'attempt', 'latest_attempt', 'succeeded', 'url'})
    obj(job, {'id', 'name', 'run_id', 'attempt', 'started_at', 'finished_at', 'succeeded'})
    obj(artifact, {'id', 'run_id', 'revision', 'digest', 'created_at', 'expired'})
    for item in (run, job, artifact):
        _identifier(item['id'])
    for item in (job, artifact):
        _identifier(item['run_id'])
    for attempt in (run['attempt'], run['latest_attempt'], job['attempt']):
        require(type(attempt) is int and attempt > 0, '来源 attempt 必须是正整数')
    for item in (run, job):
        require(type(item['succeeded']) is bool, '来源 succeeded 必须是布尔值')
    require(type(artifact['expired']) is bool, '来源 expired 必须是布尔值')
    task_url(run['url']); text(job['name']); revision(artifact['revision'])
    require(isinstance(artifact['digest'], str) and bool(re.fullmatch(r'sha256:[a-f0-9]{64}', artifact['digest'])),
            'Provider did not supply an artifact digest')
    require(timestamp(job['started_at']) <= timestamp(job['finished_at']), '来源任务时间范围颠倒')
    timestamp(artifact['created_at'])
    return value


def archive_path(output, name):
    require(isinstance(name, str) and bool(name) and not Path(name).is_absolute(), 'archive 必须位于 output 目录内')
    output = Path(output).resolve()
    path = output / name
    require(path.resolve().is_relative_to(output) and '..' not in Path(name).parts
            and not any(parent.is_symlink() for parent in (path, *path.parents) if parent != output.parent)
            and path.is_file(), 'archive 必须是 output 目录内的实际文件')
    return path


def validate(operation, value, arguments):
    if operation == 'task':
        obj(value, {'id', 'url', 'repository', 'state', 'owners', 'items', 'raw'})
        require(value['id'] == _argument(arguments, '--id'), 'Task was redirected; use its canonical URL (id 与请求身份不符)')
        task_url(value['id']); task_url(value['url'])
        repository(value['repository'])
        require(value['state'] in ('open', 'closed'), 'task.state 必须是 open 或 closed')
        strings(value['owners'])
        require(isinstance(value['items'], list) and value['items'], 'task.items 必须是非空数组')
        order, kinds = [], []
        for item in value['items']:
            obj(item, {'url', 'author', 'created_at', 'updated_at', 'body', 'kind'})
            task_url(item['url']); text(item['author'])
            created, updated = timestamp(item['created_at']), timestamp(item['updated_at'])
            require(updated >= created, 'updated_at 不能早于 created_at')
            require(isinstance(item['body'], str), 'item.body 必须是原文字符串')
            require(item['kind'] in ('task', 'comment', 'change', 'review'), '未知 item.kind')
            kinds.append(item['kind'])
            order.append((created, item['url']))
        require(kinds[0] == 'task' and kinds.count('task') == 1, 'items 首项必须是唯一的 task')
        require(value['items'][0]['url'] == value['url'], 'task 首项地址与 url 不同')
        require(order[1:] == sorted(order[1:]), 'items 必须按 created_at、url 排序')
    elif operation == 'commit':
        obj(value, {'exists', 'revision', 'author', 'time'})
        require(type(value['exists']) is bool, 'commit.exists 必须是布尔值')
        require(revision(value['revision']) == _argument(arguments, '--revision'), '平台返回了不同的提交号')
        text(value['author']); timestamp(value['time'])
    elif operation == 'reference':
        obj(value, {'reachable', 'kind'}, {'revision'})
        require(type(value['reachable']) is bool, 'reference.reachable 必须是布尔值')
        require(value['kind'] in ('commit', 'file', 'task', 'change', 'comment'), '未知 reference.kind')
        if 'revision' in value:
            revision(value['revision'])
    elif operation == 'ci-result':
        obj(value, {'provenance', 'archive'})
        provenance(value['provenance'])
        archive = archive_path(_argument(arguments, '--output'), value['archive'])
        require(archive.stat().st_size <= 64 * 1024 * 1024, 'Artifact archive exceeds 64 MiB')
        require('sha256:' + sha(archive) == value['provenance']['artifact']['digest'],
                'Downloaded archive differs from provider digest')
    return value


def _constant(value):
    raise ValueError('不是 JSON 数值：' + value)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('重复 JSON 字段')
        result[key] = value
    return result


def configuration(root):
    config = read(Path(root) / '.tw/config.json')
    require(isinstance(config, dict), '.tw/config.json 必须是对象')
    value = config.get('platform')
    require(value is not None, '缺少 platform 配置；请在初始化时生成平台脚本，并登记到 .tw/config.json 的 platform')
    problems = platform_problems(value)
    require(not problems, '；'.join(problems))
    return value


def call(root, operation, *arguments):
    root = Path(root).resolve()
    config = configuration(root)
    require(operation in config['operations'],
            f'需要平台操作 {operation}；请在项目平台脚本实现，并在 .tw/config.json 的 platform.operations 中声明')
    key = (str(root), digest(config), operation, tuple(arguments))
    if key not in _CACHE:
        try:
            _CACHE[key] = _execute(root, config, operation, arguments)
        except Invalid as exc:
            _CACHE[key] = exc
    if isinstance(_CACHE[key], Invalid):
        raise Invalid(str(_CACHE[key]))
    return copy.deepcopy(_CACHE[key])


def _execute(root, config, operation, arguments):
    try:
        result = subprocess.run(config['argv'] + [operation, *arguments], cwd=root,
                                capture_output=True, timeout=config.get('timeout', 60))
    except subprocess.TimeoutExpired as exc:
        raise Invalid(f'平台操作 {operation} 超时') from exc
    except OSError as exc:
        raise Invalid(f'无法启动平台操作 {operation}：{exc.strerror}') from exc
    if result.returncode:
        lines = result.stderr.decode('utf-8', errors='replace').splitlines()
        raise Invalid(f'平台操作 {operation} 失败：' + (lines[0] if lines else str(result.returncode)))
    try:
        value = json.loads(result.stdout, parse_constant=_constant, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as exc:
        raise Invalid(f'平台操作 {operation} 标准输出必须恰好是一个 JSON 对象') from exc
    require(isinstance(value, dict), f'平台操作 {operation} 标准输出必须恰好是一个 JSON 对象')
    return validate(operation, value, arguments)


def task(root, identity):
    value = call(root, 'task', '--id', task_url(identity))
    from artifacts import directory
    target = directory(project_root(root), identity).parent.parent / 'platform' / (
        'task-' + digest(['--id', identity]) + '-' + digest(value['raw'])[:16] + '.json')
    try:
        create(target, value['raw'])
    except FileExistsError:
        require(read(target) == value['raw'], '平台原始响应存档冲突')
    return value


def commit(root, repository_id, commit_id):
    value = call(root, 'commit', '--repo', repository(repository_id), '--revision', revision(commit_id))
    require(value['exists'], '平台找不到提交：' + commit_id)
    return value


def reference(root, url):
    value = call(root, 'reference', '--url', task_url(url))
    require(value['reachable'], '平台无法读取引用：' + url)
    return value


def ci_result(root, locator, output):
    output = Path(output).resolve()
    arguments = ('--locator', json.dumps(locator, ensure_ascii=False, separators=(',', ':'), allow_nan=False), '--output', str(output))
    key = (str(project_root(root)), digest(configuration(root)), 'ci-result', arguments)
    if key not in _CACHE:
        require(output.is_dir() and not any(output.iterdir()), 'ci-result 的 output 必须是工具提供的空目录')
    return call(root, 'ci-result', *arguments)


def check(root, identity, commit_id=None, reference_url=None, locator=None):
    from tw_runtime import gitutil
    declared = configuration(root)['operations']
    rows = []
    for operation in ('task', 'commit', 'reference', 'ci-result'):
        if operation not in declared:
            continue
        started = time.monotonic()
        row = {'operation': operation, 'ok': False}
        try:
            if operation == 'task':
                task(root, identity)
            elif operation == 'commit':
                known = gitutil.output(root, 'show', '-s', '--format=%H%n%an <%ae>%n%aI', commit_id or 'HEAD').splitlines()
                require(len(known) == 3, '无法读取本地已知提交')
                repo = gitutil.remote_identity(root)
                require(repo and not repo.startswith('local:'), 'commit 核对需要项目的 git 远端')
                value = commit(root, repo, known[0])
                require(value['author'] == known[1] and timestamp(value['time']) == timestamp(known[2]),
                        '平台提交的作者或时间与本地 git 不符')
            elif operation == 'reference':
                reference(root, reference_url or identity)
            else:
                require(locator is not None, 'ci-result 核对需要 --locator <JSON>，工具不会猜测平台定位信息')
                from portable import provider
                provider(root, json.loads(locator, parse_constant=_constant, object_pairs_hook=_object))
            row['ok'] = True
        except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
            row['problem'] = str(exc)
        row['seconds'] = round(time.monotonic() - started, 3)
        rows.append(row)
    return {'ok': all(row['ok'] for row in rows), 'scope': 'platform-check', 'checks': rows,
            'summary': '平台脚本一致性检查；仅报告结果和耗时'}
