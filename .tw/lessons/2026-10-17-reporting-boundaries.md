---
title: "场景校验、交付判定与证据显示各守一个入口"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:tests/test_scenarios.py", "self:tests/test_scenario_rounds.py", "self:tests/test_scenario_acceptance.py", "self:tests/test_scenario_batch2.py", "self:tests/test_raw_output.py", "self:tests/test_checklist_records.py"]
source: ["self:skills/team-workflow/references/contracts.md", "self:tests/test_scenarios.py", "self:tests/test_raw_output.py"]
verified: {"self": {"commit": "6a1390ab33a5e57abe1ab0b6e918fd3c8b093315", "date": "2026-10-17"}}
guards: ["self:tests/test_scenarios.py#test_regression_command_check_is_rejected_at_its_line", "self:tests/test_scenario_rounds.py#test_command_check_without_case_report_is_rejected_before_submission", "self:tests/test_scenario_batch2.py#test_delivery_lists_three_pending_regressions_and_one_automated", "self:tests/test_raw_output.py#test_empty_stdout_and_stderr_bytes_survive_capture_and_delivery", "self:tests/test_checklist_records.py#test_text_labels_follow_their_own_fields", "self:tests/test_checklist_records.py#test_empty_files_are_content_bound_artifacts"]
tags: ["回归登记", "交付状态", "原始输出", "结构化原因", "字段含义", "空文件证据"]
---
# 场景校验、交付判定与证据显示各守一个入口

现象：场景指向只报告命令退出结果的检查仍通过校验，交付时才列为待沉淀；概要和摘要给出相反结论；空输出证据被写入占位文字，评审遗漏错误输出。交付后状态的第 7 步显示“使用了被修改的工具安装”，而安装完好；空的错误输出可以存为运行记录，却不能作为场景证据提交。

根因：检查格式约束放在运行选用层；材料齐全与整体完成分别拼接文字；证据保存层承担空输出显示，摘录又单独读取标准输出。一个字段承担两种含义：步骤的 `note` 原用于标记修改过的工具，又被用来存放交付阶段的整体状态，显示层把有 `note` 一律显示为修改过的工具。共用的文件引用按文件名给空输出开了例外。

修复与防护：格式约束集中在场景文件读取，方案载入原样传递场景文件错误及行号；回归判定携带原因供所有显示共用；整体交付状态统一计算；证据保存与双通道摘录分别处理。字段与显示契约引用工具约定的检查、进度和回归段。修改过的工具用 `tool_override` 标记，整体状态写在交付步骤的 `summary`，显示文字只读各自的字段；文件引用只要求文件存在，空文件按内容绑定，需要内容的读取方在解析时核对。

发现方法：用已登记的 command 检查执行场景校验；通过命令入口走完含回归待办的交付；执行只向错误输出写字节的检查，并核对证据文件与哈希。

适用条件：增加读取入口、交付文字或输出证据时，先确认其调用现行统一入口，再用真实命令核对保存与显示结果。
