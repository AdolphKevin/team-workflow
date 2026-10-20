---
title: "回放把隐藏条目算成已列出"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/brief.py", "self:scripts/replay_brief.py"]
source: ["self:docs/validation.md", "self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "1dd6080c171ffe505b252956217b33f7ea7489f7", "date": "2026-10-15"}}
tags: ["brief", "预算", "导航", "回放", "可见"]
---
# 回放把隐藏条目算成已列出

现象：导航超出篇幅时整节消失，回放却把隐藏条目计为已列出，掩盖了使用者读不到知识的问题。core 迁移试点的回放报告 19 个预期条目列出 15 个，输出中实际可见的只有 13 个。

根因：回放直接使用被选中的条目集合，没有区分完整正文、可见索引和未输出条目；省略提示也没有预留篇幅。

修复与防护：取用、篇幅与可见性约定见[方案 R2、R4](../../docs/proposals/2026-10-14-unified-redesign.md#r2-brief-选择算法)。守护测试构造导航放不下的输入，对照输出核对可见标记、遗漏分类和字符总数。

发现方法：让排序靠后的预期条目落在预算之外，直接核对命令输出与回放的遗漏清单；提醒行中的标签不能代替正文或索引行。

适用条件：修改知识选取、输出预算或回放统计时。
