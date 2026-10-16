---
title: "任务分支合并默认分支后，别人的改动被算成本任务的改动"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/knowledge.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:tests/test_task_base.py"]
verified: {"self": {"commit": "ebcc0f402744ddf13681fdb5651b92af5903300f", "date": "2026-10-15"}}
guards: ["self:tests/test_task_base.py#TaskBase"]
tags: ["base", "合并", "默认分支", "改动范围", "知识处置", "验收"]
---
# 任务分支合并默认分支后，别人的改动被算成本任务的改动

现象：Issue #5 的任务分支多次合并 main 后，业务验收报告 main 带来的四个文件“不在任何任务范围内”而拒绝；知识处置也会把 main 新增的知识算进本任务。

根因：改动范围与知识处置都对任务块中固定的 `base` 做差异；任务进行中合并默认分支，这些合并进来的改动也被计入。

修复与防护：以当前分支与远端默认分支（`refs/remotes/origin/HEAD`）的分叉点作为实际起点，与 PR 的改动口径一致；分叉点不包含记录的 base 或没有远端默认分支时，仍用记录的 base。任务块不变，不需要重新批准。

发现方法：在任务分支上合并默认分支后运行验收或交付，核对报告的改动文件是否只有本任务的。

适用条件：修改改动范围、知识处置或任何“本任务改了什么”的计算时。
