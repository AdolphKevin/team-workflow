---
title: "收尾说明重新核对了验收已经取代的失败运行"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:docs/validation.md"]
verified: {"self": {"commit": "3cb5efe02b940e97b15781cb085a572185dbf18a", "date": "2026-10-16"}}
tags: ["收尾说明", "运行记录", "取代", "验收", "交付"]
---
# 收尾说明重新核对了验收已经取代的失败运行

现象：Issue #5 的 unit 检查在修复测试前失败过一次，之后重跑通过。业务验收选用了通过的那次并通过，生成收尾说明时却报 “Original check did not pass”，交付停在最后一步。

根因：业务验收按检查选用最新的有效运行，并在 `superseded_execution` 中记录被取代的运行；收尾说明核对验收记录时，却把报告中列出的每一次运行都重新核对一遍，包括已被取代的失败运行。

修复与防护：核对验收记录时跳过其 `superseded_execution` 中列出的运行结果，与业务验收的选用口径一致。

发现方法：一次检查失败、修复后重跑通过，再走完验收和交付。

适用条件：修改运行选用、验收记录或交接、收尾说明的证据核对时。
