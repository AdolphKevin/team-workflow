---
title: "评审记录过问题的任务，收尾说明永远生成不了"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/coordination.py", "self:skills/team-knowledge/scripts/tw_runtime/team/delivery.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:docs/validation.md"]
verified: {"self": {"commit": "2550d9348ec882080002b5dc9a2371f809bd5194", "date": "2026-10-16"}}
guards: ["self:tests/test_close_note.py#test_review_findings_are_carried_into_the_close_note"]
tags: ["收尾说明", "已知问题", "评审", "交付"]
---
# 评审记录过问题的任务，收尾说明永远生成不了

现象：Issue #5 的评审记录了 Q1–Q3，均已解决；交付生成收尾说明时报 “Known issue disappeared: Q1”。

根因：交付要求收尾说明保留评审中的全部问题及其处置，但收尾说明草稿只从平台上的方案、交接和进度记录收集问题，没有带上评审的问题。模拟任务的评审没有问题，所以一直没暴露。

修复与防护：生成收尾说明时把评审的问题一并写入，其处置仍按原规则核对。

发现方法：评审中记录至少一个问题（即使已解决），走到交付。

适用条件：修改交接、收尾说明的问题清单，或改变已知问题的来源时。
