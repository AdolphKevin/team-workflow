"""Project configuration, file sources and shared repositories."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re

from . import DATA_VERSION, FORMAT, KB, Invalid, entries, gitutil, globs

CONFIG = f'{KB}/config.json'
MAPPING = f'{KB}/local/repositories.json'
TEAM_KEYS = ('checks', 'required_checks', 'risk_checks', 'inputs', 'external_inputs', 'environment_versions', 'accounts')
KEYS = ('format', 'data_version', 'project', 'context', 'shared', 'documents', 'platform') + TEAM_KEYS
DOC_ID = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
LEGACY = ('.codestable', '.team-workflow.json', '.team-workflow')


def user_mapping_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or '~/.config').expanduser() / 'tw/repositories.json'


def location_settings(root, project_id=None, overrides=None):
    """Read user defaults and checkout overrides; keys retain their caller's meaning."""
    root = Path(root)

    def read_json(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError, UnicodeError) as exc:
            raise Invalid(f'{path} 无法解析：{exc}') from exc

    def merge(result, settings, path):
        if not isinstance(settings, dict) or settings.keys() - {'repositories', 'inputs'}:
            raise Invalid(f'{path} 只允许 repositories、inputs 对象')
        for kind in result:
            values = settings.get(kind, {})
            if not isinstance(values, dict):
                raise Invalid(f'{path} 的 {kind} 必须是对象')
            for name, value in values.items():
                if not all(isinstance(v, str) and v.strip() and '__REPLACE__' not in v for v in (name, value)):
                    raise Invalid(f'{path} 的 {kind} 名称和路径必须是非空文本')
            result[kind].update(values)

    if project_id is None and (root / CONFIG).is_file():
        config = read_json(root / CONFIG)
        project = config.get('project', {}) if isinstance(config, dict) else {}
        project_id = project.get('id') if isinstance(project, dict) else None
    result = {'repositories': {}, 'inputs': {}}
    user_path = user_mapping_path()
    if user_path.exists():
        data = read_json(user_path)
        if not isinstance(data, dict) or set(data) != {'projects'} or not isinstance(data['projects'], dict):
            raise Invalid(f'{user_path} 必须是包含 projects 对象的用户级映射')
        for name, settings in data['projects'].items():
            if not isinstance(name, str) or not name.strip():
                raise Invalid(f'{user_path} 的项目身份必须是非空文本')
            defaults = {'repositories': {}, 'inputs': {}}
            merge(defaults, settings, user_path)
            if name == project_id:
                result = defaults
    path = root / MAPPING
    if path.exists():
        merge(result, read_json(path), path)
    if overrides:
        merge(result, overrides, '--repository / --input')
    return result


def config_problems(config):
    if not isinstance(config, dict):
        return ['config.json 必须是 JSON 对象']
    problems = [f'config.json 不使用字段：{key}' for key in config if key not in KEYS]
    if config.get('format') != FORMAT:
        problems.append(f'config.json 的 format 必须是 "{FORMAT}"')
    if type(config.get('data_version')) is not int or config.get('data_version') != DATA_VERSION:
        problems.append(f'config.json 的 data_version 必须是 {DATA_VERSION}')
    project = config.get('project')
    if not (isinstance(project, dict) and set(project) == {'id', 'name'} and all(isinstance(v, str) and v.strip() for v in project.values())):
        problems.append('project 必须是 {"id": 规范化远端或 local:名称, "name": 名称}')
    context = config.get('context', [])
    if not (isinstance(context, list) and all(isinstance(x, str) and not globs.problem(x) for x in context)):
        problems.append('context 必须是仓库内相对路径数组')
    shared = config.get('shared', {})
    if not isinstance(shared, dict) or any(alias == 'self' or not globs.ALIAS.match(alias) or not (
            isinstance(value, dict) and set(value) == {'id'} and isinstance(value['id'], str) and value['id'].strip())
            for alias, value in (shared.items() if isinstance(shared, dict) else [])):
        problems.append('shared 必须是 {"别名": {"id": 规范化远端}}，别名不能是 self')
    documents = config.get('documents', [])
    if not isinstance(documents, list):
        problems.append('documents 必须是数组')
    else:
        seen = set()
        for index, doc in enumerate(documents, 1):
            if not (isinstance(doc, dict) and {'id', 'title', 'source'} <= set(doc) <= {'id', 'title', 'source', 'scope', 'section'}):
                problems.append(f'documents 第 {index} 项应包含 id、title、source，可选 scope、section')
                continue
            if not (isinstance(doc['id'], str) and DOC_ID.match(doc['id'])):
                problems.append(f'documents 第 {index} 项的 id 只能用小写字母、数字、点、连字符和下划线')
            elif doc['id'] in seen:
                problems.append(f'documents 的 id 重复：{doc["id"]}')
            seen.add(doc['id'])
            if not (isinstance(doc['title'], str) and doc['title'].strip()):
                problems.append(f'documents {doc["id"]} 缺少 title')
            if not document_source(doc.get('source')):
                problems.append(f'documents {doc["id"]} 的 source 应为 `self:路径`、`别名:路径` 或 http(s) 链接')
            scope = doc.get('scope', [])
            if not (isinstance(scope, list) and all(not globs.split(x)[2] for x in scope)):
                problems.append(f'documents {doc["id"]} 的 scope 应为 `仓库:路径` 数组')
    for key in TEAM_KEYS:
        if key in config and not isinstance(config[key], (dict, list)):
            problems.append(f'{key} 的类型不正确')
    if 'platform' in config:
        problems.extend(platform_problems(config['platform']))
    return problems


def platform_problems(value):
    if not isinstance(value, dict):
        return ['platform 必须是对象']
    problems = []
    if not {'argv', 'operations'} <= value.keys() <= {'argv', 'timeout', 'operations'}:
        problems.append('platform 应包含 argv、operations，可选 timeout')
    argv = value.get('argv')
    if not (isinstance(argv, list) and argv and all(isinstance(v, str) and v.strip() for v in argv)):
        problems.append('platform.argv 必须是非空字符串数组')
    timeout = value.get('timeout', 60)
    if type(timeout) is not int or timeout <= 0:
        problems.append('platform.timeout 必须是正整数')
    operations = value.get('operations')
    if not (isinstance(operations, list) and all(isinstance(v, str) for v in operations)
            and 'task' in operations and set(operations) <= {'task', 'commit', 'reference', 'ci-result', 'file-url'}
            and len(set(operations)) == len(operations)):
        problems.append('platform.operations 只能声明 task、commit、reference、ci-result、file-url，且必须包含 task，不得重复')
    return problems


def document_source(value):
    """('url', url) or (repo, pattern) for a valid documents source, else None."""
    if not isinstance(value, str):
        return None
    if value.startswith(('https://', 'http://')):
        return ('url', value)
    repo, pattern, issue = globs.split(value)
    return None if issue else (repo, pattern)


class Source:
    """Files of one repository, read from the working tree or from the index (`--cached`)."""

    def __init__(self, root, cached=False):
        self.root, self.cached = Path(root), cached
        self.names = gitutil.index_files(root) if cached else gitutil.files(root)

    def read(self, name):
        if self.cached:
            return gitutil.show_index(self.root, name)
        return (self.root / name).read_text(encoding='utf-8')

    def exists(self, name):
        return name in self.names


@dataclass
class Repo:
    alias: str
    root: Path = None
    expected: str = None
    status: str = 'ok'
    actual: str = None
    head: str = None
    dirty: bool = False
    config: dict = None
    entries: list = field(default_factory=list)
    names: list = field(default_factory=list)

    def describe(self):
        if self.status == 'unmapped':
            return (f'未配置本机路径（在 {MAPPING} 或用户级 {user_mapping_path()} 中登记，'
                    f'或使用 --repository {self.alias}=<路径>）')
        if self.status == 'missing':
            return f'本机路径不是 git 仓库：{self.root}'
        if self.status == 'mismatch':
            return f'检出身份不符：期望 {self.expected}，实际 {self.actual}（{self.root}）'
        state = '有未提交修改' if self.dirty else '无未提交修改'
        head = (self.head or '无提交')[:7]
        if self.status == 'not-migrated':
            return f'{self.root} @ {head}，尚未迁移到 {KB}/'
        return f'{self.root} @ {head}，{state}'


def load_entries(source, repo='self', config=None):
    found, strays = entries.classify(source.names)
    platform = (config or {}).get('platform', {})
    argv = platform.get('argv', []) if isinstance(platform, dict) else []
    scripts = {Path(value).as_posix() for value in argv if isinstance(value, str)
               and value.endswith('.py') and not Path(value).is_absolute() and '..' not in Path(value).parts}
    strays = [name for name in strays if name not in scripts]
    loaded = []
    for kind, ref in found:
        try:
            text = source.read(f'{KB}/{ref}')
        except (OSError, UnicodeDecodeError, Invalid) as exc:
            entry = entries.Entry(kind, ref, repo, errors=[f'无法读取：{exc}'])
        else:
            entry = entries.load(kind, ref, text, repo)
        loaded.append(entry)
    return loaded, strays


class Project:
    def __init__(self, root, repositories=(), cached=False, require_config=True):
        found = gitutil.toplevel(root)
        if found is None:
            raise Invalid(f'{root} 不在 git 仓库中')
        self.root = found
        self.source = Source(self.root, cached)
        self.config, self.config_errors = None, []
        path = self.root / CONFIG
        if path.is_file() or (cached and self.source.exists(CONFIG)):
            try:
                self.config = json.loads(self.source.read(CONFIG))
            except (ValueError, OSError, Invalid) as exc:
                self.config_errors = [f'config.json 无法解析：{exc}']
            else:
                self.config_errors = config_problems(self.config)
        elif require_config:
            legacy = legacy_paths(self.root)
            hint = (f'；项目里还有 {"、".join(legacy)}，按 team-knowledge 的 references/migration.md 迁移' if legacy else '')
            raise Invalid(f'{self.root} 尚未初始化 {KB}/，先运行 `tw init --apply`{hint}')
        self.overrides = dict(parse_mapping(repositories))
        self._entries = None
        self._shared = None

    @property
    def id(self):
        project = (self.config or {}).get('project')
        return project.get('id') if isinstance(project, dict) else None

    def entries(self):
        if self._entries is None:
            self._entries, self.strays = load_entries(self.source, config=self.config)
        return self._entries

    def mapping(self):
        overrides = {alias: str(Path(value).expanduser().resolve()) for alias, value in self.overrides.items()}
        settings = location_settings(self.root, self.id, {'repositories': overrides})
        return {alias: (self.root / Path(value).expanduser()).resolve()
                for alias, value in settings['repositories'].items()}

    def shared(self):
        """Resolve each configured shared repository once; entries are read from its working tree."""
        if self._shared is None:
            self._shared = {}
            declared = (self.config or {}).get('shared', {}) if isinstance((self.config or {}).get('shared'), dict) else {}
            mapping = self.mapping()
            for alias, value in declared.items():
                expected = value.get('id') if isinstance(value, dict) else None
                self._shared[alias] = resolve(alias, mapping.get(alias) or mapping.get(expected)
                                              or mapping.get((expected or '').partition('/')[2]), expected)
        return self._shared


def resolve(alias, path, expected):
    repo = Repo(alias, path, expected)
    if path is None:
        repo.status = 'unmapped'
        return repo
    root = gitutil.toplevel(path) if Path(path).is_dir() else None
    if root is None:
        repo.status = 'missing'
        return repo
    repo.root, repo.actual, repo.head = root, gitutil.remote_identity(root), gitutil.head(root)
    if expected and repo.actual != expected:
        repo.status = 'mismatch'
        return repo
    repo.dirty = bool(gitutil.dirty_paths(root))
    source = Source(root)
    repo.names = source.names
    if not (root / CONFIG).is_file():
        repo.status = 'not-migrated'
        return repo
    try:
        repo.config = json.loads((root / CONFIG).read_text(encoding='utf-8'))
    except ValueError:
        repo.config = {}
    repo.entries, _ = load_entries(source, alias, repo.config)
    return repo


def parse_mapping(values):
    for value in values or ():
        alias, sep, path = value.partition('=')
        if not sep or not globs.ALIAS.match(alias) or not path:
            raise Invalid(f'--repository 应写成 别名=路径：{value}')
        yield alias, path


def legacy_paths(root):
    return [name for name in LEGACY if (Path(root) / name).exists()]
