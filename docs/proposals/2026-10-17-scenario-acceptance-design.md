---
design: "D-scenario-acceptance"
task: "TW-SCN-1"
revision: 1
assessment: {"complexity":"medium","risks":["public-contract"],"effort":"约 5 代理日","drivers":["改变方案验收节、评审观察与交付报告的格式，影响所有项目","新增场景命令与结果契约","本仓没有测试同事的用例集，场景由方案负责人依据批准方案编写并经 AdolphKevin 确认"],"uncertainties":[],"required_skills":["Python"]}
roles: {"design_owner":"Claude","implementation_owner":"Codex","acceptance_owner":"AdolphKevin"}
---

# 场景化黑盒验收：tw 任务方案

> 本文件是任务 TW-SCN-1 的 tw 方案原文。设计、取舍与决定见[已批准方案](2026-10-16-scenario-acceptance-and-positive-text.md)；验收场景见 [批次 2 场景](../sop/tw-scenario-acceptance.yaml)。

## 全局范围
<!-- tw-section id=scope-global type=global-scope -->
按已批准方案第 2 节把场景作为验收的基本单位，按第 3 节改写两个技能的指令文本。

- 需求级验收：A1、A2、A3、A4、A5、A6、A7、A8

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | tw team scenarios、start、run、review、accept、deliver | 场景校验、用例导入与覆盖、结果登记、按场景验收与回归状态、任务阶段 | 方案作者、执行者与评审人 | tw 运行时 | team-workflow | A1、A2、A3、A4、A5、A6、A8 |
| self | 两个技能的 Markdown | 阅读与按指引操作 | 维护者 | 使用 tw 的代理与成员 | team-workflow | A7 |

## 验收 A1：场景文件与方案引用
<!-- tw-section id=A1 type=acceptance depends=scope-global -->
批次 2 的 SOP-01 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-01
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A2：测试用例导入与覆盖
<!-- tw-section id=A2 type=acceptance depends=scope-global -->
批次 2 的 SOP-02 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-02
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A3：待执行清单与结果登记
<!-- tw-section id=A3 type=acceptance depends=scope-global -->
批次 2 的 SOP-03 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-03
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A4：增量验收
<!-- tw-section id=A4 type=acceptance depends=scope-global -->
批次 2 的 SOP-04 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-04
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A5：按场景验收与评审
<!-- tw-section id=A5 type=acceptance depends=scope-global -->
批次 2 的 SOP-05 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-05
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A6：复杂任务与回归状态
<!-- tw-section id=A6 type=acceptance depends=scope-global -->
批次 2 的 SOP-06 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-06
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A7：指令文本与职责划分
<!-- tw-section id=A7 type=acceptance depends=scope-global -->
批次 2 的 SOP-07 节点全部场景通过。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-07
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 2.3 补充；确认人 AdolphKevin
- 检查：release
- 验证：自动

## 验收 A8：任务阶段
<!-- tw-section id=A8 type=acceptance depends=scope-global -->
批次 2 的 SOP-08 节点全部场景通过（方案 D9）。

- 场景：docs/sop/tw-scenario-acceptance.yaml#SOP-08
- 依据：位置 docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md；版本 2026-10-16 批准版及 D9–D12；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 任务 T1：运行时
<!-- tw-section id=T1 type=task depends=scope-global -->
方案第 6 节段 1a、1b-1、1b-2。

- 验收：A1、A2、A3、A4、A5、A6、A8
- 范围：skills/team-knowledge/scripts、skills/team-knowledge/MANIFEST.json、tests、.tw/config.json、docs/sop
- 前置任务：无

## 任务 T2：指令文本
<!-- tw-section id=T2 type=task depends=scope-global -->
方案第 6 节段 0、2a、2b、2c。

- 验收：A7
- 范围：skills/team-workflow、skills/team-knowledge/SKILL.md、skills/team-knowledge/references、scripts、docs/proposals
- 前置任务：无
