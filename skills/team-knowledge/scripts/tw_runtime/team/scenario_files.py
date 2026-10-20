"""场景文件的格式、内容指纹与节点引用。"""
import hashlib
from pathlib import Path
import re

from common import Invalid, digest
from error_codes import Code
import scenario_yaml

NEGATIVE_TYPES = frozenset(('empty-input', 'over-length', 'not-found', 'permission', 'cross-tenant',
    'duplicate', 'concurrency', 'disconnect', 'timeout', 'archived', 'invalid-input', 'incomplete-input',
    'interrupted', 'stale-input', 'tampered-input', 'other'))
NONEMPTY_CONTENT_FIELDS = ('initial_state', 'steps', 'expected')
CONTENT_FIELDS = NONEMPTY_CONTENT_FIELDS + ('forbidden_effects',)


class FileProblems(Invalid):
    def __init__(self, errors, code=Code.SCENARIO_FILE):
        self.errors = errors
        super().__init__('；'.join((f'第 {row["line"]} 行：' if row.get('line') else '') + row['problem'] for row in errors),
                         error_code=code, line=errors[0].get('line'))

    def result(self):
        return {'ok': False, 'error_code': self.error_code, 'problem': str(self), 'errors': self.errors}


def fingerprint(scenario):
    """正文字段规范化换行后计算 sha256，供各轮执行共同使用。"""
    def normalized(value):
        if isinstance(value, str):
            return value.replace('\r\n', '\n').replace('\r', '\n')
        if isinstance(value, list):
            return [normalized(item) for item in value]
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in value.items()}
        return value
    return digest({key: normalized(scenario[key]) for key in CONTENT_FIELDS})


class Validation:
    def __init__(self, document):
        self.document, self.errors = document, []

    def add(self, path, message):
        self.errors.append({'line': self.document.line(path), 'problem': message})

    def shape(self, value, path, required, optional=()):
        if not isinstance(value, dict):
            self.add(path, '应为对象')
            return False
        for key in sorted(set(required) - value.keys()):
            self.add(path, '缺少字段：' + key)
        for key in sorted(value.keys() - set(required) - set(optional)):
            self.add(path + (key,), '格式外字段：' + key)
        return True

    def text(self, value, path):
        if not isinstance(value, str) or not value.strip():
            self.add(path, '.'.join(map(str, path)) + ' 应为非空字符串')
            return False
        return True

    def array(self, value, path, nonempty=False):
        if not isinstance(value, list) or nonempty and not value:
            self.add(path, '.'.join(map(str, path)) + ' 应为' + ('非空' if nonempty else '') + '数组')
            return []
        return value

    def texts(self, value, path, nonempty=False):
        for index, item in enumerate(self.array(value, path, nonempty)):
            self.text(item, path + (index,))


def validate(document, profile):
    v, value = Validation(document), document.value
    if not v.shape(value, (), {'metadata', 'sops'}):
        raise FileProblems(v.errors)
    meta = value.get('metadata')
    if v.shape(meta, ('metadata',), {'requirement', 'batch', 'version', 'owner', 'sources'}, {'tags'}):
        for key in ('requirement', 'batch', 'owner'):
            v.text(meta.get(key), ('metadata', key))
        if not (type(meta.get('version')) is int or isinstance(meta.get('version'), str) and meta['version'].strip()):
            v.add(('metadata', 'version'), 'version 填版本文字或整数')
        for index, source in enumerate(v.array(meta.get('sources'), ('metadata', 'sources'), True)):
            path = ('metadata', 'sources', index)
            if v.shape(source, path, {'ref', 'version', 'confirmed_by'}):
                for key in ('ref', 'version', 'confirmed_by'):
                    v.text(source.get(key), path + (key,))
        if 'tags' in meta:
            v.texts(meta['tags'], ('metadata', 'tags'))
    seen, node_ids = set(), set()
    for index, node in enumerate(v.array(value.get('sops'), ('sops',))):
        path = ('sops', index)
        if not v.shape(node, path, {'id', 'title', 'actor', 'entry', 'scenarios'}, {'must', 'negative_exempt'}):
            continue
        for key in ('id', 'title', 'actor', 'entry'):
            v.text(node.get(key), path + (key,))
        identifier = node.get('id')
        if isinstance(identifier, str):
            if identifier in node_ids:
                v.add(path + ('id',), '重复节点编号：' + identifier)
            node_ids.add(identifier)
        if 'must' in node:
            v.texts(node['must'], path + ('must',))
        if 'negative_exempt' in node:
            v.text(node['negative_exempt'], path + ('negative_exempt',))
        polarities = set()
        for ordinal, row in enumerate(v.array(node.get('scenarios'), path + ('scenarios',))):
            p = path + ('scenarios', ordinal)
            required = {'id', 'polarity', 'title', 'actor', 'priority', 'verify', *CONTENT_FIELDS}
            if not v.shape(row, p, required, {'negative_type', 'refs', 'evidence_hints', 'tags', 'regression'}):
                continue
            for key in ('id', 'title', 'actor', 'priority', 'verify'):
                v.text(row.get(key), p + (key,))
            key = row.get('id')
            if isinstance(key, str):
                if key in seen:
                    v.add(p + ('id',), '重复场景编号：' + key)
                seen.add(key)
            polarity = row.get('polarity')
            if polarity not in ('positive', 'negative'):
                v.add(p + ('polarity',), 'polarity 取 positive 或 negative')
            else:
                polarities.add(polarity)
            if polarity == 'negative' or 'negative_type' in row:
                if not isinstance(row.get('negative_type'), str) or row['negative_type'] not in NEGATIVE_TYPES:
                    v.add(p + ('negative_type',), 'negative_type 填已定义的反向类型')
            if not isinstance(row.get('verify'), str) or row['verify'] not in profile.get('acceptance_entries', {}):
                v.add(p + ('verify',), '场景 ' + str(row.get('id')) + ' 的 verify 填写 acceptance_entries 中声明的入口名，当前为 ' + str(row.get('verify')))
            for key in CONTENT_FIELDS + ('refs', 'evidence_hints', 'tags'):
                if key in required or key in row:
                    v.texts(row.get(key), p + (key,), nonempty=key in NONEMPTY_CONTENT_FIELDS)
            if 'regression' in row:
                # 回归即重跑受影响的场景；{manual, owner, trigger} 记人工说明。
                # 旧文件中的 {check, cases}、{pending} 照常读取，不产生效果。
                r, rp = row['regression'], p + ('regression',)
                if not isinstance(r, dict) or set(r) not in ({'manual', 'owner', 'trigger'}, {'check', 'cases'}, {'pending'}):
                    v.add(rp, 'regression 写 {manual, owner, trigger}，或省略')
                elif 'manual' in r:
                    for key in r:
                        v.text(r[key], rp + (key,))
        if 'positive' not in polarities:
            v.add(path, '节点 ' + str(identifier) + ' 至少一条 positive 场景')
        if 'negative' not in polarities and not (isinstance(node.get('negative_exempt'), str) and node['negative_exempt'].strip()):
            v.add(path, '节点 ' + str(identifier) + ' 补充 negative 场景或 negative_exempt 理由')
    if v.errors:
        raise FileProblems(v.errors)
    return value


def load(raw, suffix, profile):
    try:
        document = scenario_yaml.loads(raw, suffix)
    except Invalid as exc:
        raise FileProblems([{'line': getattr(exc, 'line', 1), 'problem': str(exc)}]) from exc
    return validate(document, profile)


def read(path, profile):
    path = Path(path)
    try:
        payload = path.read_bytes()
        value = load(payload.decode('utf-8'), path.suffix, profile)
    except (OSError, UnicodeError) as exc:
        raise FileProblems([{'line': 1, 'problem': '读取场景文件 ' + str(path) + '：' + str(exc)}]) from exc
    return value, hashlib.sha256(payload).hexdigest()


def check(path, profile):
    try:
        value, sha256 = read(path, profile)
    except FileProblems as exc:
        return exc.result()
    node_counts = [{'node': node['id'], 'count': len(node['scenarios'])} for node in value['sops']]
    total = sum(row['count'] for row in node_counts)
    counts_text = '、'.join(f'{row["node"]} {row["count"]} 条' for row in node_counts)
    return {'ok': True, 'sha256': sha256, 'scenario_count': total, 'node_counts': node_counts,
            'fingerprints': {row['id']: fingerprint(row) for node in value['sops'] for row in node['scenarios']},
            'summary': f'场景文件已通过结构核对：共 {total} 条场景' + ('，' + counts_text if counts_text else '') + '。'}


def reference(path, nodes, reader):
    from common import require
    value, sha256 = reader(path)
    available = {node['id'] for node in value['sops']}
    require(set(nodes) <= available, '场景文件 ' + path + ' 缺少节点：' + '、'.join(sorted(set(nodes) - available)))
    return {'path': path, 'sha256': sha256, 'nodes': nodes}
