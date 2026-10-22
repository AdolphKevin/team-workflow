---
title: "本仓只发行知识库"
scope: ["self:skills/team-knowledge/**", "self:scripts/**", "self:docs/design.md", "self:docs/install.md"]
source: ["self:docs/proposals/2026-10-22-knowledge-only.md", "self:docs/proposals/2026-10-14-unified-redesign.md", "self:docs/proposals/2026-10-15-local-state-location.md"]
status: "accepted"
tags: ["知识库", "发行", "职责", "运行时", "本机状态", "升级", "放弃原因"]
---
# 本仓只发行知识库

成员在任意开发流程中读写同一份 `.tw/` 知识。本仓只发行 team-knowledge 与它的 Python 标准库运行时；仓库名、知识格式和本机材料位置保持不变。职责、字段去向和升级步骤以[批准方案](../../docs/proposals/2026-10-22-knowledge-only.md)及[升级说明](../../docs/install.md#从-0x-升级)为准。

## 备选

继续集中发行开发方法、流程和验收：与成员自选方法及 sop-board 重复，维护与使用成本过高，不采用。拆分为两个锁步发行的运行时也不采用，知识使用应独立于流程。

## 后果

旧配置与本机材料由升级者保留，知识命令只提示去向；测试文件引用可追溯，运行由产品仓库 CI 证明。平台协作交给 Issue/PR，SOP 验收与回归沉淀由 sop-board 发行。本仓独立代理按场景验收，结果写入验证记录。

## 放弃过的做法

以下删除的条目仅约束已退出的团队实现，失败机制集中保留于此；仍适用于知识层的条目改写其作用范围。原文可从 Git `8be02e4` 的同名 `.tw/` 路径读取，历史事实见[验证记录](../../docs/archive/validation-0.x.md)。

- 自带团队批准、执行绑定与范围核对
  放弃原因：团队流程退出，删除 `lessons/2026-10-13-old-format-bypassed-plan-approval.md`、`lessons/2026-10-14-knowledge-commit-invalidated-evidence.md`、`lessons/2026-10-15-task-base-after-merge.md`、`lessons/2026-10-16-design-file-outside-scope.md`。要点：旧格式曾绕过新批准要求；知识提交被当成产品变化而整轮重跑；固定基线把合并进来的变更算进当前任务；方案原文被误算越界。知识结构校验继续保留。
  来源：上述历史条目、知识库方案第 3、4 节
  关键词：旧格式、批准、证据过期、合并基线、方案范围
- 自带评审、收尾与完成阶段的记录系统
  放弃原因：评审与关闭交给 Git 平台，删除 `lessons/2026-10-16-close-note-review-findings.md`、`lessons/2026-10-16-close-note-superseded-runs.md`、`lessons/2026-10-16-combined-approval-follows-review.md`、`lessons/2026-10-16-review-submission-route.md`、`lessons/2026-10-17-completed-task-records.md`。要点：收尾遗漏评审问题；重新采用已取代的失败运行；替换评审未移除其批准；平台任务误导向本地提交；历史交付被当前方案解析覆盖。问题归属、运行选用和历史事实应一致。
  来源：上述历史条目、知识库方案第 2、4 节
  关键词：评审问题、收尾、运行选用、合并批准、提交方式、历史事实
- 在知识工具中派生流程状态与恢复命令
  放弃原因：流程状态退出，删除 `lessons/2026-10-16-error-text-changed-recovery.md`、`lessons/2026-10-17-flow-output-facts.md`、`lessons/2026-10-17-repeated-command-source-snapshots.md`、`lessons/2026-10-17-reporting-boundaries.md`。要点：显示文字曾决定恢复分支；开工与状态读取不同事实；稳定阶段重复快照导致超时；一个字段兼作工具修改标记和交付摘要；空输出被占位文字污染。保留按事实判定、原始证据不改写的原则。
  来源：上述历史条目、知识库方案第 2、4 节
  关键词：错误措辞、状态、重复快照、性能、字段含义、空文件
- 在本仓重复维护场景流程与平台适配
  放弃原因：场景职责归 sop-board，删除 `lessons/2026-10-20-scenario-granularity-undefined.md`；它记录了细节被拆成场景、技术分层拆任务、反复补措辞，导致真实业务链路未验收。平台职责退出，删除 `decisions/2026-10-15-task-platform.md`、`rules/platform-contract.md` 与 `.tw/platform.py`；平台记录的真实作者、来源与时间应由所选平台维护。
  来源：上述历史条目、知识库方案第 2、4、5 节
  关键词：场景粒度、真实入口、平台脚本、来源、作者、时间
- 两个仓库按能力协商锁步发行
  放弃原因：能力清单与联合版本重复维护，工具互相使结果失效；统一知识格式即可独立使用。
  来源：旧知识仓的相关提交、本仓提交 41b1a5a、合并方案第 P 节
  关键词：contract_version、能力协商、联合候选版
- 本机状态移到 Git 元数据目录
  放弃原因：工具数据会分散到三处，需新路径前缀并增加跨工作树与清理复杂度；仍按检出目录放在 `.tw/local/`。
  重新考虑的条件：发生真实的本机材料误删且成员说明不能避免
  来源：本机状态边界方案第 7 节
  关键词：git-path tw、local:、状态移出工作区、删除本机材料
