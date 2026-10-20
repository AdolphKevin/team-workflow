---
design: "D-tw-tier-1"
task: "TW-TIER-1"
revision: 2
assessment: {"complexity":"medium","risks":["public-contract"],"effort":"约一个工作日代理时长，分两段","drivers":["没有登记检查的任务以场景验收交付","产品变化后场景待判定，重跑或沿用","撤回修订 1 的检查形式","标准、指南、入口、交付、接入与全局指引改为以场景验收最终交付"],"uncertainties":[],"required_skills":["Python","技能写作"]}
roles: {"design_owner":"Claude","implementation_owner":"Claude","acceptance_owner":"AdolphKevin"}
---

# TW-TIER-1：以 SOP 场景验收最终交付

> 本文件是任务 TW-TIER-1 的 tw 方案原文。依据与正文见[以 SOP 场景验收最终交付（修订 2）](2026-10-20-verification-tiers.md)，AdolphKevin 于 2026-10-20 批准；验收场景见 [docs/sop/tw-tier-1.yaml](../sop/tw-tier-1.yaml)。
>
> 状态：修订 2，按已批准方案修订 2 改写；修订 1 依据方案修订 1。

## 全局范围
<!-- tw-section id=scope-global type=global-scope -->
按已批准方案修订 2 第 2、3 节修改运行时与团队技能文本：需求完成以独立执行者经真实入口执行的场景为准；没有登记检查的任务以场景验收交付；产品变化后已通过场景待判定，受影响的重跑，不受影响的写明理由沿用；撤回修订 1 的检查形式与快速检查；本仓自身测试删除。

非目标：playwright-acceptance 与 sop-verify；sop-board 的代码。

- 需求级验收：A1、A2、A3、A4

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | tw team start、scenarios submit、review、accept、deliver | 没有登记检查的任务以场景验收交付 | 实施负责人与执行者 | 评审人与交付 | team-workflow | A1 |
| self | tw team scenarios pending、submit、carry | 产品变化后重跑或沿用场景 | 独立执行者 | 交付 | team-workflow | A2 |
| self | team-workflow 的 SKILL.md、参考文档与指引模板 | 按标准写方案与验收 | 维护者 | 代理与成员 | team-workflow | A3 |
| self | scripts/check_release.py | 发行检查与篇幅预算 | 维护者 | 发行 | team-workflow | A4 |

## 运行时
<!-- tw-section id=I1 type=interface depends=scope-global -->
`checks` 可为空对象，`required_checks` 可为空数组，风险可不配检查；没有适用检查时 `run` 只绑定当前源码。产品变化后，此前通过或沿用的场景在 `pending` 中为 `undetermined`（待判定）；`scenarios carry` 以 `{scenario, reason, scope, executor, executed_at}` 登记沿用，只接受待判定场景，统计中沿用与执行分开计数。整体交付按方案 2.5：`overall_complete` 与 `delivery_complete` 相同，删去回归自动化状态。场景 `regression` 只记人工说明，旧形状照常读取不产生效果。配对文件恢复为 `{case, scenarios, note}`。契约写在 contracts.md。

## 指令文本
<!-- tw-section id=D1 type=data depends=scope-global -->
按方案修订 2 第 3 节修改业务验收标准、测试能力建设、场景指南、团队入口与团队交付、接入指南和全局指引模板；撤回修订 1 中细节交给测试与快速检查的文字。

## 验收 A1：场景验收与交付
<!-- tw-section id=A1 type=acceptance depends=scope-global,I1 -->
SOP-01 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-01
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.5 节与第 4 节；版本 修订 2（2026-10-20）；确认人 AdolphKevin
- 检查：无

## 验收 A2：产品变化后的回归
<!-- tw-section id=A2 type=acceptance depends=scope-global,I1 -->
SOP-02 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-02
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.4 节与第 4 节；版本 修订 2（2026-10-20）；确认人 AdolphKevin
- 检查：无

## 验收 A3：代理按标准写方案
<!-- tw-section id=A3 type=acceptance depends=scope-global,D1 -->
SOP-03 节点全部场景通过。技能场景由只装候选技能的新会话执行。

- 场景：docs/sop/tw-tier-1.yaml#SOP-03
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 2.1–2.3 节与第 4 节；版本 修订 2（2026-10-20）；确认人 AdolphKevin
- 检查：无

## 验收 A4：发行
<!-- tw-section id=A4 type=acceptance depends=scope-global,D1 -->
SOP-04 节点全部场景通过。

- 场景：docs/sop/tw-tier-1.yaml#SOP-04
- 依据：位置 docs/proposals/2026-10-20-verification-tiers.md 第 3 节；版本 修订 2（2026-10-20）；确认人 AdolphKevin
- 检查：release
- 验证：自动

## 任务 T1：运行时与文字
<!-- tw-section id=T1 type=task depends=scope-global,I1,D1 -->
分两段，每段完成后立即验收本段场景：

1. 运行时（起点：没有登记检查的任务开工；终点：产品变化后重跑或沿用场景并交付）：按 I1 修改，随后验收 SOP-01、SOP-02。
2. 文字（起点：方案作者读团队入口；终点：写出十几条业务流程场景、沿链路分段、不要求写测试的方案）：按 D1 修改，随后验收 SOP-03、SOP-04。

- 验收：A1、A2、A3、A4
- 范围：skills/team-workflow、skills/team-knowledge、scripts、tests、docs、.tw、.github、AGENTS.md、README.md、CHANGELOG.md
- 前置任务：无
