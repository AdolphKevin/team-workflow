---
name: team-workflow
description: 在已初始化独立 CS 的项目中开展团队任务：评估、方案评审、实施交接、验证和知识回写，并选择所需 MATT 方法。直接调用 MATT 仍保持轻量。
---

# 团队任务与开发方法

先读[CS 接入约定](references/matt-integration.md)。从本入口开始的新任务默认进入团队流程，
已有任务沿用其格式、批准、职责和授权。直接调用 MATT 不创建团队材料；团队任务切换方法
仍保留原流程要求。

## 开始与接手

1. 读取 CS 登记原文与相关经验，确认真实需求、范围和验证入口。已有任务用 `resume`
   读取共享材料；新任务形成简短评估和分节方案后用 `prepare` 汇总，并实际阅读开工简报。
2. 分别记录复杂度、风险、工作量、依据、未确定事项和所需能力；父方案与拆分任务分别评估。
   简单任务可保留同一条任务，中等、复杂任务按可独立验收的工作拆分。
3. 简单任务可先实施，再由具体评审人同时确认最终方案与代码；接口、数据库、权限等风险
   不改变这条路径，仍需对应验证。中等、复杂任务先取得具体评审人的方案确认。评审人不设
   固定职级或必须独立于实施者的限制；已有明确批准可直接记录依据，不再请求同一确认。
4. 已获批并指派后按方案实施。内容或约束实际偏离时，只重新评审受影响部分；批准范围内
   的修改不因涉及某种文件、接口或数据类型而暂停。待定业务选择只阻塞其影响的工作。

日常操作与收尾读[团队协作与交付](references/team-delivery.md)。首次接入读
[接入指南](references/onboarding.md)；写方案、批准或检查局部变化时读[分节方案](references/designs.md)；
调用工具时读[第四版命令与记录](references/contracts-v4.md)。旧阶段记录只按原任务约定处理，
新任务不套用旧版逐阶段评论和硬暂停规则。

## 按目标选择方法

只读取当前所需方法，保留用户已选择的方法、测试方式和实现安排。

| 当前目标 | 方法 |
| --- | --- |
| 澄清方案、形成规格或拆分任务 | [问题澄清](../matt-grilling/SKILL.md)、[规格](../matt-to-spec/SKILL.md)、[任务拆分](../matt-to-tickets/SKILL.md) |
| 实现已有需求或一组关联任务 | [实现](../matt-implement/SKILL.md)、[多任务实现](../matt-implement-spec/SKILL.md) |
| 定位故障或采用测试先行 | [诊断](../matt-diagnosing-bugs/SKILL.md)、[测试](../matt-tdd/SKILL.md) |
| 调整模块或领域概念 | [设计](../matt-codebase-design/SKILL.md)、[领域建模](../matt-domain-modeling/SKILL.md) |
| 审查改动或撰写 PR 说明 | [审查](../matt-code-review/SKILL.md)、[PR 说明](../matt-pr/SKILL.md) |
| 验证想法、调研或编写代理指引 | [原型](../matt-prototype/SKILL.md)、[调研](../matt-research/SKILL.md)、[代理写作](../matt-writing-for-agents/SKILL.md) |

用户要求代理工作环境复盘时使用[环境复盘](../matt-retro/SKILL.md)。普通收尾不自动增加复盘
或 CS 使用分析。多代理按实际需要与已有授权采用，不是团队流程的必经步骤。
