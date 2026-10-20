---
title: "方案文件随任务提交，却被算成越界改动"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/design_files.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:docs/validation.md"]
verified: {"self": {"commit": "84aa206ff361d4673e0d2919a21b73bb7318b43f", "date": "2026-10-16"}}
tags: ["方案", "任务范围", "改动范围", "验收", "交付"]
---
# 方案文件随任务提交，却被算成越界改动

现象：文档要求先提交方案文件，验收却报方案文件“不在任何任务范围内”而拒绝，只能修订方案、重新批准、重跑检查。Issue #5 靠把方案文件写进 T3 的范围绕过；独立试用者照文档操作时再次遇到。

根因：改动范围把任务分支上的所有文件都当作实现改动，没有区分随任务提交的方案原文。

修复与防护：文件头 `design`、`task` 与本任务方案相同的 Markdown 不计入改动范围；其他方案或普通文档仍须落在任务范围内。按内容识别，本地与平台任务、方案换路径都适用。经 AdolphKevin 确认。

发现方法：把方案提交到仓库目录（不放在 `.tw/local/`），走完开工、检查、评审和验收。

适用条件：修改改动范围的计算，或改变方案文件的存放与识别方式时。
