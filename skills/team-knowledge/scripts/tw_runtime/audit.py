"""Read-only health report. Separates structure, evidence availability and undecided business truth."""
from collections import Counter
from datetime import date, datetime
import os
from pathlib import Path
import urllib.error
import urllib.request

from . import KB, brief, cache, check, entries, gitutil, textmatch

BIG_FILE = 20 * 1024 * 1024
LOCAL_MANAGED = {Path(cache.DIRECTORY).name, 'repositories.json'}


def run(project, links=False, top=10):
    top = max(0, top)
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
    recurring = []
    for entry in knowledge:
        dates = entries.occurrence_dates(entry)
        if len(dates) > 1:
            recurring.append({'path': entry.path, 'kind': entry.kind, 'dates': dates,
                              'promote': entry.kind == 'lesson' and len(dates) >= entries.PROMOTE_AT})
    recurring.sort(key=lambda x: x['path'])
    recurring.sort(key=lambda x: x['dates'][-1], reverse=True)
    recurring.sort(key=lambda x: len(x['dates']), reverse=True)
    report = {
        'structure': {'ok': structure['ok'], 'errors': len(structure['errors']), 'warnings': len(structure['warnings'])},
        'counts': dict(sorted(kinds.items())), 'abandoned_approaches': abandoned,
        'rejected_decisions': sum(1 for e in knowledge if e.fields.get('status') == 'rejected'),
        'recurring': recurring,
        'lessons_without_guards': sorted(e.path for e in knowledge if e.kind == 'lesson' and not e.values('guards')),
        'change_hotspots': hotspots[:top], 'without_baseline': unverified,
        'similar_titles': similar, 'near_size_limit': near_limit,
        'shared': {alias: repo.describe() for alias, repo in sorted(project.shared().items())},
        'local': local_usage(project.root), 'top': top,
        'business_truth': '未判定：结构检查与提交变化只说明需要复核的位置，结论是否成立由评审和真实入口验证决定',
    }
    if links:
        report['links'] = check_links(project)
    return report


def local_usage(root):
    base = Path(root) / KB / 'local'
    items, big = [], []
    if base.is_dir():
        for path in base.iterdir():
            size, count, modified = 0, 0, path.lstat().st_mtime
            material = [path]
            if path.is_dir() and not path.is_symlink():
                material = []
                for directory, dirs, names in os.walk(path):
                    modified = max(modified, Path(directory).lstat().st_mtime)
                    material.extend(Path(directory) / name for name in names)
                    material.extend(Path(directory) / name for name in dirs if (Path(directory) / name).is_symlink())
            for file in material:
                try:
                    stat = file.lstat()
                except OSError:
                    continue
                size += stat.st_size
                count += 1
                modified = max(modified, stat.st_mtime)
                if stat.st_size > BIG_FILE:
                    big.append({'path': file.relative_to(root).as_posix(), 'bytes': stat.st_size})
            last = datetime.fromtimestamp(modified).date()
            age = (date.today() - last).days
            items.append({'path': path.relative_to(root).as_posix(), 'bytes': size, 'files': count,
                          'modified': last.isoformat(), 'age_days': age, 'stale': age > 30,
                          'managed': path.name in LOCAL_MANAGED})
    items.sort(key=lambda x: (-x['bytes'], x['path']))
    big.sort(key=lambda x: (-x['bytes'], x['path']))
    return {'files': sum(x['files'] for x in items), 'bytes': sum(x['bytes'] for x in items),
            'items': items, 'large_files': big}


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
    if report['recurring']:
        lines += ['## 反复出现', *[f'- {x["path"]}：出现 {len(x["dates"])} 次（{"、".join(x["dates"])}）'
                                   + ('，待升级为 rule' if x['promote'] else '') for x in report['recurring']], '']
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
    top = report['top']
    lines += ['## 本机材料', f'本地目录 {KB}/local：{local["files"]} 个文件，{local["bytes"] / 1048576:.1f} MiB', '']
    for item in local['items'][:top]:
        flags = ('；工具管理' if item['managed'] else '') + ('；30 天以上未修改' if item['stale'] else '')
        lines.append(f'- {item["path"]}：{item["bytes"] / 1048576:.1f} MiB，{item["files"]} 个文件，'
                     f'最后修改 {item["modified"]}，距今 {item["age_days"]} 天{flags}')
    remainder = local['items'][top:]
    if remainder:
        lines.append(f'另有 {len(remainder)} 项，共 {sum(x["bytes"] for x in remainder) / 1048576:.1f} MiB')
        stale = [x for x in remainder if x['stale']]
        if stale:
            lines += ['30 天以上未修改（其余项）：', *[f'- {x["path"]}：最后修改 {x["modified"]}，距今 {x["age_days"]} 天' for x in stale[:top]]]
            if len(stale) > top:
                lines.append(f'另有 {len(stale) - top} 项 30 天以上未修改')
        managed = [x['path'] for x in remainder if x['managed']]
        if managed:
            lines.append('工具管理：' + '、'.join(managed))
    big = local['large_files']
    if big:
        lines += ['', f'超过 20 MiB 的文件共 {len(big)} 个：',
                  *[f'- {x["path"]}：{x["bytes"] / 1048576:.1f} MiB' for x in big[:top]]]
    lines.append('')
    if 'links' in report:
        lines += ['## 外部链接', *[f'- {x["url"]}：{x["result"]}' for x in report['links']], '']
    lines.append(report['business_truth'])
    return '\n'.join(lines) + '\n'
