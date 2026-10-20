---
title: "平台读取按项目脚本契约维护"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/platform_script.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py", "self:skills/team-knowledge/scripts/tw_runtime/team/reviews.py", "self:skills/team-knowledge/scripts/tw_runtime/team/designs.py", "self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery_sequence.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/init.py", "self:skills/team-workflow/references/platform.md", "self:skills/team-workflow/references/onboarding.md", "self:skills/team-knowledge/scripts/tw_runtime/team/design_markdown.py", "self:skills/team-knowledge/scripts/tw_runtime/team/design_files.py", "self:skills/team-knowledge/scripts/tw_runtime/team/records.py", "self:skills/team-knowledge/scripts/tw_runtime/team/contracts.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery.py", "self:skills/team-knowledge/scripts/tw_runtime/team/commands.py", "self:skills/team-knowledge/scripts/tw_runtime/team/starting.py", "self:skills/team-knowledge/scripts/tw_runtime/team/task_inputs.py", "self:skills/team-knowledge/scripts/tw_runtime/team/design_links.py", "self:skills/team-knowledge/scripts/tw_runtime/team/repairs.py", "self:skills/team-knowledge/scripts/tw_runtime/team/summary.py", "self:skills/team-knowledge/scripts/tw_runtime/team/status_records.py", "self:skills/team-knowledge/scripts/tw_runtime/team/issue_draft.py", "self:skills/team-workflow/references/coordination.md"]
source: ["self:skills/team-workflow/references/platform.md", "self:skills/team-workflow/references/onboarding.md", "self:skills/team-workflow/references/designs.md", "self:skills/team-workflow/references/contracts.md", "self:docs/proposals/2026-10-15-issue-and-change-request-flow.md", "self:docs/proposals/2026-10-15-markdown-designs.md", "self:docs/proposals/2026-10-15-acceptance-binding-and-flow-fixes.md", "self:docs/proposals/2026-10-16-owner-and-agent-close.md"]
verified: {"self": {"commit": "a55eb12a0a507b800e947f1ca90b625a7ae2b31b", "date": "2026-10-16"}}
guards: ["check:release"]
tags: ["平台", "脚本", "契约", "持续集成", "来源", "批准", "评审"]
---
# 平台读取按项目脚本契约维护

修改平台调用、任务读取、批准或评审来源核对时，先读[平台契约](../../skills/team-workflow/references/platform.md)及
[批准与评审约定](../../skills/team-workflow/references/contracts.md)，按守护测试核对正常与拒绝路径。
分节批准、当前验证写法与对账重启见[分节方案](../../skills/team-workflow/references/designs.md)。验收编号、待确认原因、默认批准范围、发布顺序及链接展示也在该页；字段与判定只在原文维护，本条不复制。
平台负责人与代理实施的收尾、同目录接续及历史对账草稿见[任务协作](../../skills/team-workflow/references/coordination.md)与[工具约定](../../skills/team-workflow/references/contracts.md)。

## 依据
平台流程方案第 3、4、6、7、12 节、Markdown 方案 v1.1 第 2、3、3.1 节及验收绑定方案第 2–7 节；守护测试另见 `test_verification_gaps.py`、`test_reconciliation.py`、`test_contracts.py`、`test_markdown_review.py`。任务元数据和来源归属核查独立于仅存档的原始响应。
