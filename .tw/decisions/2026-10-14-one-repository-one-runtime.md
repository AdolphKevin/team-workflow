---
title: "团队流程与项目知识合并为一个仓库、一个运行时、一个项目目录"
scope: ["self:skills/**", "self:scripts/**"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
status: "accepted"
tags: ["合并", "运行时", ".tw", "目录", "命名"]
---
# 团队流程与项目知识合并为一个仓库、一个运行时、一个项目目录

团队流程与项目知识由同一个仓库发行，只有一个 Python 运行时（team-knowledge/scripts/tw_runtime，团队部分在 team/）。项目中只保留 `.tw/` 一个目录：知识与配置入库，`local/` 被忽略。

## 备选
- 沿用 `.team-workflow/` 作为目录：它是旧的纯本地证据目录，被各项目根 .gitignore 整体忽略，原地替换风险高，不采用。
- `workbench`、`keel`、`baton`、`cairn` 等通用名：代理工具圈已有同名目录或命令，不采用。

## 后果
团队技能依赖知识技能，安装说明要求一次装齐，`tw version --check-install` 核对两者属于同一发行。

## 放弃过的做法
- 两个仓库独立发布，通过 contract_version 1 与 8 项能力协商联动
  放弃原因：两边按“联合候选版”锁步发版，能力清单在两仓各写一份；一个工具的写入会使另一个工具的结果失效，代理只能按“让工具通过”的顺序操作
  重新考虑的条件：知识部分出现团队以外、独立发版的使用者
  来源：codestable-compact 提交 4364912；本仓提交 41b1a5a；方案第 P 节第 3、8 条
  关键词：contract_version、能力协商、两个仓库、联合候选版、独立 CS
