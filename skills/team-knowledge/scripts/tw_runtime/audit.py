"""Read-only health report. Separates structure, evidence availability and undecided business truth."""
from collections import Counter
import os
from pathlib import Path
import urllib.error
import urllib.request

from . import KB, brief, cache, check, entries, gitutil, textmatch

BIG_FILE = 20 * 1024 * 1024
LOCAL_MANAGED = {Path(cache.DIRECTORY).name, 'repositories.json'}


def run(project, links=False, top=10):
    structure = check.run(project)
    loaded = project.entries()
    knowledge = [e for e in loaded if e.kind in check.KNOWLEDGE]
    kinds = Counter(e.kind for e in loaded)
    memo, dirty, hotspots, unverified = {}, {}, [], []
    for entry in knowledge:
        pick = brief.Pick(entry, project.root, brief.SCOPE)
        status = brief.drift(pick, memo, dirty)
        if status['state'] != 'ok':
            unverified.append({'path': entry.path, 'status': status['text']})
        elif status['commits'] or status['dirty']:
            hotspots.append({'path': entry.path, 'commits': status['commits'], 'status': status['text']})
    hotspots.sort(key=lambda x: (-x['commits'], x['path']))
    similar = []
    for index, left in enumerate(knowledge):
        a = textmatch.title_phrases(left.title)
        for right in knowledge[index + 1:]:
            b = textmatch.title_phrases(right.title)
            if a and b and len(a & b) / len(a | b) >= 0.5:
                similar.append([left.path, right.path])
    near_limit = [{'path': e.path, 'chars': len(e.body.strip()), 'limit': entries.LIMITS[e.kind]}
                  for e in loaded if e.kind in entries.LIMITS and len(e.body.strip()) > 0.8 * entries.LIMITS[e.kind]]
    abandoned = sum(len(entries.abandoned(e.body) or []) for e in knowledge)
    report = {
        'structure': {'ok': structure['ok'], 'errors': len(structure['errors']), 'warnings': len(structure['warnings'])},
        'counts': dict(sorted(kinds.items())), 'abandoned_approaches': abandoned,
        'rejected_decisions': sum(1 for e in knowledge if e.fields.get('status') == 'rejected'),
        'lessons_without_guards': sorted(e.path for e in knowledge if e.kind == 'lesson' and not e.values('guards')),
        'change_hotspots': hotspots[:top], 'without_baseline': unverified,
        'similar_titles': similar, 'near_size_limit': near_limit,
        'shared': {alias: repo.describe() for alias, repo in sorted(project.shared().items())},
        'local': local_usage(project.root),
        'business_truth': '未判定：结构检查与提交变化只说明需要复核的位置，结论是否成立由评审和真实入口验证决定',
    }
    if links:
        report['links'] = check_links(project)
    return report


def local_usage(root):
    base = Path(root) / KB / 'local'
    files, size, big, unmanaged = 0, 0, [], []
    if base.is_dir():
        for directory, _, names in os.walk(base):
            for name in names:
                path = Path(directory) / name
                try:
                    length = path.stat().st_size
                except OSError:
                    continue
                files += 1
                size += length
                if length > BIG_FILE:
                    big.append(path.relative_to(root).as_posix())
        for path in sorted(base.iterdir()):
            if path.name not in LOCAL_MANAGED:
                try:
                    unmanaged.append({'path': path.relative_to(root).as_posix(), 'bytes': material_size(path)})
                except OSError:
                    continue
    return {'files': files, 'bytes': size, 'over_20MiB': sorted(big), 'unmanaged': unmanaged}


def material_size(path):
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    return sum((Path(directory) / name).lstat().st_size
               for directory, _, names in os.walk(path) for name in names)


def check_links(project):
    urls = set()
    for entry in project.entries():
        urls.update(v for v in entry.values('source') if v.startswith(('http://', 'https://')))
    for doc in (project.config or {}).get('documents', []) or []:
        if isinstance(doc, dict) and str(doc.get('source', '')).startswith(('http://', 'https://')):
            urls.add(doc['source'])
    results = []
    for url in sorted(urls):
        request = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'tw-audit'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                results.append({'url': url, 'result': 'ok', 'status': response.status})
        except urllib.error.HTTPError as exc:
            results.append({'url': url, 'result': 'missing' if exc.code in (404, 410) else 'http-error', 'status': exc.code})
        except (urllib.error.URLError, OSError) as exc:
            results.append({'url': url, 'result': 'unreachable', 'reason': str(getattr(exc, 'reason', exc))})
    return results


def render(report):
    lines = ['# 知识库健康报告', '',
             f'结构检查：{"通过" if report["structure"]["ok"] else "有错误"}（错误 {report["structure"]["errors"]}，警告 {report["structure"]["warnings"]}；详情运行 tw check）',
             '条目：' + '，'.join(f'{k} {v}' for k, v in report['counts'].items()) +
             f'；放弃过的做法 {report["abandoned_approaches"]} 项；已拒绝决策 {report["rejected_decisions"]} 条', '']
    if report['change_hotspots']:
        lines += ['## 核实后相关代码变化最多', *[f'- {x["path"]}：{x["status"]}' for x in report['change_hotspots']], '']
    if report['without_baseline']:
        lines += ['## 变化情况无法计算', *[f'- {x["path"]}：{x["status"]}' for x in report['without_baseline']], '']
    if report['lessons_without_guards']:
        lines += ['## 没有防护引用的教训', *[f'- {p}' for p in report['lessons_without_guards']], '']
    if report['similar_titles']:
        lines += ['## 标题相近，可能重复', *[f'- {a} ↔ {b}' for a, b in report['similar_titles']], '']
    if report['near_size_limit']:
        lines += ['## 接近篇幅上限', *[f'- {x["path"]}：{x["chars"]}/{x["limit"]}' for x in report['near_size_limit']], '']
    if report['shared']:
        lines += ['## 共享仓', *[f'- {k}：{v}' for k, v in report['shared'].items()], '']
    local = report['local']
    lines += [f'本地目录 {KB}/local：{local["files"]} 个文件，{local["bytes"] / 1048576:.1f} MiB' +
              (f'；超过 20MiB 的原件：{"、".join(local["over_20MiB"])}' if local['over_20MiB'] else ''), '']
    if local['unmanaged']:
        lines += ['## 不归工具管理的本机材料',
                  *[f'- {x["path"]}：{x["bytes"]} 字节（{x["bytes"] / 1048576:.1f} MiB）' for x in local['unmanaged']], '']
    if 'links' in report:
        lines += ['## 外部链接', *[f'- {x["url"]}：{x["result"]}' for x in report['links']], '']
    lines.append(report['business_truth'])
    return '\n'.join(lines) + '\n'
