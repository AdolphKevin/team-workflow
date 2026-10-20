---
title: "场景粒度没有定义，细节用例都成了经真实入口执行的场景"
scope: ["self:skills/team-workflow/SKILL.md", "self:skills/team-workflow/references/business-acceptance.md", "self:skills/team-workflow/references/scenarios.md", "self:skills/team-workflow/references/team-delivery.md", "self:skills/team-workflow/references/onboarding.md", "self:skills/team-knowledge/scripts/tw_runtime/team/scenarios.py", "self:skills/team-knowledge/scripts/tw_runtime/team/scenario_acceptance.py"]
source: ["self:docs/proposals/2026-10-20-verification-tiers.md"]
verified: {"self": {"commit": "e22349cf2024ec9c9ce7cf60b819ffb4842a4c00", "date": "2026-10-20"}}
tags: ["场景粒度", "用例集", "分段验收", "快速检查", "文档膨胀"]
---
# 场景粒度没有定义，细节用例都成了经真实入口执行的场景

现象：2026-10-19 至 10-20 按 tw 流程开发 SOP 看板约 16 小时，10 个需求中 7 个评为复杂，各由测试代理写 51–85 条用例，场景合计约 500 条；方案与场景文件 597KB，多于产品代码 357KB。导出编号格式、换行符统一、YAML 错误的行列号都写成了场景。任务按页面、队列、执行等技术层拆分，主流程到会话结束仍未在真实项目上接通；实现每交回一段重跑约 20 分钟的全套检查。

根因：标准只写了场景的字段与每节点正反向，没有定义什么内容属于场景，用例覆盖又只能用场景；用例集按复杂度触发、规模没有边界；“可独立验收”的拆分没有指向业务链路；检查没有快慢之分。

修复与防护：[场景粒度](../../skills/team-workflow/references/business-acceptance.md#场景粒度)是唯一定义：业务流程与业务失败写场景，十几条；规则、格式、边界与文案写测试并登记为检查。用例集只覆盖主流程，配对的 `covered` 可用 `checks` 引用测试用例，`accept` 按场景回归的规则核对。主需求沿业务链路分段，第一段打通最薄的端到端路径，每段完成即验收；每段交回运行相关测试与快速检查，场景验收前运行全部检查。`scenarios check` 输出场景数，数量由评审判断。

发现方法：评审方案时看场景总数与各节点数，抽查需要列举字段或取值才能说清的场景；看实施任务节第一段的起点与终点是否跨越整条链路。

适用条件：写方案、导入用例、拆分任务或安排实施中的检查时。
