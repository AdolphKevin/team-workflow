"""Markdown syntax for the existing design value; no file or platform access."""
import html
import json
import re

from common import Invalid, obj, require, strings, text
from error_codes import Code

HEADER = {'design': 'id', 'task': 'task_id', 'revision': 'revision', 'assessment': 'assessment', 'roles': 'roles'}
RETIRED_LABELS = {'角色', '初始状态', '步骤', '预期', '反例'}
LABELS = {'需求级验收', '场景', '依据', '检查', '验证', '验收', '范围', '前置任务', '评估'}
IMPACT = ('仓库', '入口', '操作', '产生方', '使用方', '提交负责方', '验收')
IMPACT_KEYS = ('repository', 'entrypoint', 'operations', 'producer', 'consumer', 'commit_owner', 'acceptance')
ISSUES = ('编号', '问题', '负责人', '影响章节', '阻塞阶段', '状态', '原因', '证据', '确认人', '确认依据', '后续任务', '范围调整')
RESOLUTION = ('reason', 'evidence', 'confirmed_by', 'confirmation', 'follow_up', 'scope_change')
LABEL = re.compile(r'^- ([^：]+)：(.*)$')
HEADING = re.compile(r'^(#{1,6}) (.+)$')
MARKER = re.compile(r'<!-- tw-section id=([^\s]+) type=([^\s]+)(?: depends=([^\s]+))? -->')


def fail(line, message):
    raise Invalid(f'第 {line} 行：{message}', error_code=Code.DESIGN_MARKDOWN, line=line)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def split(value, delimiter, *, fields=False, arrays=False):
    """Split outside complete JSON strings; prose brackets and lone quotes stay literal."""
    result, start, index, field_start = [], 0, 0, 0
    decoder = json.JSONDecoder()
    while index < len(value):
        if value[index] == '"':
            prefix = value[field_start if fields else start:index].strip()
            field = prefix
            quoted = not prefix or fields and (field in
                      {'位置', '版本', '确认人', '层级', '入口', '环境', '替身', '隔离', '隔离依据', '用例'}
                      or arrays and prefix.endswith('、') and field.partition(' ')[0] in
                      {'入口', '替身', '隔离依据', '用例'})
            if quoted:
                try:
                    _, end = decoder.raw_decode(value, index)
                except ValueError:
                    pass
                else:
                    tail = value[end:].lstrip()
                    if not tail or any(tail.startswith(mark.lstrip()) for mark in (delimiter, '、', '；', ' / ')):
                        index = end
                        continue
        if value.startswith(delimiter, index):
            result.append(value[start:index].strip())
            index += len(delimiter)
            start = field_start = index
        else:
            if fields and value[index] == '；':
                field_start = index + 1
            index += 1
    return result + [value[start:].strip()]


def scalar(value):
    return json.loads(value) if value.startswith('"') else value


def display(value):
    if (not value or value != value.strip() or any(c in value for c in '"[]{}\n\r；、|') or value in ('无', '—') or ' / ' in value):
        return dumps(value)
    return value


def inline(value, *, item=False):
    """One readable line, with entities only for line breaks and ambiguous list boundaries."""
    left, right = len(value) - len(value.lstrip()), len(value.rstrip())
    quote_start = False
    if item and value.startswith('"'):
        try:
            _, end = json.JSONDecoder().raw_decode(value)
            quote_start = end != len(value)
        except ValueError:
            quote_start = True
    return ''.join(f'&#{ord(char)};' if char in '\r\n' or item and (
        char.isspace() and (index < left or index >= right)
        or index == 0 and (value == '无' or char == '[' or quote_start)) else html.escape(char, quote=False)
        for index, char in enumerate(value))


def unquote(value, separators):
    try:
        decoded = json.loads(value) if value.startswith('"') else None
    except ValueError:
        decoded = None
    if isinstance(decoded, str) and any(mark in decoded for mark in separators):
        value = decoded
    return html.unescape(value)


def array(value, separator='、', *, outer=()):
    if value == '无':
        return []
    if value.startswith('['):
        return json.loads(value)
    return [unquote(part, (separator, *outer)) for part in split(value, separator)]


def listing(values, separator='、', *, outer=()):
    return separator.join(dumps(inline(value)) if any(mark in value for mark in (separator, *outer))
                          else inline(value, item=True) for value in values) if values else '无'


def normalize_body(body):
    lines = [line.rstrip() for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    left, right = 0, len(lines)
    while left < right and not lines[left]:
        left += 1
    while right > left and not lines[right - 1]:
        right -= 1
    return '\n'.join(lines[left:right])


def source_text(values):
    return ' / '.join('位置 ' + listing([v['ref']], '；', outer=(' / ',)) + '；版本 ' + listing([v['version']], '；', outer=(' / ',))
                      + '；确认人 ' + listing([v['confirmed_by']], '；', outer=(' / ',)) for v in values)


def sources(value):
    rows = []
    for item in split(value, ' / ', fields=True):
        fields = split(item, '；', fields=True)
        if len(fields) == 3 and fields[0].startswith('位置 '):
            rows.append({key: unquote(part.removeprefix(label + ' '), ('；', ' / ')) for key, label, part in
                         zip(('ref', 'version', 'confirmed_by'), ('位置', '版本', '确认人'), fields)})
        else:
            match = re.fullmatch(r'(.+)（([^，]+)，(.+) 确认）', item)
            require(match is not None, '依据格式应为：位置 <原文>；版本 <版本>；确认人 <姓名>')
            rows.append(dict(zip(('ref', 'version', 'confirmed_by'), match.groups())))
    return rows


def verification_text(value):
    return '；'.join(['自动'] +
                    [label + ' ' + listing(value[key], outer=('；',))
                     for label, key in (('用例', 'cases'), ('替身', 'substitutes')) if value[key]])


def verification(value):
    parts = split(value, '；', fields=True, arrays=True)
    require(parts[0] != '人工', '人工执行按场景逐条记录，用 tw team scenarios submit 登记')
    require(parts[0] == '自动', '验证方式填写自动')
    fields = {}
    for item in parts[1:]:
        label, sep, val = item.partition(' ')
        require(label not in {'层级', '入口', '环境', '隔离', '隔离依据'},
                '请改为“验证：自动；用例 <用例>；替身 <替身>”；覆盖范围写在 .tw/config.json 的 checks.<编号>.coverage')
        require(sep and label not in fields, '验证标签缺值或重复：' + label)
        fields[label] = val.strip()
    require(fields.keys() <= {'替身', '用例'}, '未知验证标签')
    result = {'method': 'automatic',
              'cases': array(fields.get('用例', '无'), outer=('；',)),
              'substitutes': array(fields.get('替身', '无'), outer=('；',))}
    strings(result['cases']); strings(result['substitutes'])
    return result


def cell(value):
    return html.escape(value, quote=False).replace('|', '&#124;').replace('\n', '&#10;').replace('\r', '&#13;')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
                     + ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])


def table_rows(lines, start, headers):
    def cells(raw):
        return [html.unescape(v.strip()) for v in raw.strip().strip('|').split('|')]
    require(cells(lines[start]) == list(headers), '表格列应为：' + '、'.join(headers))
    require(start + 1 < len(lines) and len(cells(lines[start + 1])) == len(headers)
            and all(re.fullmatch(r':?-{3,}:?', v) for v in cells(lines[start + 1])), '表格分隔行缺失或列数不正确')
    rows = []
    end = start + 2
    while end < len(lines) and lines[end].startswith('|'):
        values = cells(lines[end])
        if len(values) != len(headers):
            fail(end + 1, '表格列数不正确')
        rows.append((end + 1, values))
        end += 1
    return rows, end


def body_transform(body, escape):
    """Quote reserved prose syntax reversibly, without changing examples inside fences."""
    lines = body.split('\n')
    fence, unclosed = None, None
    if escape:
        for index, line in enumerate(lines):
            found = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if not found:
                continue
            token = found[1]
            if fence is None:
                fence, unclosed = (token[0], len(token)), index
            elif token[0] == fence[0] and len(token) >= fence[1] and not line[found.end():].strip():
                fence, unclosed = None, None
    result, fence = [], None
    for index, line in enumerate(lines):
        found = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if found:
            if escape and unclosed is not None and index >= unclosed:
                result.append('\\' + line)
                continue
            token = found[1]
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not line[found.end():].strip():
                fence = None
            result.append(line)
            continue
        bare = line.lstrip('\\')
        match = LABEL.fullmatch(bare)
        reserved = ((match and (match[1] in LABELS | RETIRED_LABELS or match[1].startswith('数据 ')))
                    or bare.startswith('<!-- tw-section') or bare == '<!-- tw-issues -->'
                    or re.match(r'^ {0,3}(`{3,}|~{3,})', bare))
        if fence is None and reserved:
            line = '\\' + line if escape else line[1:] if line.startswith('\\') else line
        result.append(line)
    return '\n'.join(result)


def render(value):
    from designs import validate_design
    validate_design(value)
    lines = ['---'] + [key + ': ' + dumps(value[field]) for key, field in HEADER.items()] + ['---']
    for row in value['sections']:
        marker = '<!-- tw-section id=' + row['id'] + ' type=' + row['type']
        if row['depends_on']:
            marker += ' depends=' + ','.join(row['depends_on'])
        lines.extend(['', '## ' + cell(row['title']), marker + ' -->',
                      body_transform(normalize_body(row['body']), True)])
        data, used = row['data'], set()
        labeled = False
        def label(name, val):
            nonlocal labeled
            if not labeled or lines[-1].startswith('|'):
                lines.append('')
            lines.append('- ' + name + '：' + val)
            labeled = True
        if row['type'] == 'global-scope':
            label('需求级验收', listing(data['requirement_acceptance']))
            used.update(('requirement_acceptance', 'impact'))
            lines.append('')
            lines.append(table(IMPACT, [[listing(r[k], '；' if k == 'operations' else '、') if isinstance(r[k], list)
                                        else display(r[k]) for k in IMPACT_KEYS] for r in data['impact']]))
        elif row['type'] == 'acceptance':
            label('场景', '；'.join(inline(ref['path']) + '#' + listing(ref['nodes']) for ref in data['scenarios']))
            if 'sources' in data:
                label('依据', source_text(data['sources']))
            label('检查', listing(data['checks']))
            if 'verification' in data:
                label('验证', verification_text(data['verification']))
            used.update(('scenarios', 'sources', 'checks', 'verification'))
        elif row['type'] == 'task':
            for name, key in (('验收', 'acceptance'), ('范围', 'scope'), ('前置任务', 'blocked_by')):
                label(name, listing(data[key]))
                used.add(key)
            if 'assessment' in data:
                label('评估', dumps(data['assessment']))
                used.add('assessment')
        for key in sorted(data.keys() - used):
            label('数据 ' + json.dumps(key, ensure_ascii=True), dumps(data[key]))
    if value['issues']:
        lines.extend(['', '## 已知问题', '<!-- tw-issues -->', ''])
        rows = []
        for issue in value['issues']:
            rows.append([display(issue[k]) if isinstance(issue[k], str) else listing(issue[k])
                         for k in ('id', 'summary', 'owner', 'affects', 'blocks', 'state')]
                        + [('—' if k not in issue['resolution'] else listing(issue['resolution'][k]) if k == 'evidence'
                            else display(issue['resolution'][k])) for k in RESOLUTION])
        lines.append(table(ISSUES, rows))
    return '\n'.join(lines) + '\n'


def load(raw, *, scenario_reader):
    from designs import SECTION_TYPES, validate_design, validate_assessment, _path
    from contracts import issue as validate_issue, material, sources as validate_sources
    if raw.lstrip().startswith(('{', '[')):
        fail(1, 'JSON 方案已停用，请改写为 Markdown，格式见 references/designs.md')
    # Keep source positions; normalize only section bodies after extracting labels and tables.
    lines = raw.split('\n')
    if lines[-1] == '':
        lines.pop()
    structural = [line.removesuffix('\r') for line in lines]
    if not structural or structural[0] != '---':
        fail(1, '缺少 Markdown 文件头，格式见 references/designs.md')
    head, locations = {}, {}
    try:
        end = structural.index('---', 1)
    except ValueError:
        fail(1, '文件头缺少结束的 ---')
    for index in range(1, end):
        key, sep, val = structural[index].partition(':')
        if not sep or key not in HEADER or key in head:
            fail(index + 1, '未知或重复的文件头字段：' + key)
        try:
            head[key] = json.loads(val)
        except ValueError as exc:
            fail(index + 1, '文件头需要 JSON 值：' + str(exc))
        locations[key] = index + 1
    if set(head) != set(HEADER):
        fail(end + 1, '缺少文件头字段：' + '、'.join(sorted(HEADER.keys() - head.keys())))
    value = {'data_version': 1, 'kind': 'design', **{field: head[key] for key, field in HEADER.items()}, 'sections': [], 'issues': []}
    if type(value['revision']) is not int or value['revision'] < 1:
        fail(locations['revision'], 'revision 必须是正整数')
    for key in ('design', 'task'):
        try:
            text(head[key])
        except Invalid as exc:
            fail(locations[key], str(exc))
    try:
        obj(value['roles'], {'design_owner', 'implementation_owner', 'acceptance_owner'})
        for role in value['roles'].values():
            require(isinstance(role, str), 'Role assignments must be text')
    except (Invalid, TypeError) as exc:
        fail(locations['roles'], str(exc))
    try:
        validate_assessment(value['assessment'])
    except (Invalid, TypeError) as exc:
        fail(locations['assessment'], str(exc))
    marked, fence = [], None
    for index in range(end + 1, len(lines)):
        line = structural[index]
        found = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if found:
            token = found[1]
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not line[found.end():].strip():
                fence = None
            continue
        if fence is not None:
            continue
        if line.startswith('<!-- tw-section') or line == '<!-- tw-issues -->':
            heading = HEADING.fullmatch(structural[index - 1])
            if not heading:
                fail(index + 1, '标记必须紧跟标题下一行')
            marker = MARKER.fullmatch(line)
            if marker is None and line != '<!-- tw-issues -->':
                fail(index + 1, '章节标记格式错误')
            marked.append((index - 1, index, len(heading[1]), html.unescape(heading[2]), marker))
    seen, globals_, row_lines, origins, impact_lines, issue_lines = set(), [], {}, {}, [], {}
    for position, (heading, start, level, title, marker) in enumerate(marked):
        stop = next((h for h, _, depth, _, m in marked[position + 1:] if depth <= level or m is None), len(lines))
        content = lines[start + 1:stop]
        if marker is None:
            if value['issues']:
                fail(start + 1, '重复的已知问题表')
            try:
                first = next(i for i, line in enumerate(content) if line.strip())
                rows, _ = table_rows(lines, start + 1 + first, ISSUES)
                for number, cells in rows:
                    resolution = {key: array(cell) if key == 'evidence' else scalar(cell)
                                  for key, cell in zip(RESOLUTION, cells[6:]) if cell != '—'}
                    item = {**{key: scalar(cell) if key not in ('affects', 'blocks') else array(cell)
                               for key, cell in zip(('id', 'summary', 'owner', 'affects', 'blocks', 'state'), cells[:6])}, 'resolution': resolution}
                    try:
                        validate_issue(item)
                        require(item['id'] not in {r['id'] for r in value['issues']}, '重复问题编号：' + item['id'])
                    except (Invalid, ValueError, TypeError) as exc:
                        fail(number, str(exc))
                    value['issues'].append(item)
                    issue_lines[item['id']] = number
            except (Invalid, ValueError, StopIteration) as exc:
                if getattr(exc, 'line', None) is not None:
                    raise
                fail(start + 1, str(exc) or '缺少已知问题表')
            continue
        identifier, kind, depends = marker.groups()
        if identifier in seen:
            fail(start + 1, '重复章节编号：' + identifier)
        if kind not in SECTION_TYPES:
            fail(start + 1, '未知章节类型：' + kind)
        if kind == 'global-scope':
            globals_.append(identifier)
            if globals_ != ['scope-global']:
                fail(start + 1, '只能有一个全局范围，编号必须为 scope-global')
        seen.add(identifier)
        row_lines[identifier] = start + 1
        labels, data, body_end = {}, {}, len(content)
        allowed = ({'需求级验收'} if kind == 'global-scope' else
                   {'场景', '依据', '检查', '验证'} if kind == 'acceptance' else
                   {'验收', '范围', '前置任务', '评估'} if kind == 'task' else set())
        nested_start = next((h - start - 1 for h, _, depth, _, m in marked[position + 1:]
                             if h < stop and depth > level), len(content))
        fence = None
        for offset, line in enumerate(content[:nested_start]):
            found = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if found:
                if fence is None:
                    fence = (found[1][0], len(found[1]))
                elif found[1][0] == fence[0] and len(found[1]) >= fence[1] and not line[found.end():].strip():
                    fence = None
            if fence:
                continue
            match = LABEL.fullmatch(line.removesuffix('\r'))
            if kind == 'acceptance' and match and match[1] in RETIRED_LABELS:
                fail(start + offset + 2, '场景写在场景文件，验收节用 `- 场景：<路径>#<节点>`')
            if match and (match[1] in allowed or match[1].startswith('数据 ')):
                name, val = match.groups()
                if name in labels:
                    fail(start + offset + 2, '重复标签：' + name)
                labels[name] = (val, start + offset + 2)
                body_end = min(body_end, offset)
        def field(name, parser=scalar):
            if name not in labels:
                fail(start + 1, '缺少标签：' + name)
            val, number = labels[name]
            try:
                result = parser(val)
                if name in {'需求级验收', '检查', '验收', '范围', '前置任务'}:
                    strings(result, name in {'需求级验收', '验收'})
                if name == '范围':
                    for path in result:
                        _path(path)
                elif name == '依据':
                    validate_sources(result)
                elif name == '评估':
                    validate_assessment(result)
                return result
            except (Invalid, ValueError, TypeError, KeyError) as exc:
                reason = ('验收 ' + identifier + ' 的验证行：' if kind == 'acceptance' and name == '验证' else '')
                fail(number, reason + str(exc))
        table_indices = set()
        if kind == 'global-scope':
            data['requirement_acceptance'] = field('需求级验收', array)
            first = None
            try:
                first = next(i for i, line in enumerate(content[:nested_start]) if line.startswith('|'))
                rows, table_end = table_rows(lines, start + 1 + first, IMPACT)
                table_indices.update(range(first, table_end - start - 1))
                impact_lines = [number for number, _ in rows]
                data['impact'] = [{key: array(c, '；' if key == 'operations' else '、') if key in ('operations', 'acceptance') else scalar(c)
                                   for key, c in zip(IMPACT_KEYS, cells)} for _, cells in rows]
                body_end = min(body_end, first)
            except (Invalid, ValueError, StopIteration) as exc:
                fail(start + 2 + (first if first is not None else 0), str(exc) or '缺少影响范围表')
        elif kind == 'acceptance':
            def references(val):
                result = []
                for item in split(val, '；'):
                    filename, separator, nodes = item.partition('#')
                    require(separator and filename.strip(), '场景引用使用 <仓内路径>#<节点>')
                    filename = scalar(filename.strip())
                    _path(filename)
                    selected = array(nodes)
                    strings(selected, True)
                    from scenario_files import reference
                    result.append(reference(filename, selected, scenario_reader))
                return result
            data.update(scenarios=field('场景', references), checks=field('检查', array))
            if data['checks'] or '验证' in labels:
                data['verification'] = field('验证', verification)
            if '依据' in labels:
                data['sources'] = field('依据', sources)
        elif kind == 'task':
            data = {key: field(name, array) for name, key in (('验收', 'acceptance'), ('范围', 'scope'), ('前置任务', 'blocked_by'))}
            if '评估' in labels:
                data['assessment'] = field('评估', json.loads)
        for name in labels:
            if name.startswith('数据 '):
                key = scalar(name[3:])
                if key in data:
                    fail(labels[name][1], '重复数据字段：' + key)
                data[key] = field(name, json.loads)
        for offset in range(body_end, nested_start):
            if not content[offset].strip() or offset in table_indices:
                continue
            match = LABEL.fullmatch(content[offset].removesuffix('\r'))
            if not match or match[1] not in labels:
                fail(start + offset + 2, '标签之后只能有本节的数据标签或表格，正文请写在标签之前')
        body = normalize_body(body_transform('\n'.join(content[:body_end]), False))
        try:
            material(title)
            material(body)
        except (Invalid, TypeError) as exc:
            fail(heading + 1 if not isinstance(title, str) or not title.strip() else start + 2, str(exc))
        origins[identifier] = labels
        value['sections'].append({'id': identifier, 'type': kind, 'title': title, 'body': body,
                                  'data': data, 'depends_on': depends.split(',') if depends else []})
    if globals_ != ['scope-global']:
        fail(end + 1, '缺少唯一的 scope-global 全局范围')
    rows = {r['id']: r for r in value['sections']}
    for row in value['sections']:
        labels = origins[row['id']]
        for ref in row['depends_on']:
            if ref not in rows:
                fail(row_lines[row['id']], '引用不存在的章节：' + ref)
        if row['type'] == 'task':
            for field_, label, expected in (('acceptance', '验收', 'acceptance'), ('blocked_by', '前置任务', 'task')):
                for ref in row['data'][field_]:
                    if ref not in rows or rows[ref]['type'] != expected:
                        fail(labels[label][1], '引用不存在或类型不符的章节：' + ref)
            if 'assessment' in row['data']:
                if not set(row['data']['assessment']['uncertainties']) <= issue_lines.keys():
                    fail(labels['评估'][1], 'Assessment uncertainties must reference shared issue IDs')
    scope = rows['scope-global']['data']
    for ref in scope['requirement_acceptance']:
        if ref not in rows or rows[ref]['type'] != 'acceptance':
            fail(origins['scope-global']['需求级验收'][1], '引用不存在的验收章节：' + ref)
    for item, number in zip(scope['impact'], impact_lines):
        try:
            for key in ('repository', 'entrypoint', 'producer', 'consumer', 'commit_owner'):
                material(item[key])
            strings(item['operations'], True)
            strings(item['acceptance'], True)
            require(all(ref in rows and rows[ref]['type'] == 'acceptance' for ref in item['acceptance']), 'Impact needs actual acceptance references')
        except (Invalid, TypeError) as exc:
            fail(number, str(exc))
    for item in value['issues']:
        try:
            validate_issue(item, rows)
        except (Invalid, TypeError) as exc:
            fail(issue_lines[item['id']], str(exc))
    if not set(value['assessment']['uncertainties']) <= issue_lines.keys():
        fail(locations['assessment'], 'Assessment uncertainties must reference shared issue IDs')
    try:
        return validate_design(value)
    except (Invalid, ValueError, TypeError, KeyError) as exc:
        key = getattr(exc, 'key', None)
        number = row_lines.get(key, locations['roles'] if key == 'roles' else end + 1)
        fail(number, str(exc))
