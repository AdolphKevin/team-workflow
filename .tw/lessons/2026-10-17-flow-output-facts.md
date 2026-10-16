---
title: "开工、状态与摘要应读取同一份事实"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:tests/test_four_command_delivery.py", "self:tests/test_ci_summary.py", "self:tests/test_scenario_acceptance.py", "self:tests/test_error_categories.py"]
source: ["self:docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md"]
verified: {"self": {"commit": "3cab1d3b07e003e639767befad3a1380ec4d8786", "date": "2026-10-17"}}
guards: ["self:tests/test_four_command_delivery.py#test_simple_start_and_status_share_steps_and_next_command", "self:tests/test_four_command_delivery.py#test_medium_start_and_status_share_steps_and_next_command", "self:tests/test_ci_summary.py#test_accept_summary_lists_only_selected_imported_checks", "self:tests/test_error_categories.py#test_scenario_repair_uses_states_with_arbitrary_problem_text"]
tags: ["下一步", "开工", "摘要", "CI", "场景处置"]
---
# 开工、状态与摘要应读取同一份事实

现象：开工提示与紧接着的状态查询指向不同步骤；只有本机检查的交付摘要把待注意事项写成“没有”；受阻场景等待问题处置时，下一步指向空的待执行清单。

根因：开工单独拼接流程；摘要没有读取选中运行的来源；恢复指引只有场景验收错误代码，缺少具体场景状态。

修复与防护：开工保存当前材料后复用状态入口，计算中带上本次尚待保存的响应；首次开工和接续都与随后查询比较。摘要从选中的记录读取 CI 事实，历史导入记录被较新的本机运行取代时按当前选用结果报告。场景验收错误携带各状态的场景编号，恢复指引按字段选择场景执行或问题评审；用任意说明文字核对选择结果。

发现方法：连续执行开工、状态查询与给出的下一条命令；分别使用本机、导入以及两者都有的运行记录；将受阻问题保留 open 后观察验收的恢复命令。

适用条件：新增流程出口、调整运行选用或增加错误恢复分支时。场景及交付规则的正文见来源方案和技能中的工具约定。
