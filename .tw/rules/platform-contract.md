---
title: "平台读取按项目脚本契约维护"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/platform_script.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py", "self:skills/team-knowledge/scripts/tw_runtime/team/reviews.py", "self:skills/team-knowledge/scripts/tw_runtime/team/designs.py", "self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery_sequence.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/init.py", "self:skills/team-workflow/references/platform.md", "self:skills/team-workflow/references/onboarding.md", "self:tests/test_tw_commands.py", "self:tests/test_approval_revision.py", "self:tests/test_change_request_flow.py", "self:tests/test_platform_review.py", "self:skills/team-knowledge/scripts/tw_runtime/team/design_markdown.py", "self:skills/team-knowledge/scripts/tw_runtime/team/design_files.py", "self:skills/team-knowledge/scripts/tw_runtime/team/records.py", "self:tests/test_markdown_design.py", "self:tests/test_markdown_records.py", "self:tests/test_hidden_records.py", "self:tests/test_markdown_readability.py"]
source: ["self:skills/team-workflow/references/platform.md", "self:skills/team-workflow/references/onboarding.md", "self:skills/team-workflow/references/designs.md", "self:skills/team-workflow/references/contracts.md", "self:docs/proposals/2026-10-15-issue-and-change-request-flow.md", "self:docs/proposals/2026-10-15-markdown-designs.md"]
verified: {"self": {"commit": "14fa1a775d434a404f084c19a8e6426f8aa3fbd7", "date": "2026-10-15"}}
guards: ["self:tests/test_platform.py#PlatformContract", "self:tests/test_tw_commands.py#Init", "self:tests/test_approval_revision.py#ApprovalRevision", "self:tests/test_change_request_flow.py#ChangeRequestRecords", "self:tests/test_platform_review.py#PlatformReview", "self:tests/test_markdown_design.py#MarkdownDesignCases", "self:tests/test_markdown_records.py#MarkdownRecordCases", "self:tests/test_hidden_records.py#HiddenRecordCases", "self:tests/test_markdown_readability.py#MarkdownReadabilityCases", "check:unit", "check:release"]
tags: ["平台", "脚本", "契约", "持续集成", "来源", "批准", "评审"]
---
# 平台读取按项目脚本契约维护

修改平台调用、任务读取、批准或评审来源核对时，先读[平台契约](../../skills/team-workflow/references/platform.md)及
[批准与评审约定](../../skills/team-workflow/references/contracts.md)，按守护测试核对正常与拒绝路径。
分节批准见[分节方案](../../skills/team-workflow/references/designs.md)。原文书写、正文规范化、标签转义及平台隐藏记录格式均在该页；字段与判定只在原文维护，本条不复制。

## 依据
平台流程方案第 3、4、6、7、12 节及 Markdown 方案 v1.1 第 2、3、3.1 节；任务元数据和来源归属字段保留已有核查，独立于仅供存档的原始响应。
