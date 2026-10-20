---
design: "D-tw-tier-1"
task: "TW-TIER-1"
revision: 1
assessment: {"complexity":"medium","risks":["public-contract"],"effort":"约一个工作日代理时长，分两段","drivers":["场景粒度、用例集、分段验收与快慢检查写入标准、指南、入口、交付与接入","配对文件的检查形式与 accept 核对","scenarios check 输出场景数"],"uncertainties":[],"required_skills":["Python","技能写作"]}
roles: {"design_owner":"Claude","implementation_owner":"Claude（文字）、Codex（运行时）","acceptance_owner":"AdolphKevin"}
---

# TW-TIER-1：验证规格分级与分段验收

> 本文件是任务 TW-TIER-1 的 tw 方案原文。依据与正文见[验证规格分级与分段验收（v1）](2026-10-20-verification-tiers.md)，AdolphKevin 于 2026-10-20 批准方案全文；验收场景见 [docs/sop/tw-tier-1.yaml](../sop/tw-tier-1.yaml)。
>
> 状态：修订 1，按已批准方案由 Claude 代为记录批准。

## 全局范围
<!-- tw-section id=scope-global type=global-scope -->
按已批准方案第 2、3 节修改团队技能的指令文本与运行时：场景只写业务流程并控制数量，复杂任务的用例集只覆盖主流程，细节用例由检查中的测试用例覆盖，沿业务链路分段并逐段验收，检查分快慢两组。

非目标：新增按数量拒绝的硬性检查；快速检查的配置字段（快慢分组由检查的 `purpose` 与项目验收方案说明）；playwright-acceptance 与 sop-verify。

- 需求级验收：A1、A2、A3、A4

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | tw team scenarios coverage、tw team accept | 配对检查形式并在业务验收时核对 | 实施代理 | 评审人与交付 | team-workflow | A1 |
| self | tw team scenarios check | 输出场景总数与各节点场景数 | 方案作者 | 评审人 | team-workflow | A2 |
| self | team-workflow 的 SKILL.md 与参考文档 | 按分级标准写方案、分段实施与验收 | 维护者 | 代理与成员 | team-workflow | A3 |
| self | scripts/check_release.py | 发行检查与篇幅预算 | 维护者 | 发行 | team-workflow | A4 |

## 配对的检查形式
<!-- tw-section id=I1 type=interface depends=scope-global -->
配对文件的 `covered` 每项必填 `case`、`note`，另含 `scenarios` 与 `checks` 至少一项。`checks` 每项为 `{check, cases}`，规则与场景 `regression` 的 `{check, cases}` 相同：引用已登记的 junit 或 go-json 检查，`cases` 为非空用例名数组。`coverage` 只核对结构。`accept` 对每个检查项按场景回归的同一规则核对（复用 `scenario_rounds.regression_reason` 的判定）：所列用例在当前源码的有效运行中出现并通过；未通过时报 `scenario-coverage-incomplete`，点名导入用例、检查与测试用例。`scenarios check` 另输出场景总数与各节点场景数，只呈现事实。契约文字写在 contracts.md。

## 指令文本
<!-- tw-section id=D1 type=data depends=scope-global -->
按已批准方案第 3 节：业务验收标准第 4 节第一步写入分层定义与数量（唯一定义处）；场景指南第 1 节链接到该定义，第 4 节写主流程用例集与配对的检查形式，篇幅不超过 5000；团队入口第 3 步改为导入主流程用例；团队交付“开工前”改为沿业务链路分段、第一段打通最薄的端到端路径、每段完成即验收、每段交回运行相关测试与快速检查、场景验收前运行全部检查；接入指南登记快速检查与完整检查，篇幅不超过 4000；2026-10-16 方案第 2.2 节注明由本方案修订。

## 验收 A1：用例覆盖的检查形式
<!-- tw-section id=A1 type=acceptance depends=scope-global,I1 -->
SOP-01 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-01
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.3 节；版本 v1（2026-10-20）；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A2：场景数
<!-- tw-section id=A2 type=acceptance depends=scope-global,I1 -->
SOP-02 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-02
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.2 节；版本 v1（2026-10-20）；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A3：代理按分级标准做事
<!-- tw-section id=A3 type=acceptance depends=scope-global,D1 -->
SOP-03 节点全部场景通过。技能场景由只装候选技能的新会话执行。

- 场景：docs/sop/tw-tier-1.yaml#SOP-03
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.1–2.5 节与第 4 节；版本 v1（2026-10-20）；确认人 AdolphKevin
- 检查：无

## 验收 A4：发行
<!-- tw-section id=A4 type=acceptance depends=scope-global,D1 -->
SOP-04 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-04
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 3 节；版本 v1（2026-10-20）；确认人 AdolphKevin
- 检查：release
- 验证：自动

## 任务 T1：文字与运行时
<!-- tw-section id=T1 type=task depends=scope-global,I1,D1 -->
分两段，每段完成后立即验收本段场景：

1. 文字（起点：方案作者读团队入口；终点：写出十几条场景、沿链路分段的方案）：按 D1 修改指令文本，随后验收 SOP-03、SOP-04。
2. 运行时（起点：`scenarios coverage` 读取配对文件；终点：`accept` 按当前运行核对检查形式）：按 I1 先写失败测试再实现，随后验收 SOP-01、SOP-02。

每段交回运行相关测试与发行检查；场景验收前 `run` 运行全部登记检查。

- 验收：A1、A2、A3、A4
- 范围：skills/team-workflow、skills/team-knowledge/scripts/tw_runtime/team、tests、docs/sop/tw-tier-1.yaml、docs/sop/fixtures/tw-tier-1、docs/proposals/2026-10-20-tw-tier-1-design.md、docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md、.tw、CHANGELOG.md
- 前置任务：无
