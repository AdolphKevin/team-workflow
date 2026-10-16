---
title: "完成阶段先读交付事实，再决定是否载入方案"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:tests/test_task_phases.py", "self:tests/test_platform_review.py"]
source: ["self:docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md", "self:skills/team-workflow/references/contracts.md"]
verified: {"self": {"commit": "6f8cb08f234c5b46478ec0b95175660d019a8cc3", "date": "2026-10-17"}}
guards: ["self:tests/test_task_phases.py#test_unrelated_commit_keeps_delivered_records_and_reuses_delivery", "self:tests/test_task_phases.py#test_run_reopens_delivered_task_and_uses_current_inputs", "self:tests/test_platform_review.py#test_closed_status_reads_pre_scenario_snapshot_as_records", "self:tests/test_task_phases.py#test_in_progress_legacy_snapshot_directs_to_start"]
tags: ["任务阶段", "历史记录", "交付", "内部快照"]
---
# 完成阶段先读交付事实，再决定是否载入方案

现象：同一分支上另一任务的文件让历史交付显示过期；已关闭任务的旧方案快照也被当前格式拒绝，恢复提示指向工具内部 JSON。

根因：流程先解析方案，再判断任务是否还在进行；状态读取和交付入口因此进入了当前目录的业务核对。内部快照与成员维护的 Markdown 共用修改文件的恢复指引。

修复与防护：任务阶段在方案解析前从平台状态、最终交付记录和后续任务活动确定，状态与交付入口共用。完成阶段保留历史事实；显式复核入口继续读取当前材料。内部快照读取失败时按对象类型引导成员用当前格式方案重新开工。阶段契约见工具约定，测试分别保留跨任务提交、重跑、旧快照与平台关闭的真实命令链。
