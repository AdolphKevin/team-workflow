---
title: "场景校验、交付判定与证据显示各守一个入口"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:tests/test_scenarios.py", "self:tests/test_scenario_rounds.py", "self:tests/test_scenario_acceptance.py", "self:tests/test_scenario_batch2.py", "self:tests/test_raw_output.py"]
source: ["self:skills/team-workflow/references/contracts.md", "self:tests/test_scenarios.py", "self:tests/test_raw_output.py"]
verified: {"self": {"commit": "b019050d38e6510c6f85e60b6874dbe9c93ac65c", "date": "2026-10-17"}}
guards: ["self:tests/test_scenarios.py#test_regression_command_check_is_rejected_at_its_line", "self:tests/test_scenario_rounds.py#test_command_check_without_case_report_is_rejected_before_submission", "self:tests/test_scenario_batch2.py#test_delivery_lists_three_pending_regressions_and_one_automated", "self:tests/test_raw_output.py#test_empty_stdout_and_stderr_bytes_survive_capture_and_delivery"]
tags: ["回归登记", "交付状态", "原始输出", "结构化原因"]
---
# 场景校验、交付判定与证据显示各守一个入口

现象：场景指向只报告命令退出结果的检查仍通过校验，交付时才列为待沉淀；概要和摘要给出相反结论；空输出证据被写入占位文字，评审遗漏错误输出。

根因：检查格式约束放在运行选用层；材料齐全与整体完成分别拼接文字；证据保存层承担空输出显示，摘录又单独读取标准输出。

修复与防护：格式约束集中在场景文件读取，方案载入原样传递场景文件错误及行号；回归判定携带原因供所有显示共用；整体交付状态统一计算；证据保存与双通道摘录分别处理。字段与显示契约引用工具约定的检查、进度和回归段。

发现方法：用已登记的 command 检查执行场景校验；通过命令入口走完含回归待办的交付；执行只向错误输出写字节的检查，并核对证据文件与哈希。

适用条件：增加读取入口、交付文字或输出证据时，先确认其调用现行统一入口，再用真实命令核对保存与显示结果。
