"""Read Markdown inputs, or tool-owned JSON snapshots selected through local references."""
import json
import os
import subprocess
from pathlib import Path

from common import Invalid, require
import designs
from error_codes import Code, fields
from scenario_files import FileProblems


def path_label(path):
    from tw_runtime.team import platform_script
    path = Path(path).resolve()
    root = platform_script.project_root()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


class DesignReadError(Invalid):
    error_code = Code.DESIGN_INPUT

    def __init__(self, path, reason, **location):
        name = path_label(path)
        super().__init__(name + ' ' + reason, **location)
        self.next_action = '修正方案文件 ' + name + ' 中指出的行，再重试原命令。'


def declares(path, design):
    """A Markdown file whose header names this design and its task is that design's own source."""
    try:
        lines = Path(path).read_text(encoding='utf-8').split('\n')
    except (OSError, UnicodeError):
        return False
    if lines[0].rstrip('\r') != '---':
        return False
    head = {}
    for line in lines[1:]:
        line = line.rstrip('\r')
        if line == '---':
            break
        key, sep, value = line.partition(':')
        if sep and key in ('design', 'task'):
            try:
                head[key] = json.loads(value)
            except ValueError:
                return False
    else:
        return False  # An unterminated header is not a design file.
    return head.get('design') == design['id'] and head.get('task') == design['task_id']


def scenario_reader(root, commit=None):
    """本地方案读取工作区；提交方案读取该提交中的场景与配置。"""
    import hashlib
    import scenario_files
    root = Path(root)
    def payload(name):
        designs._path(name)
        if commit is None:
            from common import inside
            return inside(root, name).read_bytes()
        result = _git(root, 'show', commit + ':' + name)
        require(result.returncode == 0, '提交中的文件可读取：' + commit + ':' + name)
        return result.stdout
    def read_scenario(name):
        try:
            config = json.loads(payload('.tw/config.json').decode('utf-8'))
            from common import acceptance_entries
            acceptance_entries(config.get('acceptance_entries', {}), config.get('accounts', []))
            raw = payload(name)
            value = scenario_files.load(raw.decode('utf-8'), Path(name).suffix, config)
            return value, hashlib.sha256(raw).hexdigest()
        except (OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, Invalid):
                raise
            raise Invalid('读取场景文件 ' + name + '：' + str(exc)) from exc
    return read_scenario


def read(path, *, internal=True, workspace=None, checkout=None):
    path = Path(path)
    if workspace is not None:
        return workspace.design(path, internal=internal)
    try:
        raw = path.read_bytes().decode('utf-8')
    except (OSError, UnicodeError) as exc:
        raise Invalid(f'无法读取方案：{path}: {exc}') from exc
    try:
        if raw.lstrip().startswith(('{', '[')):
            # dispatch validates every explicit --design/--record/--design-history before selecting artifacts.
            local = any(parent.name == 'local' and parent.parent.name == '.tw' for parent in path.resolve().parents)
            require(internal and local, '第 1 行：JSON 方案已停用，请改写为 Markdown，格式见 references/designs.md')
            try:
                design = designs.validate_design(json.loads(raw))
                context_path = path.parent / 'context.json'
                if context_path.is_file():
                    context = json.loads(context_path.read_text(encoding='utf-8'))
                    from tw_runtime import gitutil
                    root = checkout or gitutil.toplevel(path.resolve().parent)
                    if root and context.get('design', {}).get('path') == path.resolve().relative_to(root).as_posix():
                        origin = context.get('design_source')
                        reader = (scenario_reader(_checkout(root, origin['repository']), origin['commit']) if origin
                                  else scenario_reader(root))
                        from scenario_files import reference
                        for section in design['sections']:
                            if section['type'] == 'acceptance':
                                section['data']['scenarios'] = [reference(ref['path'], ref['nodes'], reader)
                                                               for ref in section['data']['scenarios']]
                return design
            except ValueError as exc:
                if isinstance(exc, Invalid):
                    raise
                raise Invalid(f'无法读取内部方案快照：{exc}') from exc
        from tw_runtime import gitutil
        checkout = gitutil.toplevel(path.resolve().parent) or path.resolve().parent
        return designs.load(raw, scenario_reader=scenario_reader(checkout))
    except Invalid as exc:
        if isinstance(exc, FileProblems):
            raise
        error = DesignReadError(path, str(exc), **{key: value for key, value in fields(exc).items() if key != 'error_code'})
        if internal and raw.lstrip().startswith(('{', '[')) and path.suffix == '.json':
            error.error_code = Code.DESIGN_SNAPSHOT
            error.next_action = '用当前格式的方案重新开工：tw team start --task <身份> --design <当前格式方案.md>'
        raise error from exc


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
        design = designs.load(raw, scenario_reader=scenario_reader(checkout, commit))
    except Invalid as exc:
        error = Invalid(f'{reference["path"]} 第 {reference["revision"]} 版 ' + str(exc)
                        + '；已发布方案不可读，请用 design-draft --reconcile "<原因>" 发布对账记录，从第 1 版重新开始并重新批准')
        error.next_action = '修正方案文件 ' + path_label(checkout / reference['path']) + '，再按错误中的对账提示重新发布。'
        raise error from exc
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
    raw = result.stdout.decode('utf-8')
    committed = designs.load(raw, scenario_reader=scenario_reader(checkout, revision))
    require(committed == design, '发布方案及其场景与源提交内容一致后继续；请先提交场景文件，再重新生成草稿')
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
    import design_links
    from tw_runtime.team import platform_script
    try:
        config = json.loads((Path(root) / '.tw/config.json').read_text())
    except FileNotFoundError:
        config = {}
    file_url = None
    if 'file-url' in config.get('platform', {}).get('operations', []):
        file_url = lambda path: platform_script.file_url(root, reference['repository'], reference['commit'], path)
    body = design_links.rewrite(body, reference, file_url)
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
