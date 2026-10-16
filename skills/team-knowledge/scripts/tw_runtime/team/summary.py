"""Plain-language account of a verification result for the person who must confirm or close it.

Field names stay in the structured result; this text explains what they mean in ordinary words.
"""


def disposition(completed):
    if completed['files']:
        return '改动知识文件：' + '、'.join(completed['files']) + (f'（{completed["reason"]}）' if completed.get('reason') else '')
    return '无需修改知识：' + completed['reason']


def _lines(items, empty):
    return [f'- {item}' for item in items] or [f'- {empty}']


def render(result, task, profile=None):
    checks = (profile or {}).get('checks', {})
    accepted = result.get('business_accepted')
    delivered = result.get('delivery_complete')
    lines = [f'**任务**：{task.get("goal", task["id"])}（{task["id"]}）', '']
    lines.append('**验证了哪些业务场景**')
    observations = result.get('observations', {})
    lines += _lines([f'{row["id"]}：{row["expectation"]}'
                     + (f'（{len(observations.get(row["id"], []))} 条实际观察）' if observations.get(row['id']) else '')
                     + ('；未指明用例，证据为整项检查通过' if row['id'] in result.get('unspecified_cases', []) else '')
                     for row in task.get('acceptance', [])], '没有登记验收场景')
    lines += ['', '**哪些检查实际运行并通过**']
    lines += _lines([f'{key}：{checks.get(key, {}).get("purpose", "项目检查")}' for key in result.get('checks', [])],
                    '没有必需检查')
    for row in result.get('re_evaluated', []):
        lines.append(f'- {row["check"]}：按当前用例登记，用原始运行报告重新判定为通过（运行时判定为 {row["original_status"]}，未重跑）')
    environment = result.get('environment_checked')
    if environment:
        lines.append(f'- 运行环境：{"本次实际核对" if environment == "now" else "沿用业务验收当时记录的环境"}')
    open_items = []
    if result.get('regression_pending'):
        open_items.append('有应沉淀的自动回归尚未完成（见 automation_status）')
    if result.get('superseded_execution'):
        open_items.append(f'{len(result["superseded_execution"])} 份较早或已过期的运行记录未被采用，仅作历史保留')
    if result.get('tool', {}).get('override'):
        open_items.append('本次使用了被修改过的工具安装（已显式允许并记录）')
    lines += ['', '**还没做或需要注意的**'] + _lines(open_items, '没有')
    knowledge = result.get('knowledge_disposition')
    if knowledge:
        lines += ['', f'**知识处置**：{knowledge}']
    lines += ['', '**状态**']
    lines.append(f'- 业务验收：{"已通过" if accepted else "未通过"}')
    lines.append(f'- 交付材料（验收、知识处置、交接）：{"齐全" if delivered else "未齐全"}')
    if result.get('closable'):
        authorization = result.get('close_authorization', {})
        lines.append(f'- 可以关闭：已有 {authorization.get("confirmed_by")} 的关闭授权（{authorization.get("reference")}）')
    elif delivered:
        if result.get('close_authorization'):
            lines.append('- 可以关闭：收尾说明或完整交接尚未发布')
        else:
            lines.append('- 可以关闭：还需要明确的关闭授权')
    else:
        lines.append('- 可以关闭：否')
    if result.get('close_note'):
        lines += ['', '**下一步**：按已有授权把下方“收尾说明”原样发布到 Issue，再核对关闭条件；工具不会自动发布或关闭。']
    return '\n'.join(lines) + '\n'
