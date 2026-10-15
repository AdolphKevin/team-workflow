---
title: "平台读取按项目脚本契约维护"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/platform_script.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-workflow/references/platform.md"]
source: ["self:skills/team-workflow/references/platform.md", "self:docs/proposals/2026-10-15-issue-and-change-request-flow.md"]
verified: {"self": {"commit": "8b536d5c3fa7cd8ce0100f47d1bc3d86618394ac", "date": "2026-10-15"}}
guards: ["self:tests/test_platform.py#PlatformContract", "check:unit", "check:release"]
tags: ["平台", "脚本", "契约", "持续集成", "来源"]
---
# 平台读取按项目脚本契约维护

修改平台调用、任务读取或持续集成来源核对时，先读[契约原文](../../skills/team-workflow/references/platform.md)，并按守护测试核对正常与拒绝路径。字段、错误和凭据约定只在原文维护，本条不复制。

## 依据
已批准方案第 3 节；任务元数据和来源归属字段保留已有核查，独立于仅供存档的原始响应。
