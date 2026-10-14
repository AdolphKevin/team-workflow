---
title: "删除旧记录时，它承担的核对被一起删掉"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/delivery.py", "self:skills/team-knowledge/scripts/tw_runtime/team/knowledge.py"]
source: ["self:CHANGELOG.md", "self:docs/validation.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
guards: ["self:tests/test_delivery.py#test_final_delivery_needs_this_tasks_current_acceptance_record", "self:tests/test_unified_team.py#test_listed_knowledge_must_be_changed_by_this_task"]
tags: ["最终交付", "业务验收", "知识处置", "删除桥接", "删除断言"]
---
# 删除旧记录时，它承担的核对被一起删掉

现象：阶段 2 删除 CS 的知识完成记录之后，出现了两个问题，均由独立评审发现（F1、F2）。
- 最终交付不再要求业务验收记录：从未验收、夹具身份已经改变的任务，也能得到 `delivery_complete`；收尾说明引用的是核查当场生成的“验收”文件。
- 交付报告列出本任务没有改动过的知识文件，核查也能通过。
测试中“收尾说明引用真实验收记录”的断言也随之被删除。

根因：旧的知识完成记录顺带强制了“先有当前的业务验收，交付沿用验收时的环境”。删除它时只看了它的主要用途，没有逐项列出它承担的核对。模板用 git 差异算出改动的知识文件，核查却没有用同一算法比对。

修复与防护：交付报告的 `acceptance` 引用 `verify --phase acceptance` 的产物，核查它属于本任务，且验收后任务、方案章节、源码，以及执行、评审、批准材料都没有变化；`knowledge.files` 必须正好列出相对任务 `base` 改动的知识文件。修复过程中又出现过两次偏差：先是没有绑定执行材料（F7），随后又把内容相同的副本也判为变化（F10）。

发现方法：删除记录、命令或字段之前，列出读取它的每一处核查和断言，逐项决定迁到哪里或明确放弃；删除测试断言时写明理由。

适用条件：删除或合并记录格式、命令、桥接模块的改动。
