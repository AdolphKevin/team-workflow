# Team Workflow

本仓只发行 `team-knowledge`：在任何开发流程里，开工前读取项目知识，完成后把仍有用的结论与代码一起维护。仓库名称保持不变。

知识放在各项目的 `.tw/`，通用命令只需 Python 3.10+ 和 Git。规则说明必须保持的行为，决策保留选择与放弃原因，教训记录真实发生的问题及其防护。

| 位置 | 内容 |
| --- | --- |
| `config.json` | 项目身份、上下文、共享仓与原文登记 |
| `overview.md`、`glossary.md` | 项目概览与项目特有术语 |
| `rules/`、`decisions/`、`lessons/` | 现行约束、决策与教训，与代码一起评审 |
| `local/` | 被 Git 忽略的本机路径映射、缓存和成员材料 |

## 安装与开始

按[安装与升级](docs/install.md)选择固定发行版本，只安装知识技能。下文用 `tw` 代表 `python3 <team-knowledge 技能目录>/scripts/tw.py`。

```bash
tw init                         # 预览；缺少 README 时用 --source self:文档路径
tw init --apply --guidance       # 初始化，并填写生成的 overview.md
tw brief --task "修改退款金额校验" --path src/pay/refund.py
tw read rules/refund-limit.md
tw check                        # 只检查结构与引用，不执行测试
tw audit                        # 查看健康报告与本机材料大小
```

日常使用见[成员操作说明](docs/member-guide.md)，条目格式见[写作规范](skills/team-knowledge/references/writing.md)。开发方法由成员选择；SOP 验收与回归沉淀由 sop-board 发行，职责依据见[已批准方案](docs/proposals/2026-10-22-knowledge-only.md)。

## 维护与验证

```bash
python3 scripts/check_release.py
python3 scripts/package.py --output <仓库外目录>/team-workflow.zip
```

发行包只含知识技能、插件元数据、许可与公开说明。本仓知识和本机材料留在本仓。修改技能后先运行 `python3 scripts/package.py --manifest` 更新文件清单，再执行发行检查。

[设计边界](docs/design.md)说明运行时职责。[验收标准](docs/acceptance.md)要求独立代理经实际命令入口执行场景，结果写入[验证记录](docs/validation.md)。两位真实成员的一周试点单独记录。
