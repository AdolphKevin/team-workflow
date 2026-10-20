---
title: "方案范围与简报路径语义不同，开工失败或漏读知识"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/repo_paths.py", "self:skills/team-knowledge/scripts/tw_runtime/globs.py", "self:skills/team-knowledge/scripts/tw_runtime/brief.py", "self:skills/team-knowledge/scripts/tw_runtime/team/commands.py", "self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/designs.py", "self:scripts/replay_brief.py"]
source: ["self:docs/validation.md", "self:docs/proposals/2026-10-14-unified-redesign.md", "self:skills/team-workflow/references/designs.md"]
verified: {"self": {"commit": "550f4c9ace5ed9580d65f17c17514a0bd8f5fd78", "date": "2026-10-15"}}
tags: ["scope", "路径", "目录", "仓库根", "start", "接续", "简报", "漏读"]
---
# 方案范围与简报路径语义不同，开工失败或漏读知识

现象：范围写 `.` 时首次开工和接续开工失败；写 `tests` 等目录时命令成功，但简报悄悄漏读该目录通配符范围下的知识。`./app.py` 与 `app.py` 还会被误判为范围不一致。

根因：两套路径语义并存。方案范围按目录前缀解释，简报只按具体路径处理，glob 匹配只有一个方向；任务范围核对又比较原始字符串。

修复与防护：范围、任务路径与查询共用规范化和前缀判断；简报按模式与目录是否重叠选取。仓库根、绝对查询路径和守护测试的精确匹配规则见[方案 R2](../../docs/proposals/2026-10-14-unified-redesign.md#r2-brief-选择算法)，任务范围见[分节方案](../../skills/team-workflow/references/designs.md)。守护测试经本地及平台任务入口核对首次开工、接续、简报实际条目和回放，防止仅看退出码遗漏知识缺失。

发现方法：修复前复现报告同时检查命令结果与简报内容；单独验证 `.`、目录、等价路径和范围外路径。

适用条件：修改任务范围、路径规范化、简报匹配或开工与接续的知识读取时。
