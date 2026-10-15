---
title: "团队流程与项目知识合并为一个仓库、一个运行时、一个项目目录"
scope: ["self:skills/**", "self:scripts/**"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md", "self:docs/proposals/2026-10-15-local-state-location.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
status: "accepted"
tags: ["合并", "运行时", ".tw", "目录", "命名", "本机状态", "共享仓映射", "用户级", "worktree"]
---
# 团队流程与项目知识合并为一个仓库、一个运行时、一个项目目录

团队流程与项目知识由同一个仓库发行，只有一个 Python 运行时（team-knowledge/scripts/tw_runtime，团队部分在 team/）。项目中只保留 `.tw/` 一个目录：知识与配置入库，`local/` 被忽略。

本机状态继续留在 `.tw/local/`，按检出目录隔离。共享仓与外部文件的默认路径放在用户级配置，按项目身份分组；检出目录可覆盖，命令行优先。工具只读两层文件，不自动迁移。具体格式、引用检查和成员操作见[本机状态边界方案](../../docs/proposals/2026-10-15-local-state-location.md)。

## 备选
- 沿用 `.team-workflow/` 作为目录：它是旧的纯本地证据目录，被各项目根 .gitignore 整体忽略，原地替换风险高，不采用。
- `workbench`、`keel`、`baton`、`cairn` 等通用名：代理工具圈已有同名目录或命令，不采用。

## 后果
团队技能依赖知识技能，安装说明要求一次装齐，`tw version --check-install` 核对两者属于同一发行。
新 worktree 可复用用户级路径；任务材料仍只在各自检出目录。手工试点材料放在仓库外，共享结论与关键数据写进入库原文。删除后果与清理方式见[成员说明](../../docs/member-guide.md#本机材料与清理)。

## 放弃过的做法
- 两个仓库独立发布，通过 contract_version 1 与 8 项能力协商联动
  放弃原因：两边按“联合候选版”锁步发版，能力清单在两仓各写一份；一个工具的写入会使另一个工具的结果失效，代理只能按“让工具通过”的顺序操作
  重新考虑的条件：知识部分出现团队以外、独立发版的使用者
  来源：codestable-compact 提交 4364912；本仓提交 41b1a5a；方案第 P 节第 3、8 条
  关键词：contract_version、能力协商、两个仓库、联合候选版、独立 CS
- 本机状态移到 `git rev-parse --git-path tw`，记录路径改用 `local:` 前缀
  放弃原因：仅避免 git clean 和编辑器搜索，却把工具数据从一处变为三处；worktree 状态在工作区外，需要另设路径前缀并改写路径校验和多处固定路径，live-chat 依赖工具也要跟着改，清理逻辑仍然复杂
  重新考虑的条件：实际出现整目录删除或 `git clean -fdx` 丢失进行中任务的事故，且成员说明不足以避免
  来源：本机状态边界方案第 7 节（初稿做法，已撤回）
  关键词：git-path tw、local:、状态移出工作区、.git、git clean、删除本机材料
