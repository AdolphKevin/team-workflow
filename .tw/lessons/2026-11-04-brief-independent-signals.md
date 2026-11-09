---
title: "brief 排序打平只比较独立信号数，关联只用于带出条目"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/brief.py"]
source: ["self:docs/proposals/2026-11-04-field-feedback.md"]
verified: {"self": {"commit": "ca9d1f43664dc227f0fea0bf55c9c6ccbbb5e418", "date": "2026-11-08"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-11-P01", "self:docs/sop/tw-knowledge-only.yaml#SOP-11-P02"]
tags: ["brief", "排序", "关联", "打平", "独立信号"]
---
# brief 排序打平只比较独立信号数，关联只用于带出条目

现象：2026-10-30，某多仓项目的 AI 服务仓回放三条任务查询时，相关教训排在第 28、11、29 位，其中两次未出现在正文或索引中。

根因：层级与路径具体度相同时，排序把关联理由也算进信号数；关联很多条目的决策因此挤到前面，独立命中的强弱被关联数量覆盖。

修复与防护：打平按去掉关联理由后的独立信号数比较。关联仍用于带出条目；守护场景构造多条关联与单个词组命中的对照，并在失败时的快照回放真实查询。

发现方法：同时核对目标条目的排名、正文或索引可见标记以及字符预算，选中集合中存在条目只说明进入了候选范围。

适用条件：调整 brief 排序、关联扩展或篇幅取舍时。
