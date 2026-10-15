---
title: "技能指令文本受篇幅预算约束"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**", "self:skills/team-workflow/SKILL.md", "self:skills/team-workflow/references/matt-integration.md", "self:skills/team-workflow/references/platform.md", "self:scripts/check_release.py"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
guards: ["check:release"]
tags: ["篇幅预算", "指令", "发行检查"]
---
# 技能指令文本受篇幅预算约束

按 Unicode 字符计算，以下文本有上限，超出即发行失败：

- team-knowledge 的 SKILL.md 不超过 2,500；writing.md、migration.md 各不超过 3,000；lessons-from-history.md 不超过 1,500。
- team-workflow 的 SKILL.md、matt-integration.md、platform.md 各不超过 3,000。
- 两个技能各自的首次必读链不超过 8,000。

新增参考文档必须先在 `scripts/check_release.py` 中登记预算。超出预算时通过合并、删除或按需路由解决，不通过提高上限解决。业务验收标准等按需参考暂不计入，留待流程简化阶段处理。

## 依据
方案 M6：一个团队任务曾需要读约 129KB 指令，规则只增不减。
