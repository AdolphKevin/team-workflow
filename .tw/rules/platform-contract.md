---
title: "平台读取按项目脚本契约维护"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/platform_script.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py", "self:skills/team-knowledge/scripts/tw_runtime/team/reviews.py", "self:skills/team-knowledge/scripts/tw_runtime/team/designs.py", "self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery_sequence.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-workflow/references/platform.md", "self:tests/test_approval_revision.py", "self:tests/test_change_request_flow.py", "self:tests/test_platform_review.py"]
source: ["self:skills/team-workflow/references/platform.md", "self:skills/team-workflow/references/designs.md", "self:skills/team-workflow/references/contracts.md", "self:docs/proposals/2026-10-15-issue-and-change-request-flow.md"]
verified: {"self": {"commit": "a63d72d22552bc0c1c036bed89f12e213328286c", "date": "2026-10-15"}}
guards: ["self:tests/test_platform.py#PlatformContract", "self:tests/test_approval_revision.py#ApprovalRevision", "self:tests/test_change_request_flow.py#ChangeRequestRecords", "self:tests/test_platform_review.py#PlatformReview", "check:unit", "check:release"]
tags: ["平台", "脚本", "契约", "持续集成", "来源", "批准", "评审"]
---
# 平台读取按项目脚本契约维护

修改平台调用、任务读取、批准或评审来源核对时，先读[平台契约](../../skills/team-workflow/references/platform.md)及
[批准与评审约定](../../skills/team-workflow/references/contracts.md)，按守护测试核对正常与拒绝路径。
分节批准见[分节方案](../../skills/team-workflow/references/designs.md)。字段与判定只在原文维护，本条不复制。

## 依据
已批准方案第 3、6、7、12 节；任务元数据和来源归属字段保留已有核查，独立于仅供存档的原始响应。
