---
title: "SOP 独立验证、看板与团队流程通过场景文件和结果格式协作"
scope: ["self:skills/playwright-acceptance/**", "self:skills/team-workflow/references/scenarios.md", "self:skills/team-workflow/references/onboarding.md"]
source: ["self:docs/proposals/2026-10-19-tw-sop-1-design.md"]
status: "accepted"
tags: ["SOP", "独立验证", "sop-verify", "sop-board", "praxis-skills", "采用方式"]
---
# SOP 独立验证、看板与团队流程通过场景文件和结果格式协作

采用依据与握手规则见[已批准方案 D1](../../docs/proposals/2026-10-19-tw-sop-1-design.md#采用说明与决策)：`sop-verify` 归 praxis-skills，看板归 sop-board，总体方案位于 sop-board 的 `docs/proposals/`。

三方只共享场景文件与结果 JSONL 两种格式，格式只加字段。team-workflow 不依赖另外两个仓库的代码，协作通过文件完成。

## 备选

- 把独立验证与看板并入 team-workflow：会将独立使用绑定到团队流程，采用方案 D1 的仓库分工。
- 跨仓库直接导入运行时代码：会增加安装与升级耦合，采用文件格式握手。

## 后果

项目可按需采用独立验证或团队流程。浏览器执行技能提供两种路径，tw 项目沿用原有用法；独立验证的采用与接入见[场景指南](../../skills/team-workflow/references/scenarios.md)与[接入指南](../../skills/team-workflow/references/onboarding.md)。
