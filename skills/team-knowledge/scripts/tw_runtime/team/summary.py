"""Plain-language account of a verification result for the person who must confirm or close it.

Field names stay in the structured result; this text explains what they mean in ordinary words.
"""


def disposition(completed):
    if completed['files']:
        return '改动知识文件：' + '、'.join(completed['files']) + (f'（{completed["reason"]}）' if completed.get('reason') else '')
    return '无需修改知识：' + completed['reason']


def _lines(items, empty):
    return [f'- {item}' for item in items] or [f'- {empty}']


def delivery_status(result):
    """整体交付：场景在当前产品上全部通过或沿用、受阻已处置，知识与交接记录齐全。"""
    complete = bool(result.get('delivery_complete'))
    return {'overall_complete': complete, 'summary': '交付完成' if complete else result.get('summary', '交付材料待齐全')}


def render(result, task, profile=None):
    checks = (profile or {}).get('checks', {})
    accepted = result.get('business_accepted')
    delivered = result.get('delivery_complete')
    lines = [f'**任务**：{task.get("goal", task["id"])}（{task["id"]}）', '']
    lines.append('**验证了哪些业务场景**')
    named_cases = result.get('named_cases', {})
    lines += _lines([f'{row["id"]}：' + row['expectation'].rstrip('。；; ')
                     + ('；用例 ' + '、'.join(named_cases[row['id']]) if named_cases.get(row['id']) else
                        '；未指明用例，证据为整项检查通过' if row['id'] in result.get('unspecified_cases', []) else '')
                     for row in task.get('acceptance', [])], '没有登记验收场景')
    if 'summary_counts' in result:
        lines += ['', '场景汇总：' + '，'.join(key + ' ' + str(value) for key, value in result['summary_counts'].items())]
        stats = result['statistics']
        for key, label in (('first_pass', '一次通过率'), ('agreement', '多人一致')):
            ratio = stats[key]
            lines.append(label + '：' + str(ratio['numerator']) + '/' + str(ratio['denominator']))
    lines += ['', '**哪些检查实际运行并通过**']
    lines += _lines([f'{key}：{checks.get(key, {}).get("purpose", "项目检查")}' for key in result.get('checks', [])],
                    '没有必需检查')
    for row in result.get('re_evaluated', []):
        lines.append(f'- {row["check"]}：按当前用例登记，用原始运行报告重新判定为通过（运行时判定为 {row["original_status"]}，未重跑）')
    for key, excerpt in result.get('output_excerpts', {}).items():
        lines += ['- ' + key + ' 原始输出摘录：'] + ['    ' + line for line in excerpt]
    environment = result.get('environment_checked')
    if environment:
        lines.append(f'- 运行环境：{"本次实际核对" if environment == "now" else "沿用业务验收当时记录的环境"}')
    ci_checks = result.get('ci_verified_checks', [])
    open_items = (['导入的 CI 检查：' + '、'.join(ci_checks)] if ci_checks else
                  ['检查只在本机运行，CI 未验证'] if result.get('checks') else [])
    if result.get('superseded_execution'):
        open_items.append(f'{len(result["superseded_execution"])} 份较早或已过期的运行记录未被采用，仅作历史保留')
    if result.get('tool', {}).get('override'):
        open_items.append('本次使用了被修改过的工具安装（已显式允许并记录）')
    lines += ['', '**还没做或需要注意的**'] + _lines(open_items, '没有')
    if result.get('unverified_scope'):
        lines += ['', '**未验证范围**'] + [
            '- ' + row['scenario'] + '：' + row['status'] + '；问题 ' + row['finding'] + '：' + row['finding_state']
            for row in result['unverified_scope']]
    knowledge = result.get('knowledge_disposition')
    if knowledge:
        lines += ['', f'**知识处置**：{knowledge}']
    lines += ['', '**状态**']
    lines.append('- ' + delivery_status(result)['summary'])
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
