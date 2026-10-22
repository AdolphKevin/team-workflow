---
title: "浏览器 SOP 验收与回归沉淀由 sop-board 发行"
scope: ["self:docs/design.md", "self:docs/install.md", "self:docs/acceptance.md"]
source: ["self:docs/proposals/2026-10-22-knowledge-only.md", "self:docs/proposals/2026-10-19-tw-sop-1-design.md"]
status: "accepted"
tags: ["场景验收", "Playwright", "浏览器", "CDP", "录屏", "回归", "上游用例"]
---
# 浏览器 SOP 验收与回归沉淀由 sop-board 发行

浏览器步骤执行、证据保留及已确认场景的回归沉淀随 sop-board 发行。本仓只保留知识库，验收入口及账号操作由产品仓库真实验证手册维护；知识条目引用测试或场景文件，不接管执行。

职责依据见[已批准方案](../../docs/proposals/2026-10-22-knowledge-only.md)。本仓自身由独立代理按当前场景直接验收，结果写入验证记录。

## 备选

继续在本仓保留独立验收副本：两套契约与升级路径重复，使用者需判断调用哪套，因此不采用。

## 后果

产品成员按 sop-board 已发行的契约整理入口与场景，人工范围保留原因、负责人和触发时机；知识使用者自行选择开发方法。

## 放弃过的做法

- 本仓维护浏览器验收副本，并让独立验证与团队流程通过文件格式协作
  放弃原因：验收职责已统一交给 sop-board，继续保留副本会重复维护与发行；旧操作见 Git 历史。
  来源：2026-10-19 的采用方案与 2026-10-22 知识库方案第 2、4、5 节
  关键词：浏览器验收、SOP、回归沉淀、格式协作
