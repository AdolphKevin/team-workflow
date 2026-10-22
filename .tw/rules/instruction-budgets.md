---
title: "技能指令文本受篇幅预算约束"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**", "self:scripts/check_release.py"]
source: ["self:docs/proposals/2026-10-22-knowledge-only.md", "self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:scripts/check_release.py#knowledge_checks"]
tags: ["篇幅预算", "指令", "发行检查"]
---
# 技能指令文本受篇幅预算约束

按 Unicode 字符计算，team-knowledge 的 SKILL.md 上限 2,500；writing.md、migration.md 各 3,000；lessons-from-history.md 为 1,500；首次必读链上限 8,000。超出即发行失败。

新增参考文档先在 `scripts/check_release.py` 登记预算。超出预算时合并、删除重复内容或按需引用；新增强制规则须对应真实失败案例或验收要求。

## 依据

合并方案 M6 记录了单次任务需读约 129KB 指令的失败；知识库方案保留知识预算，移除团队指令及其预算。
