"""Bring existing tasks into the team flow; every output is a draft to post."""
import json
import re

from common import digest, require, task_valid
import coordination
import designs
import records
import task_inputs
from tw_runtime.team import platform_script as platform_read

BLOCK = re.compile(r'```team-workflow-task\s*\n.*?\n```', re.S)


def body(issue, task, parent, design=None):
    task_inputs.validate_written(task)
    prose = re.sub(r'<!-- tw-task:start -->.*?<!-- tw-task:end -->', '', issue.get('body') or '', flags=re.S)
    prose = BLOCK.sub('', prose, count=1)
    # Replace a standalone task comment produced outside this helper as well.
    for match in reversed(records.matches(prose)):
        if records.kind(records.read(match[0])) == 'task':
            prose = prose[:match.start()] + prose[match.end():]
    prose = prose.rstrip()
    lines = ['<!-- tw-task:start -->', '## 任务', '', '目标：' + records.prose(task['goal']), '', '非目标：']
    lines += ['- ' + records.prose(value) for value in task['non_goals']] or ['- 无']
    labels = {row['id']: designs.section_label(row) for row in (design or {}).get('sections', [])}
    lines += ['', '验收项：'] + ['- ' + records.prose(labels.get(row['id'], row['id']))
                           for row in task['acceptance']]
    lines += ['', records.comment({'data_version': 1, 'parent': parent, 'task': task}), '<!-- tw-task:end -->', '']
    return (prose + '\n\n' if prose else '') + '\n'.join(lines)


def approval_request(url, design, reviewer):
    sections = designs.fingerprints(design)['sections']
    lines = [f'## 请求方案评审：{design["id"]} 第 {design["revision"]} 版', '',
             f'评审人：{reviewer or "（请指定具体的人）"}', '',
             '请阅读方案原文，确认以下章节。方案记录发布在承载方案的变更请求上；没有变更请求时发布在任务上。'
             '只回复“同意”不够，请写明认可的范围；'
             '需要修改时说明章节和原因。', '']
    for row in design['sections']:
        lines.append(f'- {designs.section_label(row, code_id=True)}（指纹 {sections[row["id"]]["own"][:12]}）')
    lines += ['', '评审人确认后，生成批准草稿并按已有授权发布：', '',
              '```bash', f'tw team approval-draft --root "$PROJECT" --issue {url} --reviewer "{reviewer or "<评审人>"}" --confirmation "<认可的范围>"', '```']
    return '\n'.join(lines) + '\n'


def draft(root, profile, task, design=None, siblings=(), reviewer=None, *, design_path=None):
    rows = []
    reconciliations = []
    for item in [task, *siblings]:
        url = item['id']
        platform_read.task_url(url)
        task_inputs.validate_written(item)
        task_valid(task_inputs.expand(item, design) if design else item, profile, root, written=design is None)
        parent = None
        if design is not None and design['task_id'] != url:
            parent = design['task_id']
            require(item.get('parent') == parent and item.get('acceptance_scope') == 'task',
                    f'{url} shares the design of {parent}: set "parent" and acceptance_scope "task"')
        else:
            require(item.get('parent') in (None, parent), f'{url}: parent differs from the design owner issue')
        if design is not None:
            coordination.validate_task_design(item, design)
        issue = coordination.platform_issue(url, root)
        require(issue.get('state', 'open') == 'open', f'{url} is closed; reopen it before drafting')
        new_body = body(issue, item, parent, design)
        adopted = {**issue, 'body': new_body}
        coordination.task_source(adopted)
        row = {'issue': url, 'body': new_body, 'body_changed': new_body != issue.get('body'),
               'body_digest_before': digest(issue.get('body') or '')}
        if design is not None and design['task_id'] == url:
            try:
                published = coordination.draft_design(url, design, issue=adopted, path=design_path, root=root)
            except coordination.DesignHistoryGap:
                reconciliations.append(url)
            else:
                row['design_comment'] = published['markdown']
                row['pr_description'] = published['pr_description']
                row['approval_request'] = approval_request(url, design, reviewer)
        rows.append(row)
    require(design is None or any(row['issue'] == design['task_id'] for row in rows),
            'Include the issue that owns the design (its task_id) with --task or --with-task')
    steps = ['用草稿替换各任务正文（保留原文），并完成变更请求描述等其他编辑。']
    if reconciliations:
        steps += ['方案历史需要对账；核对全部方案分支后，用 design-draft --issue ' + url
                  + ' --record <方案.md> --reconcile "<原因>" 发布方案。' for url in reconciliations]
    elif design is not None:
        steps += ['最后重新生成方案记录，立即发布到承载方案的变更请求上；没有变更请求时发布在任务上，之后不要修改更早的评论。',
                  '发布评审请求，请具名评审人阅读方案原文并确认所列章节。',
                  '确认后运行 approval-draft，按已有授权发布批准记录。']
    steps.append('逐个运行 tw team start --issue <URL>，按其实施就绪状态继续。')
    return {'ok': True, 'kind': 'issue-adoption-draft', 'read_only': True, 'issues': rows, 'next_steps': steps,
            'publication': 'draft-only; post in this order after reading the current issue again',
            'summary': f'已为 {len(rows)} 个任务生成接入草稿；工具没有修改平台。'}
