# Team Workflow

本仓集中维护团队工作流程、直接复用的 MATT 开发方法和验证工具。使用前独立安装 CS，并完成项目知识初始化。

用 `team-workflow` 开始新任务，默认进入团队流程：评估、分节方案、评审、实施与交接、业务验收、知识回写和最终交付。简单任务可以先实施，再由具体评审人一并批准方案和代码；中等、复杂任务先批准方案再实施。复杂度与风险分别判断，简单任务涉及接口、数据库或权限时仍保留合并评审路径，并完成相应真实验证。

直接调用 MATT 方法保持轻量，不要求团队配置。已经进入团队流程的任务，切换方法继续沿用其有效批准、验收与交接要求。已有批准且已指派的任务，接手者核对共享材料后即可实施；批准范围内不重复请求开工确认。

| 内容 | 维护位置 |
| --- | --- |
| 开发方法 | 15 个 MATT 技能及配套资源 |
| 任务流程与验证工具 | `skills/team-workflow` |
| 业务验收、有效回归、缺陷关联与每周质量复盘 | [共同标准](skills/team-workflow/references/business-acceptance.md) |
| 为各项目设计匹配的验收方式、过渡状态与按需建设 | [项目验收方式与测试能力建设](skills/team-workflow/references/test-capability.md) |
| 可填写的团队记录 | [项目验收方案](skills/team-workflow/templates/project-verification.md)、[交付验收](skills/team-workflow/templates/business-delivery.md)、[缺陷复验与保护](skills/team-workflow/templates/defect-protection.md)、[每周质量复盘](skills/team-workflow/templates/weekly-quality-review.md) |
| 术语、架构决策和项目规则 | 所属项目已有原文，通过独立 CS 登记与读取 |
| 方案、职责、进度和交接 | 共享任务材料，首批支持 GitHub Issues |
| 最终任务记录与可复用经验 | 所属项目的 CS 知识库 |
| 业务命令、测试及环境准备 | 业务仓库 |

## 安装与开始

按[安装与升级](docs/install.md)安装完整技能集合，保留同级目录关系。新会话中使用 `/team-workflow` 或 `$team-workflow`；直接调用 MATT 时沿用同一份 CS 接入约定。

```bash
npx skills add AdolphKevin/codestable-compact -g --skill '*' --agent claude-code codex cursor
npx skills add AdolphKevin/team-workflow -g --skill '*' --agent claude-code codex cursor
```

项目使用 `schema_version: 5` 的配置与任务格式，工具生成的本地证据使用 `schema_version: 6`。从已安装技能获得模板和字段说明：

```bash
python3 <team-workflow技能目录>/scripts/workflow.py schema --root <项目目录>
python3 <team-workflow技能目录>/scripts/workflow.py project --root <项目目录> --cs-skill <CS技能目录>
python3 <team-workflow技能目录>/scripts/workflow.py guidance --root <项目目录> --apply
```

`guidance` 把“团队开发流程、需求完成门槛、安全边界”写入项目的 AGENTS.md，CLAUDE.md 只保留一行 `@AGENTS.md`
引用，项目规则统一在 AGENTS.md 维护；再把“需求交付与验收”写入本机 `~/.claude/CLAUDE.md` 与 `~/.codex/AGENTS.md`。
只维护标记块，每位成员安装后得到相同内容。

首次接入读[接入指南](skills/team-workflow/references/onboarding.md)，日常任务读[团队协作与交付](skills/team-workflow/references/team-delivery.md)。团队任务、业务验收、自动回归、缺陷处理、每周质量复盘及多代理派遣均读取[业务验收与质量改进标准](skills/team-workflow/references/business-acceptance.md)，按其中相应章节和模板执行；正文统一维护，不在各入口复制。实际命令和记录格式读[工具约定](skills/team-workflow/references/contracts.md)。

## 0.7.0-rc.1 候选版

工具核对主需求业务场景及其业务来源、具体验证范围、验收人独立性、已知问题处置、回归
自动化状态和知识验收引用。`knowledge-template` 通过 CS 的公开接口生成进度或完成草稿。工具继续只读连接 CS，实际写入遵循 CS 的预览与应用流程。

检查仍可在多任务间复用，业务验收与知识完成分开。实现前核对实际准备状态，交接保留
原始验证材料及未决问题，报告明确区分子任务与主需求。自动化和隔离代理试用用于工程
候选版验证；正式推广仍需两位真实成员双向接续，结果见[验证记录](docs/validation.md)。

## 维护与验证

MATT 基于 [mattpocock/skills](https://github.com/mattpocock/skills) 1.3.1，保留源码、配套资源和 MIT 许可；适配补丁可反向恢复并逐文件校验，见[来源与更新](docs/upstream.md)。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/check_cs_knowledge.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/check_cs_delivery.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/check_parallel.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/package.py --output <仓库外目录>/team-workflow-0.7.0-rc.1.zip
```

[验收标准](docs/acceptance.md)区分自动化测试、隔离技能试用和真实成员试点。实际结果记录在[验证记录](docs/validation.md)，未执行项目不得写成通过。工具核对所列检查与材料，不替代业务判断，也不把未签名的本地文件当成防伪证明。
