---
title: "新增强制规则要有真实失败案例或验收要求，纠正写在概念的定义处"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**", "self:skills/team-knowledge/scripts/tw_runtime/check.py", "self:skills/team-knowledge/scripts/tw_runtime/entries.py"]
source: ["https://github.com/AdolphKevin/team-workflow/commit/a0bc686", "https://github.com/AdolphKevin/team-workflow/commit/40ffdae", "https://github.com/AdolphKevin/team-workflow/commit/d55d892", "https://github.com/AdolphKevin/team-workflow/commit/41b1a5a", "https://github.com/AdolphKevin/team-workflow/commit/e117f8b", "https://github.com/AdolphKevin/team-workflow/commit/f51c1b9", "self:docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md"]
verified: {"self": {"commit": "ca9d1f43664dc227f0fea0bf55c9c6ccbbb5e418", "date": "2026-11-08"}}
guards: ["self:scripts/check_release.py#knowledge_checks", "self:scripts/release_text_rules.py#RULES"]
tags: ["强制规则", "失败案例", "规则膨胀", "篇幅", "指令", "反复", "补丁话术", "否定句", "重复定义"]
related: ["rules/instruction-budgets.md"]
---
# 新增强制规则要有真实失败案例或验收要求，纠正写在概念的定义处

修改技能入口、参考文档，或在运行时增加报错与拒绝路径时：

- 新增强制规则指向真实失败案例或验收要求；其余提议交用户决定。
- 放弃的规则连同理由写进相关决策的“放弃过的做法”。
- 纠正写在概念的定义处，用肯定句；同一概念只在一个文件定义，其他文件链接过去。
- 契约只写现行行为，版本差异交给 git 历史和决策。
- 指令篇幅受 `rules/instruction-budgets.md` 的预算约束。

## 依据

每暴露一个问题就追加一条强制规则，既没有篇幅上限，也不记录删掉规则的理由，同样的规则会被重新加回；纠正写在误读发生的位置，概念本身从未在一处正面定义，一个概念出现在几个文件里，纠正就补几遍。CS 的 SKILL.md 曾从 8KB 涨到 38KB，团队参考文档到 102KB，一个团队任务要读约 129KB 指令。

发现方法：发行检查超出预算即失败；评审时看新增规则是否附带案例，看新增句子是否在纠正别处已定义的概念。

## 出现记录
- 2026-10-14：d55d892 删除 10-11 由 a0bc686 加入的 S0–G3 阶段流程与 adopt 命令，同日 41b1a5a 又加回 adopt；40ffdae 取消评审记录的评论作者核对
- 2026-10-15：e117f8b 撤销“平台评审人须不同于变更作者”，这条规则没有失败案例，用户也从未提出
- 2026-10-16：盘点两个技能的 23 份文档，有 8 处“和上一版的差别”、20 余处“工具不做某事”、20 余处“X 不代表 Y”、10 处“Y 不会使 X 失效”，收尾说明的适用条件原样写在 4 个文件里；f51c1b9 改为在定义处正面陈述
