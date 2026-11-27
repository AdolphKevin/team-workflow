---
title: "brief 先保证候选条目可见再分配全文，关联只用于带出条目"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/brief.py", "self:skills/team-knowledge/scripts/tw_runtime/textmatch.py"]
source: ["self:docs/proposals/2026-11-04-field-feedback.md", "self:docs/proposals/2026-11-27-knowledge-root-and-index-first.md"]
verified: {"self": {"commit": "b9ad58184ab11dc29de1f1e01d3cf54c18171770", "date": "2026-11-27"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-11-P01", "self:docs/sop/tw-knowledge-only.yaml#SOP-11-P02", "self:docs/sop/tw-knowledge-only.yaml#SOP-20-P01", "self:docs/sop/tw-knowledge-only.yaml#SOP-20-P02", "self:docs/sop/tw-knowledge-only.yaml#SOP-20-P05"]
tags: ["brief", "排序", "关联", "打平", "索引", "可见", "全文"]
related: ["decisions/2026-11-27-brief-index-first.md"]
---
# brief 先保证候选条目可见再分配全文，关联只用于带出条目

现象：代理用到的知识已被选中，却排在后面，既没有全文也不在索引里；全文位置给了只因常见词或关联数量靠前的条目。代理随后改用 grep 逐个查词。

根因：预算先给全文，放哪几条由字面匹配和打平规则决定。打平规则每换一种，排错的方式也换一种：先是关联理由计入信号数，后是同分按标签字母序、常见词与少见词同分。

修复与防护：索引先于全文分配篇幅，全文只给直接命中的条目，见[决策](../decisions/2026-11-27-brief-index-first.md)。层级与路径具体度相同时按词语得分排序，本仓先于共享仓；关联只用于带出条目。守护场景在失败当时的快照上回放真实查询，并构造多条关联、常见词与少见词、本仓与共享仓的对照。

发现方法：同时核对目标条目的排名、索引可见标记、字符预算，以及截取输出前 60 行后是否还在；选中集合中存在条目只说明进入了候选范围。

适用条件：调整 brief 的选取、排序、关联扩展或篇幅分配时。

## 出现记录
- 2026-10-30：某多仓项目的 AI 服务仓回放三条任务查询，相关教训排在第 28、11、29 位，其中两次没有出现在正文或索引中；当时排序把关联理由计入信号数
- 2026-11-26：同一项目的核心服务仓与 AI 服务仓，一次会话的 6 条开工查询对应 8 个目标条目，全文 0 个、不可见 4 个；同分按条目标签字母序，共享仓条目占满全文位置
