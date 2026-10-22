---
design: "D-tw-sop-1"
task: "TW-SOP-1"
revision: 4
assessment: {"complexity":"medium","risks":["public-contract"],"effort":"约半个工作日代理时长","drivers":["试点技能 playwright-acceptance 增加不依赖 tw 的输入与受阻原因写法，供 sop-board 的执行会话使用","场景指南与接入指南补充独立验证的采用方式","记录 SOP 验证独立化在本仓的归属与握手规则"],"uncertainties":[],"required_skills":["Python","技能写作"]}
roles: {"design_owner":"Claude","implementation_owner":"Codex","acceptance_owner":"AdolphKevin"}
---

> 历史文档：保留当时的方案或验证记录；现行能力与使用方式见 [README](../../README.md)。

# TW-SOP-1：playwright-acceptance 的独立用法与采用说明

> 本文件是任务 TW-SOP-1 的 tw 方案原文。总体设计见 sop-board 仓库的 `docs/proposals/2026-10-19-standalone-sop-verification.md`（v8）的 D9、D12 与第 8 节 TW-SOP-1 一行；验收场景见 [docs/sop/archive/tw-sop-1.yaml](https://github.com/AdolphKevin/team-workflow/blob/8be02e4/docs/sop/tw-sop-1.yaml)。
>
> 状态：修订 2。修订 1 于 2026-10-19 经 AdolphKevin 授权由 Claude 代批；实现时发现场景指南已达 5000 字的篇幅上限，修订 2 改为场景指南只加一句指向接入指南的独立验证方式，采用方式完整写在接入指南；修订 3 依第 1 轮验收补充转换失败时结果目录保持原样、如实写明场景指南的压缩方式、任务范围加入发行清单；修订 4 依第 2 轮验收在技能文本中写明执行者的取法；均于同日代批。

## 全局范围
<!-- tw-section id=scope-global type=global-scope -->
让试点技能 `playwright-acceptance` 在没有接入 tw 的项目中也能使用：待执行清单可以来自 praxis-skills 的 `sop-verify pending --format json`，也可以来自 sop-board 交给执行会话的清单文件；受阻与跳过的 `finding` 可以直接写原因文字。tw 项目的用法与输出保持不变。场景指南与接入指南补充 SOP 验证独立化的采用方式，写一条决策记录归属与握手规则。

非目标：tw 运行时的命令与契约；sop-verify 与 sop-board 的代码；playwright-acceptance 的执行模型（CDP 接管、单 worker、证据录制）。

- 需求级验收：A1、A2、A3

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | skills/playwright-acceptance/scripts/to_scenarios.py | 读取待执行清单、转换结果、写受阻原因 | 执行者 | tw、sop-verify、sop-board | team-workflow | A1 |
| self | skills/playwright-acceptance/SKILL.md 与 references | 按指引在有无 tw 的项目中执行 | 维护者 | 执行浏览器场景的代理 | team-workflow | A2 |
| self | 场景指南、接入指南与决策记录 | 阅读采用方式与归属 | 维护者 | 成员与代理 | team-workflow | A3 |

## 待执行清单与受阻原因
<!-- tw-section id=I1 type=interface depends=scope-global -->
`to_scenarios.py --pending <文件>` 接受三种清单：tw 的 `scenarios pending --format json` 输出（`pending` 数组，元素带 `id`）、sop-verify 的 `pending --format json` 输出（`pending` 数组，元素带 `scenario`），以及顶层直接是场景编号字符串或上述元素的数组。三种都取出场景编号用于核对；无法取出任何编号时报错并说明接受的格式。

转换失败时 `--out` 保持原样：结果与证据先在临时目录生成，成功后再整体复制到 `--out`。

新增 `--finding-from-reason`：没有用 `--finding` 指定的受阻场景，以测试抛出的 `受阻：` 之后的原因文字为 `finding`；跳过场景以 `test.skip()` 的说明为 `finding`，没有说明时报错并提示补写。`--finding` 指定的值优先。不加该选项时行为与现在相同：受阻与跳过必须用 `--finding` 指定。

## 技能文本
<!-- tw-section id=I2 type=interface depends=scope-global,I1 -->
`SKILL.md` 的工作流程第 1 步与第 7 步、命令节写明两种项目：接入 tw 的项目照旧用 `tw team scenarios pending` 与 `submit`；没有 tw 的项目用 sop-verify 的 `pending --format json` 取清单，用 `--finding-from-reason` 转换，用 sop-verify 的 `submit` 登记，或把结果文件交回调用方（例如 sop-board 的执行会话）。`--executor` 写实际执行测试的人或会话；转换他人执行的报告时，执行者与实现者以使用者告知的为准，没有告知时先询问。篇幅在发布检查的预算内。

## 采用说明与决策
<!-- tw-section id=D1 type=data depends=scope-global -->
接入指南（`skills/team-workflow/references/onboarding.md`）补充采用方式：不接入团队流程的项目可用 praxis-skills 的 `sop-verify` 按同一场景格式验证，轮次与协作在 sop-board；入口声明可复制进 `acceptance_entries`；看板导出的结果 JSONL 可直接用 `tw team scenarios submit` 登记。场景指南（`skills/team-workflow/references/scenarios.md`）已达篇幅上限，只加一句指向接入指南的独立验证方式，为此删去开头一句范围说明，并压缩几处措辞，规则不变。新增决策记录 `.tw/decisions/2026-10-19-standalone-sop-verification.md`：`sop-verify` 归 praxis-skills，看板归 sop-board，总体方案在 sop-board 的 `docs/proposals/`；三方只共享场景文件与结果 JSONL 两种格式，格式只加字段；team-workflow 不依赖另外两个仓库的代码。

## 验收 A1：清单与受阻原因
<!-- tw-section id=A1 type=acceptance depends=scope-global,I1 -->
SOP-01 节点全部场景通过。

- 场景：docs/sop/archive/tw-sop-1.yaml#SOP-01
- 依据：位置 sop-board 仓库 docs/proposals/2026-10-19-standalone-sop-verification.md 的 D9、D12；版本 v8（2026-10-19）；确认人 AdolphKevin / 位置 docs/proposals/2026-10-19-tw-sop-1-design.md 的 I1 节；版本 修订 4；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

## 验收 A2：技能文本
<!-- tw-section id=A2 type=acceptance depends=scope-global,I2 -->
SOP-02 节点全部场景通过。技能场景由只装候选技能的新会话执行。

- 场景：docs/sop/archive/tw-sop-1.yaml#SOP-02
- 依据：位置 sop-board 仓库 docs/proposals/2026-10-19-standalone-sop-verification.md 的 D9；版本 v8（2026-10-19）；确认人 AdolphKevin / 位置 docs/proposals/2026-10-19-tw-sop-1-design.md 的 I2 节；版本 修订 4；确认人 AdolphKevin
- 检查：无

## 验收 A3：采用说明与决策
<!-- tw-section id=A3 type=acceptance depends=scope-global,D1 -->
SOP-03 节点全部场景通过。

- 场景：docs/sop/archive/tw-sop-1.yaml#SOP-03
- 依据：位置 sop-board 仓库 docs/proposals/2026-10-19-standalone-sop-verification.md 的 D12 与第 7 节 E-T1；版本 v8（2026-10-19）；确认人 AdolphKevin / 位置 docs/proposals/2026-10-19-tw-sop-1-design.md 的 D1 节；版本 修订 4；确认人 AdolphKevin
- 检查：release
- 验证：自动

## 任务 T1：脚本、技能文本与采用说明
<!-- tw-section id=T1 type=task depends=scope-global,I1,I2,D1 -->
按 I1 修改 `to_scenarios.py` 并在 `tests/test_playwright_to_scenarios.py` 中先写失败测试再实现；按 I2 修改 `SKILL.md`；按 D1 补充两份指南并写决策记录。运行全量测试、发布检查与 `tw check`。

- 验收：A1、A2、A3
- 范围：skills/playwright-acceptance、skills/team-workflow/MANIFEST.json、tests/test_standalone_sop_docs.py、skills/team-workflow/references/scenarios.md、skills/team-workflow/references/onboarding.md、tests/test_playwright_to_scenarios.py、.tw/decisions、docs/sop/archive/tw-sop-1.yaml、docs/proposals/2026-10-19-tw-sop-1-design.md、docs/validation.md
- 前置任务：无
