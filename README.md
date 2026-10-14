# Team Workflow

本仓集中维护三样东西：团队开发流程、项目知识，以及直接复用的 MATT 开发方法。

| 技能 | 作用 |
| --- | --- |
| `team-workflow` | 团队任务入口：评估、分节方案、评审、实施与交接、业务验收、知识更新和最终交付 |
| `team-knowledge` | 项目知识入口，也承载唯一的 Python 运行时 `tw`：开工前读取 `.tw/` 中的现行约束、决策和踩过的坑，完成后在同一改动中更新 |
| `matt-*` | 15 个 MATT 方法：规格、拆分、实现、诊断、测试先行、设计、领域建模、审查、PR 等 |

用 `team-workflow` 开始新任务时，默认进入团队流程。简单任务可以先实施，再由具体评审人一并批准方案和代码；中等、复杂任务要先批准方案再实施。直接调用 MATT 方法保持轻量，只需要 `.tw/` 知识。

## 项目里的 `.tw/`

| 位置 | 是否入库 | 内容 |
| --- | --- | --- |
| `config.json` | 入库 | 项目身份、共享仓、原文登记、团队检查配置 |
| `overview.md`、`glossary.md` | 入库 | 项目总览、项目特有术语 |
| `rules/`、`decisions/`、`lessons/` | 入库 | 现行约束、决策（含放弃过的做法）、踩过的坑 |
| `local/` | 忽略 | 本机路径映射、缓存、任务草稿与运行证据 |

条目存在就表示它现在有效。决定改变时，正文改写为新结论，旧做法和放弃原因保留在“放弃过的做法”中。写作规范见[写作规范](skills/team-knowledge/references/writing.md)，成员使用方法见[成员操作说明](docs/member-guide.md)。

## 安装与开始

按[安装与升级](docs/install.md)用固定发行标签安装全部技能。下面以 `tw` 代表 `python3 ~/.agents/skills/team-knowledge/scripts/tw.py`。

```bash
tw init --apply --guidance        # 新项目：建立 .tw/ 与 AGENTS.md 中的知识指引
tw brief --task "<任务>" --path <相关路径>
tw check                          # 结构检查，零写入
tw team project                   # 团队流程：核对配置、知识与安装
```

- 已有 `.codestable/` 的项目按[迁移指南](skills/team-knowledge/references/migration.md)由代理整理。
- 团队流程的接入见[接入指南](skills/team-workflow/references/onboarding.md)，命令见[工具约定](skills/team-workflow/references/contracts.md)。
- 业务验收、回归、缺陷关联与每周复盘的共同标准见[业务验收与质量改进标准](skills/team-workflow/references/business-acceptance.md)。

## 维护与验证

MATT 基于 [mattpocock/skills](https://github.com/mattpocock/skills) 主分支提交 `b0618bc`，保留源码、配套资源和 MIT 许可；适配补丁可以反向恢复并逐文件校验，见[来源与更新](docs/upstream.md)。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/package.py --output <仓库外目录>/team-workflow.zip
```

[验收标准](docs/acceptance.md)区分自动化测试、隔离代理试用和真实成员试点，实际结果记录在[验证记录](docs/validation.md)；未执行的项目不得写成通过。工具只核对所列检查与材料，不替代业务判断。
