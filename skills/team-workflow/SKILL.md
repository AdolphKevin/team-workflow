---
name: team-workflow
description: 在 CS 已安装且项目已完成知识初始化的前提下，按当前目标选择 MATT 开发方法；项目要求或用户需要时，接入团队交接、验证结果核对和跨仓交付工具。
---

# MATT 方法与可选团队工具

先读取[CS 接入约定](references/matt-integration.md)，保留用户已经选择的方法和授权。
MATT 负责开发方法，项目知识统一交给 CS。普通方法调用无需创建团队配置、任务文件或交付报告。

## 按目标选择方法

只读取当前任务需要的方法，直接调用某个 MATT 技能也适用相同的 CS 前提。

| 当前目标 | 方法 |
| --- | --- |
| 澄清方案、形成规格或拆分任务 | [问题澄清](../matt-grilling/SKILL.md)、[规格](../matt-to-spec/SKILL.md)、[任务拆分](../matt-to-tickets/SKILL.md) |
| 实现已有需求或一组关联任务 | [实现](../matt-implement/SKILL.md)、[多任务实现](../matt-implement-spec/SKILL.md) |
| 定位故障或采用测试先行 | [诊断](../matt-diagnosing-bugs/SKILL.md)、[测试](../matt-tdd/SKILL.md) |
| 调整模块设计或领域概念 | [设计](../matt-codebase-design/SKILL.md)、[领域建模](../matt-domain-modeling/SKILL.md) |
| 审查改动或撰写 PR 说明 | [审查](../matt-code-review/SKILL.md)、[PR 说明](../matt-pr/SKILL.md) |
| 验证设计想法、调研资料或编写代理指引 | [原型](../matt-prototype/SKILL.md)、[调研](../matt-research/SKILL.md)、[代理写作](../matt-writing-for-agents/SKILL.md) |

用户要求走完整流程、按阶段推进需求交付，或项目规则要求时，读取[阶段流程](references/stage-flow.md)：
它规定阶段、确认关卡、关闭条件和中断后的子代理恢复方式。默认不启用。

用户要求代理工作环境复盘，或当前任务明确包含环境改进时，使用[环境复盘](../matt-retro/SKILL.md)。
普通开发任务结束按 CS 完成知识记录，不自动增加环境复盘或 CS 使用分析。

## 按需使用团队工具

项目约定或用户明确需要交接、核对验证结果、跨仓交付时，读取[团队协作与交付](references/team-delivery.md)。
这些工具继续执行完整核验要求；采用何种开发方法不决定是否启用它们。
并行源码工作复用独立检出目录，进度独立追加、交接由负责人确认；生成材料使用工具
返回的任务和请求路径。共享配置只保存团队规则，本机位置与运行材料均被 Git 忽略。
