---
title: "项目用出现记录追踪教训复发，满 3 个日期升级为规则，并定期复盘提交"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**", "self:skills/team-knowledge/scripts/tw_runtime/entries.py", "self:skills/team-knowledge/scripts/tw_runtime/check.py", "self:skills/team-knowledge/scripts/tw_runtime/brief.py", "self:skills/team-knowledge/scripts/tw_runtime/audit.py", "self:skills/team-knowledge/scripts/tw_runtime/init.py"]
source: ["self:docs/proposals/2026-11-08-lesson-loop.md", "https://github.com/yetone/magpie/blob/main/LESSONS.md"]
status: "accepted"
tags: ["出现记录", "出现次数", "复发", "升级为规则", "复盘", "做对的例子", "返工", "错题本", "magpie"]
related: ["rules/evidence-backed-rules.md"]
---
# 项目用出现记录追踪教训复发，满 3 个日期升级为规则，并定期复盘提交

tw 帮各项目在自己的 `.tw/` 中建立教训闭环，做法参考 magpie 的错题本：

- 教训标题写一句要遵守的做法；再次出现时在 `## 出现记录` 追加日期、证据与后果，次数取不同日期数；照着做对的提交写进 `## 做对的例子`。
- 教训出现满 3 个不同日期升级为 rule，经 PR 由用户确认；评审时以改动的文件读取知识，逐条核对规则。
- 技能提供定期复盘指南：按返工、不该合入、验证太粗三类回看提交，结果是只改知识的 PR，范围写在 PR 说明中。
- 运行时从出现记录计算次数：brief 在标题旁显示，check 校验格式并在满 3 次时警告，audit 列出反复出现的条目。读取沿用按任务与路径选取。

## 备选

- 文件头 `seen` 计数字段：计数与日期、证据分开写会不一致，不采用。
- 单独的代码规范文件：`rules/` 已是现行约束的位置，不采用。
- 复盘进度标记文件或配置字段：magpie 的 `reviewed-through` 停在 10-13 而复盘提交持续到 10-28，PR 说明已能给出下一次的起点，不采用。

## 后果

复发、升级与正面示例都写在条目正文，随 PR 评审；追加出现记录按改写条目对待，核对后更新 `verified`。复盘的节奏与执行者由各项目决定，工具提供格式检查与计数。

## 放弃过的做法

- brief 每次列出反复出现的条目标题，路径没有选中的也列出
  放弃原因：用户确认本设计帮助项目产生和维护教训，读取沿用按任务与路径选取（2026-11-08）
  重新考虑的条件：真实使用中反复出现的教训因路径未选中而被漏读
  来源：教训闭环方案第 4、7 节
  关键词：反复出现、固定列出、全文载入、LESSONS.md
- `tw review` 复盘辅助命令：列出范围内提交、疑似返工链与相关条目
  放弃原因：用户确认先用复盘指南在真实项目中试行，看清哪些步骤值得固化（2026-11-08）
  重新考虑的条件：复盘会话反复手工统计返工链，或漏配已有教训
  来源：教训闭环方案第 4、7 节
  关键词：tw review、复盘命令、返工链
- 按出现次数调整 brief 排序
  放弃原因：次数已显示在标题旁；排序改动会改变已验收的回放结果
  重新考虑的条件：反复出现的教训因排序靠后而被漏读
  来源：教训闭环方案第 4 节
  关键词：排序、出现次数、排名
