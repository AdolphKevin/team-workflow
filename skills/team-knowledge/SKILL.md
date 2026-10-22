---
name: team-knowledge
description: 项目知识入口。开始需求、修复、重构或评审前，用 tw brief 读取 .tw/ 中与任务相关的现行约束（rule）、决策（decision）和踩过的坑（lesson）；完成后在同一个 PR 中直接编辑 Markdown 更新知识并运行 tw check。也用于把旧 .codestable 迁移到 .tw/，以及按用户要求从历史中找回教训。
---

# 项目知识

项目知识的读写与使用的开发流程无关。

知识放在仓库的 `.tw/`：`overview.md`、`glossary.md`、`rules/`、`decisions/`、`lessons/`，与代码一起评审；`.tw/local/` 是被 Git 忽略的本机目录。命令都是 `python3 <本技能目录>/scripts/tw.py <命令>`，下文简写为 `tw`。

## 开工前

1. 用用户的原始要求读取：`tw brief --task "<要求>" [--path <文件或目录>] [--symbol <符号>]`。查明真实入口后，带上 `--path` 再读一次。
2. 按读到的约束实施。要重新采用“放弃过的做法”或已拒绝的决策时，先写出新理由并告知用户。
3. 需要全文时用 `tw read <条目或文档编号>`；`tw read --list` 列出已登记的原文。

## 完成后

可复用的结论按种类写：

- 修复了根因不明显的缺陷：写 lesson，在 `guards` 引用能发现它的测试。
- 做了难以逆转、缺少背景会让人意外、确有取舍的选择：写或改写 decision。决定改变时，旧做法连同放弃原因移入“放弃过的做法”。
- 改变了必须保持的行为或契约：新增或改写 rule。
- 项目已登记原文（`config.json` 的 `documents`）时，直接改原文，条目引用它。

一次性结果、测试计数、工具版本、行号和任务过程写进 PR 或提交说明。没有可复用结论时说明理由即可。新条目可用 `tw new rule|decision|lesson --slug --title --scope --source` 生成骨架，核对过当前代码后加 `--verified-at-head`。最后运行 `tw check` 并修复全部错误，知识与代码放在同一个 PR。

写法与正反例见[写作规范](references/writing.md)。

## 其他场景

- 首次使用：`tw init` 预览，`tw init --apply --guidance` 写入，再填写 `overview.md`。概览来源取可重复的 `--source`，其次取 `README.md`；预览列出所需来源，补齐后写入。
- 项目里还有 `.codestable/` 或 `.team-workflow*`：由你按[迁移指南](references/migration.md)逐条整理。
- 用户要求找回历史教训：按[找回历史教训](references/lessons-from-history.md)。
- 健康报告：`tw audit`。brief、read、check、audit 只读。
