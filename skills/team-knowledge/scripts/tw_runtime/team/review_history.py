"""Explicit review ancestry, per-file source evidence, and human fields to recheck."""
import design_files
import copy

from common import Invalid, artifact_valid, digest, read
import validation

BINDINGS = ('task_id', 'task_digest', 'source_digest', 'validation_policy', 'sections', 'risks', 'selected_runs')
LABELS = {'task_digest': '任务', 'source_digest': '源码', 'validation_policy': '校验策略',
          'sections': '章节', 'risks': '风险', 'selected_runs': '选中运行', 'approval_plan': '批准所用方案'}


def same_group(left, right):
    # Candidate failures do not expire a review when the established selector still uses the same passing runs.
    return (all(left.get(key) == right.get(key) for key in BINDINGS)
            and ('approval_plan' not in left or left['approval_plan'] == right.get('approval_plan')))


def approval_plan(design, history):
    # Combined consent also approves the assessment and roles, outside section fingerprints.
    return digest({'design': design, 'history': history})


def source_record(root, profile, task):
    state = validation.source(root, profile)
    files = {}

    def collect(value, prefix=''):
        for path, item in value.get('files', {}).items():
            files[prefix + path] = item
        for key, item in value.get('external_inputs', {}).items():
            name = prefix + '[' + key + ']'
            if 'files' in item:
                collect(item, name + '/')
            else:
                files[name] = item

    collect(state)
    return {'data_version': 1, 'kind': 'review-source', 'task_id': task['id'],
            'source_digest': digest(state), 'files': files}


def latest(root, state, current=None, group=None):
    """Follow recorded pointers, never infer ancestry from filenames or timestamps."""
    entry = state.get('latest')
    if not entry:
        submitted = state['submitted']
        wanted = (group or {}).get('review') or (current or {}).get('previous_review')
        if wanted:
            entry = next((row for row in submitted.values() if row['review'] == wanted), None)
        if not entry:
            entry = submitted.get((current or {}).get('bindings', {}).get('draft_id'))
        if not entry and len(submitted) == 1:
            entry = next(iter(submitted.values()))  # An unambiguous B1 record has no explicit latest pointer.
    if not entry:
        return None
    entry = copy.deepcopy(entry)
    if not entry.get('binding'):
        key = next((key for key, row in state['submitted'].items() if row['review'] == entry['review']), None)
        entry['binding'] = state['generations'][key]
    entry['value'] = read(artifact_valid(root, entry['binding']))
    entry['review_value'] = read(artifact_valid(root, entry['review']))
    entry['text'] = artifact_valid(root, entry['markdown']).read_bytes().decode('utf-8')
    entry['source_value'] = read(artifact_valid(root, entry['source'])) if entry.get('source') else entry['value'].get('source_snapshot')
    return entry


def carry(candidate, previous, fields, baseline):
    """Carry only editable text; generated bindings/results always come from the current snapshot."""
    names = ['评审信息', '规范 standards', '需求 spec', '问题清单']
    names += ['验收 ' + row['id'] for row in candidate['template']['acceptance']]
    names += ['人工观察 ' + key for key in candidate['manual']]
    names += [name for name in fields if name.startswith('问题 ')]
    candidate['prefill'] = {name: {key: item['value'] for key, item in fields[name]['fields'].items() if key != '复核'}
                            for name in names if name in fields}
    rechecks = []
    for name, values in candidate['prefill'].items():
        keys = ('结论', '理由', '证据文件') if name.startswith(('规范 ', '需求 ', '验收 ')) else (
            ('观察人', '时间', '操作', '结果', '数据', '证据文件') if name.startswith('人工观察 ') else (
            ('批准方案与代码', '批准说明') if name == '评审信息' and candidate.get('approval_needed') else ()))
        if any(values.get(key, '').strip() for key in keys):
            rechecks.append(name)
    candidate['rechecks'] = rechecks
    candidate['bindings']['recheck_sections'] = rechecks
    if baseline is None and (previous or {}).get('bindings', {}).get('source_digest') == candidate['source_snapshot']['source_digest']:
        # Equal content-bound source digests prove an unchanged tree, even for a B1 record without a file list.
        baseline = candidate['source_snapshot']
    old_files = (baseline or {}).get('files', {})
    new_files = candidate['source_snapshot']['files']
    files = sorted(name for name in old_files.keys() | new_files.keys() if old_files.get(name) != new_files.get(name)) if baseline else []
    old_results = (previous or {}).get('acceptance_results')
    if old_results is not None:
        changed = sorted(key for key, row in candidate['acceptance_results'].items() if old_results.get(key) != row and row['checks'])
    else:
        old_runs = (previous or {}).get('bindings', {}).get('selected_runs', {})
        changed = sorted(key for key, row in candidate['acceptance_results'].items()
                         if any(old_runs.get(check) != result['run'] for check, result in row['checks'].items()))
    bindings = [label for key, label in LABELS.items() if (previous or {}).get('bindings', {}).get(key) != candidate['bindings'].get(key)]
    candidate['changes'] = {'files': files, 'acceptance': changed, 'bindings': bindings, 'baseline_complete': baseline is not None}
    lines = ['- 绑定变化：' + ('、'.join(bindings) or '工作草稿已过期')]
    if baseline is None:
        lines.append('- 上一轮未保存逐文件指纹，无法还原精确文件差异；预填内容均须重新核对。')
    elif not files:
        lines.append('- 源码文件：无内容变化。')
    for name in files:
        action = '新增' if name not in old_files else '删除' if name not in new_files else '修改'
        lines.append('- 文件：' + name + '（' + action + '）')
    lines.append('- 运行结果变化的验收项：' + ('、'.join(changed) or '无'))
    candidate['generated']['changes'] = '\n'.join(lines)


def status(root, profile, task, state, current, group=None, inputs=None):
    previous = latest(root, state, current, group)
    if not previous and not current:
        return None
    import delivery
    import designs
    from commands import local
    binding = {'task_id': task['id'], 'task_digest': digest(task),
               'source_digest': validation.source_digest(root, profile),
               'validation_policy': delivery.review_policy(root, profile, task), 'risks': task['risks']}
    try:
        design_path = getattr(inputs, 'design', None) or (group or {}).get('design', {}).get('path')
        design = design_files.read(local(root, design_path))
        hashes = designs.fingerprints(design)['sections']
        binding['sections'] = {key: hashes[key] for key in task['section_ids']}
        history_paths = getattr(inputs, 'design_history', None)
        if history_paths is None:
            history_paths = [row['path'] for row in (group or {}).get('design_history', [])]
        binding['approval_plan'] = approval_plan(design, [design_files.read(local(root, path)) for path in history_paths])
        paths = getattr(inputs, 'run', None)
        if paths is None:
            refs = (group or {}).get('selected_runs')
            paths = [row['path'] for row in refs if row] if refs is not None else [row['path'] for row in (group or {}).get('runs', [])]
        paths = [local(root, path).relative_to(root).as_posix() for path in paths]
        execution = validation.verify_runs(root, profile, task, paths, live=False)
        from common import artifact
        binding['selected_runs'] = {key: artifact(root, local(root, path)) for key, path in execution['selected_runs'].items()}
        valid = previous is not None and same_group(previous['value']['bindings'], binding)
    except (Invalid, OSError, ValueError, TypeError, KeyError):
        valid = False
    return {'current': valid, 'review': previous['review'] if previous else None, 'binding': binding,
            'draft_current': current is not None and same_group(current['bindings'], binding)}
