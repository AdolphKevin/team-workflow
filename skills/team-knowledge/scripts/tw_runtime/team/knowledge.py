"""Read project knowledge through the shared runtime; delivery records its actual disposition."""
from pathlib import Path

from common import (RECORD_SCHEMA, LOCATIONS, digest, inside, knowledge_path, now, obj,
                    require, sha, strings, text)
from tw_runtime import Invalid as RuntimeInvalid, brief as knowledge_brief, check, globs
from tw_runtime.brief import relative_paths
from tw_runtime.project import Project, document_source


def project(root):
    current = Project(root)
    current.overrides.update({key: str((root / Path(value).expanduser()).resolve())
                              for key, value in LOCATIONS.get()['repositories'].items()})
    return current


def query_paths(root, task, design, paths=()):
    """Use explicit hints, task hints, then the selected design task scopes."""
    sections = {row['id']: row for row in design['sections']}
    selected = paths or task.get('paths') or sorted({path for key in task['section_ids']
               if sections[key]['type'] == 'task' for path in sections[key]['data']['scope']})
    return relative_paths(root, selected)


def brief(root, task, paths=(), symbols=()):
    current = project(root)
    require(not current.config_errors, '；'.join(current.config_errors))
    paths = relative_paths(root, paths or task.get('paths', []))
    symbols = list(symbols or task.get('symbols', []))
    result = knowledge_brief.build(current, task['goal'], paths=paths, symbols=symbols)
    files = {name: sha(inside(root, name)) for name in current.source.names if knowledge_path(name)}
    return {'data_version': RECORD_SCHEMA, 'kind': 'knowledge-brief', 'task_id': task['id'],
            'at': now(), 'task_digest': digest(task), 'paths': paths, 'symbols': symbols,
            'markdown': result['markdown'], 'entries': result['entries'], 'files': files,
            'knowledge_digest': digest(files), 'brief': result}


def template(root, task):
    files = sorted(changed_since(root, task['base']))
    return {'files': files, 'reason': '' if files else '__REPLACE__'}


MISSING = ('交付报告需要写明知识处置 knowledge，二选一：在 files 列出本任务改动的 .tw 知识文件，'
           '或在 reason 写明不需要更新知识的理由')


def disposition(value):
    require(isinstance(value, dict), MISSING)
    obj(value, {'files'}, {'reason'})
    strings(value['files'])
    require(all(knowledge_path(name) for name in value['files']),
            'knowledge.files 只能列出 .tw/ 的知识正文路径')
    reason = value.get('reason')
    if not value['files']:
        require(isinstance(reason, str) and reason.strip() and '__REPLACE__' not in reason, MISSING)
    elif reason:
        text(reason)
    return value


def state(root):
    """Current knowledge files and their content, for request identity."""
    return {name: sha(inside(root, name)) for name in project(root).source.names if knowledge_path(name)}


def changed_since(root, base):
    """Knowledge files changed in this task: differences from the task base plus untracked files."""
    from common import git
    names = set()
    for args in (('diff', '--name-only', '--no-renames', '-z', base),
                 ('ls-files', '--others', '--exclude-standard', '-z')):
        names.update(n.decode() for n in git(root, *args).split(b'\0') if n)
    return {n for n in names if knowledge_path(n)}


def verify(root, value, base=None):
    """files lists exactly the knowledge this task changed since its base (existing or deleted)."""
    disposition(value)
    require(bool(base), '任务缺少 base，无法核对本任务改动的知识文件')
    changed = changed_since(root, base)
    for name in value['files']:
        if inside(root, name, exists=False).is_file():
            continue
        from common import git
        try:
            git(root, 'cat-file', '-e', f'{base}:{name}')
            deleted = True
        except Exception:
            deleted = False
        require(deleted, '知识文件不存在，也不是本任务删除的条目：' + name)
    unchanged = sorted(set(value['files']) - changed)
    require(not unchanged, '列出的知识文件在本任务中没有改动：' + '、'.join(unchanged))
    omitted = sorted(changed - set(value['files']))
    require(not omitted, '本任务改动的知识文件没有列入 knowledge.files：' + '、'.join(omitted)
            + '；重新运行 delivery-template，或把它们加入 files')
    result = check.run(project(root))
    require(not result['errors'], 'tw check 有错误：' + '；'.join(
        f'{row["path"]}：{row["message"]}' for row in result['errors']))
    return {'files': list(value['files']), **({'reason': value['reason']} if value.get('reason') else {})}


def documents(root):
    """Originals are declared in config; hash local originals without calling an external CLI."""
    current = project(root)
    rows = []
    for doc in current.config.get('documents', []):
        alias, pattern = document_source(doc['source'])
        item = dict(doc, status='unavailable')
        if alias != 'url':
            from tw_runtime.read import repo_root
            try:
                target, names = repo_root(current, alias)
                matched = sorted(n for n in names if globs.matches(pattern, n))
                if len(matched) == 1:
                    item.update(sha256=sha(target / matched[0]), status='current')
                elif matched:
                    item.update(sha256=digest({n: sha(target / n) for n in matched}), status='current')
            except (RuntimeInvalid, ValueError, OSError):
                pass
        rows.append(item)
    return {'documents': rows}
