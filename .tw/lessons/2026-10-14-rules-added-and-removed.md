---
title: "每遇到一个问题就加一条规则，规则反复增删、文本只增不减"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**"]
source: ["https://github.com/AdolphKevin/team-workflow/commit/a0bc686", "https://github.com/AdolphKevin/team-workflow/commit/40ffdae", "https://github.com/AdolphKevin/team-workflow/commit/d55d892", "https://github.com/AdolphKevin/team-workflow/commit/41b1a5a", "self:docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:scripts/check_release.py#knowledge_checks", "self:scripts/release_text_rules.py#RULES"]
tags: ["规则膨胀", "篇幅", "指令", "反复", "补丁话术", "否定句", "重复定义"]
---
# 每遇到一个问题就加一条规则，规则反复增删、文本只增不减

现象：S0–G3 阶段流程加入 3 天后删除；“评论作者必须是评审人”加入后又取消；adopt 同一天被删除又加回。CS 的 SKILL.md 从 8KB 涨到 38KB，团队参考文档到 102KB，一个团队任务要读约 129KB 指令。合并重构后篇幅降下来，同样的习惯换了形态：2026-10-16 盘点两个技能的 23 份文档，有 8 处“和上一版的差别”、20 余处“工具不做某事”、20 余处“X 不代表 Y”、10 处“Y 不会使 X 失效”，收尾说明的适用条件原样写在 4 个文件里。

根因：每暴露一个问题就追加一条强制规则，既没有篇幅上限，也不记录删掉一条规则的理由，于是同样的规则会被重新加回。纠正写在误读发生的位置，而概念本身从未在一处正面定义；一个概念出现在几个文件里，纠正就补几遍。

修复与防护：发行检查强制指令篇幅预算（见 rules/instruction-budgets.md）；新增强制规则必须指向真实失败案例或验收要求；放弃的规则写进相关 decision 的“放弃过的做法”。纠正写在概念的定义处，用肯定句；同一概念只在一个文件定义，其他文件链接过去；契约只写现行行为，版本差异交给 git 历史和 decision。

发现方法：发行检查超出预算即失败；评审时看新增规则是否附带案例，看新增句子是否在纠正某个别处已定义的概念。

适用条件：修改任何技能入口或参考文档时。
