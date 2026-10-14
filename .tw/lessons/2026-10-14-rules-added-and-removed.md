---
title: "每遇到一个问题就加一条规则，规则反复增删、文本只增不减"
scope: ["self:skills/team-workflow/SKILL.md", "self:skills/team-workflow/references/**", "self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**"]
source: ["https://github.com/AdolphKevin/team-workflow/commit/a0bc686", "https://github.com/AdolphKevin/team-workflow/commit/40ffdae", "https://github.com/AdolphKevin/team-workflow/commit/d55d892", "https://github.com/AdolphKevin/team-workflow/commit/41b1a5a"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
guards: ["check:release"]
tags: ["规则膨胀", "篇幅", "指令", "反复"]
---
# 每遇到一个问题就加一条规则，规则反复增删、文本只增不减

现象：S0–G3 阶段流程加入 3 天后删除；“评论作者必须是评审人”加入后又取消；adopt 同一天被删除又加回。CS 的 SKILL.md 从 8KB 涨到 38KB，团队参考文档到 102KB，一个团队任务要读约 129KB 指令。

根因：每暴露一个问题就追加一条强制规则，既没有篇幅上限，也不记录删掉一条规则的理由，于是同样的规则会被重新加回。

修复与防护：发行检查强制指令篇幅预算（见 rules/instruction-budgets.md）；新增强制规则必须指向真实失败案例或验收要求；放弃的规则写进相关 decision 的“放弃过的做法”。

发现方法：发行检查超出预算即失败；评审时看新增规则是否附带案例。

适用条件：修改任何技能入口或参考文档时。
