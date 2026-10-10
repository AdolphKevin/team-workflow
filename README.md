# Team Workflow

团队共用开发标准，个人按任务选择开发方式。独立的技能仓库集中分发流程和工具，业务项目只保存配置、原文档、测试和经验。

任务开始通过 CS 读取项目知识，需求和协作信息沿用项目任务平台。按需要选择 MATT 方法，在交接时保留下一步和验证范围，交付时核对本地或持续集成证据并完成知识回写。成员可以使用不同模型、工具和开发方法。

| 职责 | 唯一维护位置 |
| --- | --- |
| 开发方法 | 本仓直接复用的 15 个 MATT 技能及原配套文件 |
| 工作流与检查工具 | 本仓 `skills/team-workflow` |
| 术语、架构决策、项目规则 | 业务仓已有 GLOSSARY、ADR、AGENTS 等原文 |
| 知识检索入口 | 独立 CS 的 `brief` 与 `documents read` |
| 进行中的需求、职责、依赖和交接 | 项目任务平台，首批支持 GitHub Issues |
| 任务结果、引用和新增经验 | 业务仓 `.codestable`，不复制原文正文 |
| 实际业务验证 | 业务仓的命令、测试和必要环境 |

按[安装与升级](docs/install.md)将同一插件安装到 Codex 或 Cursor，在新会话中使用 `$team-workflow` 或 `/team-workflow`。`plugin.json` 是插件入口，`skills/` 是完整技能集合；也可将这些技能作为一组安装，保留同级目录关系。不要只复制主技能，否则 MATT 配套方法无法定位。

CS 独立安装，测试版本及源码身份见 [依赖锁定](dependencies.json)。通过已安装技能发现 CS 路径，再传给 `--cs-skill` 或 `TEAM_WORKFLOW_CS_SKILL`。本仓不携带 CS 副本，不修改全局技能目录。

当前锁定 CS 2.1.0 的已公开提交；其主分支合并仍在[独立变更](https://github.com/AdolphKevin/codestable-compact/pull/1)中审查。使用锁定提交安装，不以 CS 主分支的旧版代替。

```bash
python3 <team-workflow技能目录>/scripts/workflow.py project --root <项目目录> --cs-skill <CS技能目录>
```

项目接入见[接入与升级](skills/team-workflow/references/onboarding.md)，命令见[工具约定](skills/team-workflow/references/contracts.md)。项目保留 `.team-workflow.json`、简短 AGENTS 入口和可选 CS 文档登记；升级通用工具只更新共享插件。原有检查、卡片编号和历史继续保留，普通技能升级不需要重建知识库。

MATT 基于 [mattpocock/skills](https://github.com/mattpocock/skills)，固定版本 1.3.1，保留 MIT 许可。技能正文及模板直接复用，适配差异可独立查看和核验，见[来源与更新](docs/upstream.md)。

开发者运行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/check_cs.py --cs-skill <独立CS源码或安装目录>/skills/cs
python3 scripts/package.py --output <仓库外目录>/team-workflow-0.4.0-rc.1.zip
```

[验收标准](docs/acceptance.md)区分自动化工具验证、隔离技能试用和真实团队试点。交付检查只证明记录与所列检查一致；它不签名、防伪或证明所有业务正确。真实数据库、场景审查和跨服务验证仍按项目风险执行。

本版本的实际结果见[验证记录](docs/validation.md)。

0.4 候选版新增 [任务接续与交接](skills/team-workflow/references/collaboration.md)、[外部验证结果](skills/team-workflow/references/external-results.md)和[可移植联合验收](skills/team-workflow/references/cross-repository.md)。工具仅生成平台更新草稿，发布沿用已有授权。Codex 与 Cursor 共用同一插件包；在途任务记录所用版本，升级不自动切换任务版本。
