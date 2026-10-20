---
title: "本仓通过只读项目脚本接入 GitHub"
scope: ["self:.tw/platform.py", "self:.tw/config.json"]
source: ["用户确认：AdolphKevin，2026-10-15，会话中确认需求在 Issue、方案与批准在 PR 描述与评审、从 GitHub Actions 导入检查结果", "self:.github/workflows/validate.yml", "self:skills/team-workflow/references/platform.md"]
status: "accepted"
tags: ["平台", "GitHub", "Issue", "PR", "持续集成", "项目脚本", "接入"]
---
# 本仓通过只读项目脚本接入 GitHub

## 背景与决定

AdolphKevin 在 2026-10-15 的本次接入会话确认：需求在 GitHub Issue，方案在 PR 描述，批准在 PR 评审，
从 GitHub Actions 导入检查结果；确认记录写在 source 中。
本仓在 `.tw/config.json` 登记 `.tw/platform.py` 的 task、commit、reference、ci-result 操作，
只用 Python 标准库和 `gh api`；凭据仅由已有 gh 客户端提供，不读取、保存或输出凭据。

Issue #2 的最后一条评论直接链接 PR #3，PR #3 正文没有关闭关键词。
本仓按 Issue 正文或评论中的同仓完整 PR 地址关联，同时支持 PR 正文的
Closes/Fixes/Resolves（含其变体）加 `#N`、`所有者/仓库#N` 或完整 Issue 地址；
分页扫描所有状态的 PR，不把普通 Issue 提及当作关闭关联。
task 首项是 Issue，其后完整合入 Issue 评论、关联 PR 描述（change）、已提交评审（review）、
PR 讨论与行内评论（comment），保留实际作者、原文及时间；没有关联 PR 时只返回 Issue 和评论。
遇到重定向、缺失对象、作者或必要字段时拒绝，不改用父对象。

REST 评审用 `submitted_at` 表示发表时间；其最后编辑时间额外通过固定的只读 GraphQL
`PullRequestReview.lastEditedAt` 查询取得，并核对编号、地址和正文，null 表示从未编辑。
其余对象映射 REST 的 `created_at`、`updated_at`；原始 JSON 完整交给工具存档。
reference 支持 Issue、PR、评论、提交，以及固定到完整提交号的文件；内容对象的 `sha` 是文件摘要，不能当作提交号。
平台上不存在的提交返回 `exists: false`，作者与时间为 null，不伪造占位值。

## 持续集成定位与来源映射

locator 是恰含四个正整数的对象：
`{"run_id":38719357681,"attempt":1,"job_id":116369807488,"artifact_id":11964392562}`。
仓库固定为 `github.com/AdolphKevin/team-workflow`；运行必须来自 `validate.yml` 的最新成功尝试。

- repository、revision 来自运行的 `repository.full_name`、`head_sha`；run 的 id、attempt、latest_attempt、url 来自 `id`、`run_attempt`（最新运行响应）、`html_url`，成功取 `status` 和 `conclusion`。
- job 来自指定尝试的完整分页任务列表，id、name、run_id、attempt 映射 `id`、`name`、`run_id`、`run_attempt`，起止时间映射 `started_at`、`completed_at`，成功取状态和结论。
- artifact 来自该运行的完整分页产物列表，id、run_id、revision、digest、created_at、expired 映射 `id`、`workflow_run.id`、`workflow_run.head_sha`、`digest`、`created_at`、`expired`；另核对仓库编号。

validate.yml 的 `TW_RUN_CONTEXT.job` 使用 `github.job`，即 `validate`；保留平台显示名
`validate (3.10)` / `validate (3.13)`，符合工具允许的 `标识 (` 前缀。
产物名必须对应 `workflow-python-<版本>-attempt-<次数>`；两个任务时间重叠，单凭时间不足以配对。
脚本核对产物未过期、来源、创建时间和平台摘要，通过 gh 跟随下载重定向，只在给定空目录创建 ZIP。

## 备选

- 仅用 PR 正文关闭关键词：历史样本没有该关联，会漏掉 PR #3，故保留 Issue 中的直接链接。
- 把方案和批准放回 Issue 评论：与用户确认的位置不同，不采用。
- 自行管理 HTTP 凭据或内置平台实现：已有 gh，且指引要求项目脚本优先复用客户端，不采用。
- 以评审提交时间代替最后编辑时间，或自行生成平台产物摘要：会掩盖已编辑历史或丢失平台摘要依据，不采用。

## 后果

平台调用仍是只读，安装和登录由用户维护 gh；全量扫描 PR 和逐条查询评审可能耗时，配置超时为 120 秒。
离线输入、合成部分和真实平台待核对范围见提交 5313562 中的 `tests/fixtures/project_platform/README.md`（本仓测试于 2026-10-20 删除）。
真实分页、下载重定向、产物摘要及有评审 PR 的编辑时间仍由沙箱外验收，离线通过不代表这些已经完成。

## 接入指引问题与处理

1. 指引未规定 Issue 与 PR 如何关联；据真实评论中的直接链接和用户给出的关闭关键词约定实现，并保留无关联分支。
2. 契约要求最后编辑时间，但 REST 评审不提供；补只读 GraphQL 查询，不凭提交时间推定未编辑。
3. 样本没有 PR 列表、已提交评审和 ZIP，且本次禁止联网；列表复用原始 PR，评审和 ZIP 显式用合成输入，真实结果待外部核对。
4. 不存在提交仍要求作者与时间，契约未定义无对象时的合法值；采用非零退出，不输出虚构字段。
5. 本次沙箱无法执行调查中的联网列表和第 4 步在线检查；用已提供的原始响应调查，将在线一致性命令交给沙箱外执行。
6. 按指引填写脚本 scope 后，tw check 排除 `.tw/` 文件而报告范围匹配不到；保留要求的脚本范围及原始警告，不修改运行时或删除范围来消除提示。
