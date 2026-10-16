---
name: team-workflow
description: 团队任务入口：方案评审、实施交接、场景验收、自动回归与知识更新。适用于新任务、接手、方案变更和交付；独立调用 MATT 方法保持轻量。
disable-model-invocation: true
---

# 团队任务与开发方法

先读[方法与知识约定](references/matt-integration.md)。接手时沿用有效批准、验收和未决问题。验收、回归、缺陷及每周复盘按[业务验收标准](references/business-acceptance.md)；首次接入或缺测试入口时读[接入指南](references/onboarding.md)，按其中的项目平台脚本与验收入口接入。

`tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`；`--root`、`--repository` 可写在团队子命令前后，参数见 `--help`。工具与成员的分工见[工具做什么](references/contracts.md#工具做什么)。

## 五步交付

用 `tw team project` 核对配置、知识与安装，用 `tw brief` 读知识和需求原文，查明入口、范围、失败情形及验收负责人，按可独立验收的工作拆分，主需求覆盖完整业务。安装被修改或工具报缺陷时，报告缺陷并停在这里。

方案评估复杂度、风险、工作量与待定事项，按[批准路径](references/designs.md#内容与依赖)推进：简单任务开发后合并评审；中等、复杂任务先获具名批准，可用 `approval-draft --reviewer <姓名> --mode plan` 生成记录。验收节引用场景文件中的节点，写法见[场景指南](references/scenarios.md)。

1. **start**：`tw team start --task <任务文件> --design <方案> [--approval <批准>]`，之后用 `--task <身份>`（任务编号或完整 Issue 地址）。实施或委派前读简报、确认实施条件。
2. **run**：`tw team run --task <身份>` 执行登记检查；失败时保留原始输出，聚焦补跑。
3. **场景验收**：未参与实施的执行者经声明的验收入口，逐条执行 `tw team scenarios pending --task <身份>` 列出的场景，用 `scenarios submit` 登记结果。复杂任务先用 `scenarios import-cases` 导入测试同事的用例，按语义写配对后运行 `scenarios coverage`。
4. **评审**：场景验收完成后 `run` 生成 `review.md`。未参与实施的人填写姓名、规范与需求及逐项验收的结论、理由、问题处置；简单任务需合并批准时填“批准方案与代码：是”。本地用 `review --task <身份> --submit`；配置平台时，评审人把完整 Markdown 提交到变更请求，`deliver` 采用较新的一份，也可 `review --task <身份> --from-platform`。
5. **deliver**：`tw team deliver --task <身份> --reason <理由>` 依次完成业务验收、知识处置和最终核查；失败时停在对应步骤并给出下一步，重试复用有效记录。要更新知识时，先 `tw team accept --task <身份>`，在同一分支更新 `.tw/` 并运行 `tw check`，再 `deliver`。

源码、方案、场景或选中运行变化后，按 `status --task <身份> --format text` 的下一步继续，复核稿中的预填结论逐项改为“已复核”。检查、场景验收、业务验收和最终交付分别报告，证据来自真实入口及原始结果。收尾说明、交接与关闭见[团队交付](references/team-delivery.md)。

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
