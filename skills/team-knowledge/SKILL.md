---
name: team-knowledge
description: 项目知识入口。开始需求、修复、重构或评审前，用 tw brief 读取 .tw/ 中与任务相关的现行约束（rule）、决策（decision）和踩过的坑（lesson）；完成后在同一个 PR 中直接编辑 Markdown 更新知识并运行 tw check。也用于把旧 .codestable 迁移到 .tw/，以及按用户要求从历史中找回教训。
---

# 项目知识

知识放在仓库的 `.tw/`：`overview.md`、`glossary.md`、`rules/`、`decisions/`、`lessons/`，与代码一起评审；`.tw/local/` 只在本机，不入库。命令都是 `python3 <本技能目录>/scripts/tw.py <命令>`，下文简写为 `tw`。

## 开工前

1. 用用户的原始要求读取：`tw brief --task "<要求>" [--path <文件或目录>] [--symbol <符号>]`。查明真实入口后，带上 `--path` 再读一次。
2. 按读到的约束实施。“放弃过的做法”和已拒绝的决策，没有新的理由并告知用户前不要重新采用。
3. 需要全文时用 `tw read <条目或文档编号>`；`tw read --list` 列出已登记的原文。

## 完成后

- 修复了根因不明显的缺陷：写 lesson，尽量绑定守护测试。
- 做了难以逆转、没有背景会意外、确有取舍的选择：写或改写 decision。决定改变时，把旧做法连同放弃原因移入“放弃过的做法”，不要删掉。
- 改变了必须保持的行为或契约：新增或改写 rule。
- 没有可复用的结论就不写。不记录一次性结果、测试计数、工具版本、行号或任务过程。
- 项目已登记原文（`config.json` 的 `documents`）的，改原文，不复制进条目。
- 新条目可用 `tw new rule|decision|lesson --slug --title --scope --source` 生成骨架；只有确实核对过当前代码，才加 `--verified-at-head`。
- 运行 `tw check` 并修复全部错误，知识与代码放在同一个 PR。

写法与正反例见[写作规范](references/writing.md)。

## 其他场景

- 首次使用：`tw init` 预览，`tw init --apply --guidance` 写入，再填写 `overview.md`。概览来源优先取可重复的 `--source`，其次取 `README.md`；预览列出所需来源，补齐后写入。
- 项目里还有 `.codestable/` 或 `.team-workflow*`：按[迁移指南](references/migration.md)由你整理，不使用脚本。
- 用户要求找回历史教训：按[找回历史教训](references/lessons-from-history.md)。
- 健康报告：`tw audit`。brief、read、check、audit 都不写文件。
