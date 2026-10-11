# Team Workflow

本仓集中分发直接复用的 MATT 开发方法和可选团队工具。使用技能前，CS 已安装且项目已完成 CS 知识初始化；MATT 负责开发方法，CS 统一负责项目知识的读取与沉淀。

`team-workflow` 主技能按当前目标选择方法，也可以直接调用各个 MATT 技能。普通任务结束由 CS 完成知识记录。环境复盘和 CS 使用分析按需调用，不进入固定收尾流程。项目明确采用时，再启用交接、验证结果核对和跨仓交付工具。

| 职责 | 唯一维护位置 |
| --- | --- |
| 开发方法 | 本仓直接复用的 15 个 MATT 技能及原配套文件 |
| 方法选择与可选团队工具 | 本仓 `skills/team-workflow` |
| 术语、架构决策、项目规则 | 业务仓已有 GLOSSARY、ADR、AGENTS 等原文 |
| 知识读取与沉淀规则 | 独立 CS 及其开发方法组合约定 |
| 进行中的需求、职责、依赖和交接 | 项目任务平台，首批支持 GitHub Issues |
| 任务结果、引用和新增经验 | 业务仓 `.codestable`，不复制原文正文 |
| 实际业务验证 | 业务仓的命令、测试和必要环境 |

按[安装与升级](docs/install.md)用 `npx skills add AdolphKevin/team-workflow -g --skill '*' --agent claude-code codex cursor` 一次安装全部技能，Claude Code、Codex 与 Cursor 共用同一份文件，`npx skills update -g` 同时升级。在新会话中使用 `/team-workflow` 或 `$team-workflow`。必须安装完整技能集合，保留同级目录关系；只复制主技能会导致 MATT 配套方法无法定位。根目录 `plugin.json` 与 `.claude-plugin/plugin.json` 作为可选插件入口保留，不要与统一安装混用。

CS 独立安装，运行时通过公开命令和返回字段核对能力，不锁定版本或提交。各方法遵循[CS 接入约定](skills/team-workflow/references/matt-integration.md)。使用可选工具时，通过已安装技能发现 CS 路径，再传给 `--cs-skill` 或 `TEAM_WORKFLOW_CS_SKILL`。本仓不携带 CS 副本，不修改全局技能目录。

CI 获取 CS 默认分支验证真实接口，实际使用的提交只记入[验证记录](docs/validation.md)。MATT 来源锁定及补丁核验继续保留。

可选工具使用只读共享配置（格式 3）；本机位置与按任务分开的运行材料均被忽略。
多人进度独立追加，负责人确认交接。原文正文保持唯一，CS 的登记、任务记录和独立
经验分别存放，普通任务不改写共享目录或统计。

项目需要团队工具时，运行配置检查：

```bash
python3 <team-workflow技能目录>/scripts/workflow.py project --root <项目目录> --cs-skill <CS技能目录>
```

可选工具的使用见[团队协作与交付](skills/team-workflow/references/team-delivery.md)。需要按阶段推进需求、确认方案并判定 Issue 能否关闭时，显式开启[阶段流程](skills/team-workflow/references/stage-flow.md)。采用工具的项目保留 `.team-workflow.json` 和必要运行材料；普通 MATT 调用无需这些配置。升级通用工具只更新共享插件，原有检查、卡片编号和历史继续保留，普通技能升级不需要重建知识库。

MATT 基于 [mattpocock/skills](https://github.com/mattpocock/skills)，固定版本 1.3.1，保留 MIT 许可。技能正文及模板直接复用，适配差异可独立查看和核验，见[来源与更新](docs/upstream.md)。

开发者运行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/check_cs.py --cs-skill <独立CS源码或安装目录>/skills/cs
python3 scripts/check_parallel.py --cs-skill <独立CS源码或安装目录>/skills/cs
python3 scripts/package.py --output <仓库外目录>/team-workflow-0.5.0-rc.1.zip
```

[验收标准](docs/acceptance.md)区分自动化工具验证、隔离技能试用和真实团队试点。交付检查只证明记录与所列检查一致；它不签名、防伪或证明所有业务正确。真实数据库、场景审查和跨服务验证仍按项目风险执行。

本版本的实际结果见[验证记录](docs/validation.md)。

0.4 候选版新增 [任务接续与交接](skills/team-workflow/references/collaboration.md)、[外部验证结果](skills/team-workflow/references/external-results.md)和[可移植联合验收](skills/team-workflow/references/cross-repository.md)。工具仅生成平台更新草稿，发布沿用已有授权。Codex 与 Cursor 共用同一插件包；在途任务记录所用版本，升级不自动切换任务版本。
