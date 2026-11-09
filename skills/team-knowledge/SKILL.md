---
name: team-knowledge
description: 项目知识入口。开始需求、修复、重构或评审前，用 tw brief 读取 .tw/ 中与任务相关的现行约束（rule）、决策（decision）和踩过的坑（lesson）；完成后在同一个 PR 中直接编辑 Markdown 更新知识并运行 tw check。也用于定期复盘提交中的返工与验证问题、把旧 .codestable 迁移到 .tw/，以及按用户要求从历史中找回教训。
---

# 项目知识

项目知识的读写与使用的开发流程无关。

知识放在仓库的 `.tw/`：`overview.md`、`glossary.md`、`rules/`、`decisions/`、`lessons/`，与代码一起评审；`.tw/local/` 是被 Git 忽略的本机目录。命令写作 `tw <命令>`：PATH 上有 `tw` 启动器时直接运行，否则为 `python3 <本技能目录>/scripts/tw.py <命令>`。交给子代理时，把 `tw version` 输出的 `command` 写进交接。

## 开工前

1. 用用户的原始要求读取：`tw brief --task "<要求>" [--path <文件或目录>] [--symbol <符号>]`。查明真实入口后，带上 `--path` 再读一次。
2. 按读到的约束实施。要重新采用“放弃过的做法”或已拒绝的决策时，先写出新理由并告知用户。
3. 需要全文时用 `tw read <条目或文档编号>`；`tw read --list` 列出已登记的原文。

## 评审时

用改动的文件（`git diff --name-only <基线>...`）作 `--path` 读取，逐条核对读到的规则，评审意见写明不满足哪一条。

## 完成后

按结论的种类决定去向：

| 结论 | 去向 |
| --- | --- |
| 修复了根因不明显的缺陷 | lesson，标题写成一句要遵守的做法，`guards` 引用能发现它的测试 |
| 又遇到已有教训或规则所述的问题，或照它做对了 | 在该条目追加“出现记录”或“做对的例子”；教训出现满 3 个不同日期时升级为 rule |
| 难以逆转、缺少背景会让人意外、确有取舍的选择，含用户确认的产品决定 | decision；决定改变时，旧做法连同放弃原因移入“放弃过的做法” |
| 改变了必须保持的行为或契约 | rule |
| 验证环境的操作事实：入口、账号类别、验证码与密钥的取得位置 | 产品仓库的真实验证手册 |
| 个人偏好与协作习惯 | 代理或个人记忆 |
| 一次性结果、测试计数、工具版本、行号、任务过程 | PR 或提交说明 |
| 草稿、日志、截图、原始输出 | `.tw/local/<任务>/` |

结论写在它所约束的代码所在的仓库；项目已登记原文（`config.json` 的 `documents`）时直接改原文，条目引用它。该仓库还没有 `.tw/` 时，先写进 PR 说明，并向用户提出初始化或迁移。条目中的人写成角色与日期，如“用户确认（2026-11-08）”“财务确认”。

收尾时通读 `.tw/local/<任务>/` 和本次写入记忆的内容，其中的项目结论按上表移入仓库。没有可复用结论时说明理由即可。新条目可用 `tw new rule|decision|lesson --slug --title --scope --source` 生成骨架，核对过当前代码后加 `--verified-at-head`；改写已有条目时，核对后把 `verified` 更新为当前提交与日期。最后运行 `tw check` 并修复全部错误，知识与代码放在同一个 PR。

写法与正反例见[写作规范](references/writing.md)。

## 其他场景

- 首次使用：`tw init` 预览，`tw init --apply --guidance` 写入，再填写 `overview.md`。概览来源取可重复的 `--source`，其次取 `README.md`；预览列出所需来源，补齐后写入。
- 项目里还有 `.codestable/` 或 `.team-workflow*`：由你按[迁移指南](references/migration.md)逐条整理。
- 定期复盘提交，或用户要求找回历史教训：按[复盘与找回教训](references/lessons-from-history.md)。
- 查看知识健康或清理本机材料：`tw audit` 列出反复出现的条目，并按目录列出 `.tw/local/` 的大小与最后修改时间。brief、read、check、audit 只读。
