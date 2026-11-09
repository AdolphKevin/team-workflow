---
title: "brief 逐条写明选中依据，并说明任务路径的直接覆盖情况"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/brief.py"]
source: ["self:docs/proposals/2026-11-04-field-feedback.md"]
verified: {"self": {"commit": "ca9d1f43664dc227f0fea0bf55c9c6ccbbb5e418", "date": "2026-11-08"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-08-P01", "self:docs/sop/tw-knowledge-only.yaml#SOP-08-N01", "self:docs/sop/tw-knowledge-only.yaml#SOP-08-N02", "self:docs/sop/tw-knowledge-only.yaml#SOP-08-P02", "self:docs/sop/tw-knowledge-only.yaml#SOP-08-P03"]
tags: ["brief", "选中依据", "覆盖说明", "路径", "间接命中"]
---
# brief 逐条写明选中依据，并说明任务路径的直接覆盖情况

现象：某多仓项目的一次页面修改在核心服务仓读到三条无关知识：一条只因任务含“验收”而选中，两条由它关联带出；文本没有说明相关程度，指向另一仓库的路径又被拒绝。

根因：条目被选中与知识覆盖所改路径是两件事。选中依据只放在 JSON 中，文本只展示结论，使用者看不到词组与关联带来的间接命中。

修复与防护：文本同时展示逐条选中依据和任务覆盖计数，区分路径等直接信号与词组、关联等间接信号。其他仓库路径报告知识状态和命令；本仓选择只用本仓路径。

发现方法：以含通用词组、路径没有知识覆盖以及未给路径的真实命令对照，核对覆盖说明、逐条依据与其他仓库状态。

适用条件：修改 brief 选取、文字输出或仓库外路径处理时。
