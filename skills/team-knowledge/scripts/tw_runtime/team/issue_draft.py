"""Bring existing tasks into the team flow; every output is a draft to post."""
import json
import re

from common import digest, require, task_valid
import coordination
import designs
import records
from tw_runtime.team import platform_script as platform_read

BLOCK = re.compile(r'```team-workflow-task\s*\n.*?\n```', re.S)


def body(issue, task, parent):
    prose = re.sub(r'<!-- tw-task:start -->.*?<!-- tw-task:end -->', '', issue.get('body') or '', flags=re.S)
    prose = BLOCK.sub('', prose, count=1)
    # Replace a standalone task comment produced outside this helper as well.
    for match in reversed(records.matches(prose)):
        if records.kind(records.read(match[0])) == 'task':
            prose = prose[:match.start()] + prose[match.end():]
    prose = prose.rstrip()
    lines = ['<!-- tw-task:start -->', '## 任务', '', '目标：' + records.prose(task['goal']), '', '非目标：']
    lines += ['- ' + records.prose(value) for value in task['non_goals']] or ['- 无']
    lines += ['', '验收项：'] + ['- ' + records.prose(row['id']) + '：' + records.prose(row.get('expectation', '待补充验收预期')) for row in task['acceptance']]
    lines += ['', records.comment({'data_version': 1, 'parent': parent, 'task': task}), '<!-- tw-task:end -->', '']
    return (prose + '\n\n' if prose else '') + '\n'.join(lines)


def approval_request(url, design, reviewer):
    sections = designs.fingerprints(design)['sections']
    lines = [f'## 请求方案评审：{design["id"]} 第 {design["revision"]} 版', '',
             f'评审人：{reviewer or "（请指定具体的人）"}', '',
             '请阅读本 Issue 上的方案记录，确认以下章节。只回复“同意”不够，请写明认可的范围；'
             '需要修改时说明章节和原因。', '']
    for row in design['sections']:
        lines.append(f'- `{row["id"]}` {row["title"]}（指纹 {sections[row["id"]]["own"][:12]}）')
    lines += ['', '评审人确认后，生成批准草稿并按已有授权发布：', '',
              '```bash', f'tw team approval-draft --root "$PROJECT" --issue {url} --reviewer "{reviewer or "<评审人>"}" --confirmation "<认可的范围>"', '```']
    return '\n'.join(lines) + '\n'


def draft(root, profile, task, design=None, siblings=(), reviewer=None, *, design_path=None):
    rows = []
    for item in [task, *siblings]:
        url = item['id']
        platform_read.task_url(url)
        task_valid(item, profile, root)
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
        new_body = body(issue, item, parent)
        adopted = {**issue, 'body': new_body}
        coordination.task_source(adopted)
        row = {'issue': url, 'body': new_body, 'body_changed': new_body != issue.get('body'),
               'body_digest_before': digest(issue.get('body') or '')}
        if design is not None and design['task_id'] == url:
            published = coordination.draft_design(url, design, issue=adopted, path=design_path, root=root)
            row['design_comment'] = published['markdown']
            row['pr_description'] = published['pr_description']
            row['approval_request'] = approval_request(url, design, reviewer)
        rows.append(row)
    require(design is None or any('design_comment' in row for row in rows),
            'Include the issue that owns the design (its task_id) with --task or --with-task')
    steps = ['Replace each issue body with its drafted body (the original prose is kept verbatim).']
    if design is not None:
        steps += ['Post the design comment on the design issue.',
                  'Post the approval request and wait for the named reviewer to confirm the listed sections.',
                  'After explicit confirmation, run approval-draft and post the approval record.']
    steps.append('Run tw team start --issue <URL> for each issue; implementation starts only when it reports implementation_ready.')
    return {'ok': True, 'kind': 'issue-adoption-draft', 'read_only': True, 'issues': rows, 'next_steps': steps,
            'publication': 'draft-only; post in this order after reading the current issue again',
            'summary': f'已为 {len(rows)} 个任务生成接入草稿；工具没有修改平台。'}
