"""Read Markdown inputs, or tool-owned JSON snapshots selected through local references."""
import json
import os
import subprocess
from pathlib import Path

from common import Invalid, require
import designs


def read(path, *, internal=True):
    path = Path(path)
    try:
        raw = path.read_bytes().decode('utf-8')
    except (OSError, UnicodeError) as exc:
        raise Invalid(f'无法读取方案：{path}: {exc}') from exc
    if raw.lstrip().startswith(('{', '[')):
        # dispatch validates every explicit --design/--record/--design-history before selecting artifacts.
        local = any(parent.name == 'local' and parent.parent.name == '.tw' for parent in path.resolve().parents)
        require(internal and local, '第 1 行：JSON 方案已停用，请改写为 Markdown，格式见 references/designs.md')
        try:
            return designs.validate_design(json.loads(raw))
        except ValueError as exc:
            raise Invalid(f'无法读取内部方案快照：{path}: {exc}') from exc
    return designs.load(raw)


def _checkout(root, repository):
    from common import external_path, location_settings
    from portable import repository_id
    from tw_runtime.project import Project
    root = Path(root).resolve()
    from tw_runtime import gitutil
    if gitutil.remote_identity(root) == repository:
        return root
    mappings = location_settings(root)['repositories']
    if repository not in mappings:
        # Knowledge shared aliases resolve to the same checked repository identity.
        project = Project(root, require_config=False)
        for alias, entry in (project.config or {}).get('shared', {}).items():
            if entry.get('id') == repository and alias in mappings:
                path = (root / Path(mappings[alias]).expanduser()).resolve()
                require(repository_id(path) == repository, 'Local checkout identity differs from ' + repository)
                return path
    return external_path(root, repository, {'kind': 'repository', 'repository': repository})


def _git(root, *arguments):
    return subprocess.run(['git', '-C', str(root), *arguments], capture_output=True,
                          env={**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'})


def source(root, reference):
    """Resolve and verify the immutable original exclusively through local git."""
    import hashlib
    import re
    from common import obj
    from tw_runtime import gitutil
    from tw_runtime.team import platform_script
    obj(reference, {'id', 'revision', 'repository', 'path', 'commit', 'sha256'})
    platform_script.repository(reference['repository'])
    require(isinstance(reference['commit'], str) and re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', reference['commit']),
            '方案记录需要完整提交号')
    require(isinstance(reference['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', reference['sha256']), 'Invalid design sha256')
    require(type(reference['revision']) is int and reference['revision'] > 0, 'Invalid design reference revision')
    designs._path(reference['path'])
    checkout = _checkout(root, reference['repository'])
    commit = reference['commit']
    require(_git(checkout, 'cat-file', '-e', commit + '^{commit}').returncode == 0,
            '本地缺少方案提交 ' + commit + '；请先 fetch，再重新读取（工具不访问平台）')
    # Bytes matter to sha256: subprocess text mode would normalize CRLF.
    result = _git(checkout, 'show', commit + ':' + reference['path'])
    require(result.returncode == 0, '方案文件不在提交中：' + commit + ':' + reference['path'])
    require(hashlib.sha256(result.stdout).hexdigest() == reference['sha256'], '方案原文 sha256 不符：' + reference['path'])
    try:
        raw = result.stdout.decode('utf-8')
    except UnicodeError as exc:
        raise Invalid('方案原文必须是 UTF-8 Markdown') from exc
    try:
        design = designs.load(raw)
    except Invalid as exc:
        raise Invalid(str(exc) + '；已发布方案不可读，请用 design-draft --reconcile "<原因>" 发布对账记录，从第 1 版重新开始并重新批准') from exc
    require(design['id'] == reference['id'] and design['revision'] == reference['revision'], '方案引用身份或版本与原文不同')
    return design, raw


def publication(root, path, design):
    """Bind a clean committed source file to a platform record and its exact display."""
    import hashlib
    from portable import repository_id
    from tw_runtime import gitutil
    root = Path(root).resolve()
    require(path is not None, '发布方案需要 Markdown 文件路径，请先提交方案文件')
    path = Path(path)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    require(path.is_relative_to(root), '方案文件必须在发布仓库中')
    checkout = gitutil.toplevel(path.parent) or root
    if checkout != root:
        require(_checkout(root, repository_id(checkout)) == checkout, 'Shared design checkout mapping differs')
    name = path.relative_to(checkout).as_posix()
    require(path.is_file(), '请先提交方案文件：' + name)
    revision = gitutil.head(checkout)
    require(revision is not None, '请先提交方案文件')
    result = _git(checkout, 'show', revision + ':' + name)
    require(result.returncode == 0 and result.stdout == path.read_bytes()
            and not gitutil.output(checkout, 'status', '--porcelain=v1', '-z', '--', name),
            '方案文件尚未提交或工作区中已修改，请先提交：' + name)
    require(read(path, internal=False) == design, '发布文件与所选方案不同')
    raw = result.stdout.decode('utf-8')
    reference = {'id': design['id'], 'revision': design['revision'], 'repository': repository_id(checkout),
                 'path': name, 'commit': revision, 'sha256': hashlib.sha256(result.stdout).hexdigest()}
    return reference, display(raw, design, reference, root=root)


COMPLEXITY = {'simple': '简单', 'medium': '中等', 'complex': '复杂'}


def check_table(design, checks):
    """Only declarations for referenced checks belong in the readable design display."""
    from design_markdown import table
    names = dict.fromkeys(key for row in design['sections'] if row['type'] == 'acceptance'
                          for key in row['data']['checks'])
    rows = []
    for key in names:
        if key not in checks:
            continue
        coverage = checks[key].get('coverage', {})
        rows.append([key, coverage.get('level', '未声明'), '、'.join(coverage.get('entrypoints', [])) or '未声明',
                     coverage.get('environment', '未声明'), '、'.join(coverage.get('substitutes', [])) or '无',
                     coverage.get('isolation', '未声明')])
    return ('## 本方案引用的检查\n\n' + table(('检查', '层级', '入口', '环境', '替身', '隔离'), rows) + '\n') if rows else ''


def display(raw, design, reference, *, root):
    """The pull request shows the original body; front matter data becomes readable lines, never JSON."""
    body = raw.split('\n---\n', 1)[1].lstrip('\n') if raw.startswith('---\n') else raw
    assessment, roles = design['assessment'], design['roles']
    joined = lambda values: '、'.join(values) or '无'
    header = [
        f"> 方案 {design['id']} · 第 {design['revision']} 版 · 原文 `{reference['path']}`（提交 {reference['commit'][:7]}）",
        f"> 复杂度：{COMPLEXITY.get(assessment['complexity'], assessment['complexity'])} · 风险：{joined(assessment['risks'])}"
        f" · 工作量：{assessment['effort']}",
        f"> 评估依据：{joined(assessment['drivers'])}",
        f"> 方案负责人：{roles['design_owner']} · 实施负责人：{roles['implementation_owner'] or '待定'}"
        f" · 验收负责人：{roles['acceptance_owner']}",
    ]
    result = _git(_checkout(root, reference['repository']), 'show', reference['commit'] + ':.tw/config.json')
    appendix = ''
    if result.returncode == 0:
        try:
            checks = json.loads(result.stdout).get('checks', {})
            appendix = check_table(design, checks)
        except (ValueError, AttributeError, TypeError):
            pass  # An absent or unreadable declaration supplies no display metadata.
    return '\n'.join(header) + '\n\n' + body + ('\n' + appendix if appendix else '')
