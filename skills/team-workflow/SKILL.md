---
name: team-workflow
description: 团队任务入口：方案评审、实施交接、业务验收、自动回归、每周质量复盘和知识更新。适用于新建任务、接手、变更方案及交付；项目知识由 team-knowledge 提供，独立调用 MATT 方法时保持轻量。
disable-model-invocation: true
---

# 团队任务与开发方法

先读[方法与知识约定](references/matt-integration.md)。命令都是 `tw team <命令>`，其中 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`；知识读写用 team-knowledge。切换 MATT 方法或恢复会话时，沿用当前任务的批准、验收和未决问题。团队任务、缺陷处理和每周质量复盘按[业务验收与质量改进标准](references/business-acceptance.md)执行；首次接入或项目缺少集成、E2E 入口时，先读[接入指南](references/onboarding.md)。

## 从需求到可实施

1. 运行 `tw team project` 核对配置、知识检查和安装。项目还有 `.codestable/` 或 `.team-workflow*` 时，先按 team-knowledge 的迁移指南迁移。结果为 `tool-modified` 或 `tool-defect` 时停止并报告，不修改已安装文件。
2. 用 `tw brief` 读取知识，读需求原文，先写清真实起点、角色操作、业务入口、结果、失败情形和验收负责人。调查相关的读取、修改、删除、引用替换、后台触发，以及谁产生数据、谁提交结果。再按可独立验收的工作拆分；主需求保留完整业务路径的独立验收。
3. 形成可评审的方案，分别评估复杂度、风险、工作量、依据和待定事项。简单任务用短方案，开发后合并评审；中等、复杂任务先取得具体评审人的确认。已有批准只按实际范围复用。Issue 还没有结构化任务块时，用 `issue-draft` 生成草稿交由用户发布。
4. **首次修改业务源码或派出实施代理前**，新任务运行 `prepare`，接手任务运行 `resume`，确认 `implementation_ready` 或 `ready_to_implement` 为真。Issue 已建、业务选择已确认，都不能替代这项核对。

范围、约束或跨服务责任变化时，只重审受影响的部分。代理交接须包含方案版本、实际批准、允许修改范围、验收和未决问题。

## 实施与交付

按[团队交付步骤](references/team-delivery.md)执行，命令细节见[工具约定](references/contracts.md)，方案指纹见[分节方案](references/designs.md)。

- 顺序为：实际验证与评审 → 业务验收 → 在同一分支更新 `.tw` 知识并通过 `tw check` → 交付报告写明知识处置 → 最终交付。
- 每个已知问题保留编号、影响范围、负责人和处置。接受限制或延期须写明确认人。
- 检查过期时只重跑过期的那一项。任务中断后先运行 `status --format text`，按下一步继续。
- 单人以 Issue 为任务时，最终 `verify` 给出收尾说明草稿；多人接力或跨仓任务仍发布实施交接。
- 回复分别说明检查通过、失败、未验证范围、业务验收和交付状态。实际通过需要原始运行或人工观察证据。

## 按目标选择方法

| 目标 | 方法 |
| --- | --- |
| 澄清、规格、拆分 | [问题澄清](../matt-grilling/SKILL.md)、[规格](../matt-to-spec/SKILL.md)、[拆分](../matt-to-tickets/SKILL.md) |
| 实现 | [实现](../matt-implement/SKILL.md)、[多任务实现](../matt-implement-spec/SKILL.md) |
| 故障与测试 | [诊断](../matt-diagnosing-bugs/SKILL.md)、[测试](../matt-tdd/SKILL.md) |
| 模块与领域 | [设计](../matt-codebase-design/SKILL.md)、[领域建模](../matt-domain-modeling/SKILL.md) |
| 审查与 PR | [审查](../matt-code-review/SKILL.md)、[PR](../matt-pr/SKILL.md) |
| 原型、调研、写作 | [原型](../matt-prototype/SKILL.md)、[调研](../matt-research/SKILL.md)、[代理写作](../matt-writing-for-agents/SKILL.md) |

用户要求环境复盘时使用[环境复盘](../matt-retro/SKILL.md)。
