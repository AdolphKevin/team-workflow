---
title: "场景粒度没有定义、完成标准落在测试上，主流程始终没有在真实项目上验收"
scope: ["self:skills/team-workflow/SKILL.md", "self:skills/team-workflow/references/business-acceptance.md", "self:skills/team-workflow/references/scenarios.md", "self:skills/team-workflow/references/team-delivery.md", "self:skills/team-workflow/references/test-capability.md", "self:skills/team-knowledge/scripts/tw_runtime/team/scenario_rounds.py", "self:skills/team-knowledge/scripts/tw_runtime/team/scenario_acceptance.py"]
source: ["self:docs/proposals/2026-10-20-verification-tiers.md"]
verified: {"self": {"commit": "8ff33f577f1a2562bf0e131c8b2d8d4d5b0f722f", "date": "2026-10-20"}}
guards: ["self:docs/sop/tw-tier-1.yaml#SOP-03-P01", "self:docs/sop/tw-tier-1.yaml#SOP-02-P01"]
tags: ["场景粒度", "用例集", "分段验收", "场景回归", "沿用", "文档膨胀", "测试膨胀"]
---
# 场景粒度没有定义、完成标准落在测试上，主流程始终没有在真实项目上验收

现象：2026-10-19 至 10-20 按 tw 流程开发 SOP 看板约 16 小时，10 个需求中 7 个评为复杂，各由测试代理写 51–85 条用例，场景合计约 500 条；方案与场景文件 597KB，多于产品代码 357KB；测试约 12,400 行，是产品代码的两倍。导出编号格式、换行符统一、YAML 错误的行列号都写成了场景。任务按页面、队列、执行等技术层拆分，主流程到会话结束仍未在真实项目上接通；实现每交回一段重跑约 20 分钟的全套测试。

根因：标准没有定义什么内容属于场景，细节用例都成了场景；用例集按复杂度触发、规模没有边界；“可独立验收”的拆分没有指向业务链路；完成标准落在测试上——每个问题先写失败测试、验收后沉淀为仓内测试、整体交付以自动回归为条件，开发时间花在与业务结果无关的测试上，交付产物本身没有被验收。

修复与防护：需求以最终交付产物经 SOP 场景验收，开发中不产出单元、接口与集成测试（[场景粒度](../../skills/team-workflow/references/business-acceptance.md#场景粒度)）。场景只写业务流程，十几条，细节并入所属流程场景的预期；用例集只覆盖主流程。主需求沿业务链路分段，第一段打通最薄的端到端路径，每段完成即验收。产品变化后已通过场景待判定，受影响的重跑，不受影响的用 `scenarios carry` 写明理由沿用；整体交付不再以自动回归为条件，`checks` 可以为空。

区分细节、反向与新场景按前置状态：前置状态相同、只差取值或时限是细节；前置状态相同、业务结果失败是反向；前置状态不同是新场景，属于加深时放后续段。TW-TIER-1 的 SOP-03 曾连续五轮各在一个边界失败（输入校验、第一段带加深、超时、写法位置、加深被当细节），每轮补一句措辞只是把边界移到下一处，换成这一条定义后细节与加深才同时归位。

发现方法：评审方案时看场景总数与各节点数，抽查需要列举字段或取值才能说清的场景；看实施任务节第一段的起点与终点是否跨越整条链路；看交接是否要求写测试。

适用条件：写方案、导入用例、拆分任务、安排验收或产品变化后的回归时。
