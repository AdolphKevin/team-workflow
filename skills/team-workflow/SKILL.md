---
name: team-workflow
description: 团队任务入口：方案评审、实施交接、业务验收、自动回归与知识更新。适用于新任务、接手、方案变更和交付；独立调用 MATT 方法保持轻量。
disable-model-invocation: true
---

# 团队任务与开发方法

先读[方法与知识约定](references/matt-integration.md)。接手时沿用有效批准、验收和未决问题。团队任务、缺陷及每周复盘按[业务验收标准](references/business-acceptance.md)执行；首次接入时读[接入指南](references/onboarding.md)，包括“项目平台脚本”一节；缺少测试入口时也读该指南。

下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`；`--root`、`--repository` 可写在团队子命令前后。参数见 `--help`。

## 四步交付

用 `tw team project` 核对配置、知识与安装，用 `tw brief` 读知识和需求原文，查明入口、范围、失败情形及验收负责人。按可独立验收的工作拆分，主需求覆盖完整业务。安装被修改或工具报缺陷时停止报告，不修改安装文件。

方案分别评估复杂度、风险、工作量与待定事项。简单任务用短方案，开发后合并评审；中等、复杂任务先获具名批准，可用 `approval-draft --reviewer <姓名> --mode plan` 生成记录。复用已有授权和有效批准。

平台中等、复杂任务先开只含方案块的草稿变更请求，评审通过后再写代码（团队约定，工具不强制）。方案与批准可在描述和评审中，提交号可用 `approval-draft --revision` 记录。

1. **start**：首次用 `tw team start --task <任务文件> --design <方案> [--approval <批准>]`。后续用 `--task <身份>`（任务编号或完整 Issue 地址）补齐材料。实施或委派前读简报、确认实施条件；输入变化新建上下文。
2. **run**：`tw team run --task <身份>` 执行登记检查。必需结果可用后自动给出 `review.md`；失败保留原始输出，聚焦补跑失败或过期项。最终验收期间共享目录保持稳定。
3. **评审**：未参与实施的人填写姓名、规范与需求及逐项验收结论、理由、问题处置；人工观察由观察人填写。简单任务需合并批准时填“批准方案与代码：是”。配置平台时，将完整 Markdown 作为变更请求评审提交，`deliver` 自动导入；也可显式 `review --task <身份> --from-platform`。本地用 `review --task <身份> --submit`。不通过意见也可提交；绑定区与自动结果不改。
4. **deliver**：不改知识时用 `tw team deliver --task <身份> --reason <理由>`，顺序完成业务验收、知识处置报告和最终核查。失败停在对应步骤，重试复用有效记录，不手写报告 JSON。

简单平台任务可用 `start`、`run`、评审人在变更请求上提交评审、`deliver`。

要更新知识时，在第 3 步后先 `tw team accept --task <身份>`；通过后在同一分支更新 `.tw/` 并运行 `tw check`，再 `deliver --task <身份>`。检查通过、业务验收和最终交付分别报告，证据来自真实入口及原始结果。

源码、方案或选中运行变化后，用 `review --task <身份>` 核对“变化”，逐项把预填结论、人工观察的“待复核”改为“已复核”后提交。已知问题保留编号、负责人和影响；接受限制或延期须有确认及处置依据。

中断后用 `status --task <身份> --format text` 看有效记录和下一步；显式材料路径见[工具约定](references/contracts.md)。交付后按授权发布收尾说明或交接，报告记录关闭授权；工具不执行关闭。跨仓、接力与关闭见[团队交付](references/team-delivery.md)。

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
