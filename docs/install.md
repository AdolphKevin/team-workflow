# 安装与升级

Codex、Cursor 与 Claude Code 使用同一个完整 `skills/` 目录，推荐通过 skills CLI 统一安装。Codex 与 Cursor 读取根目录 `plugin.json`，Claude Code 读取 `.claude-plugin/plugin.json`；两份清单只声明入口，名称、版本和描述保持一致，由 `scripts/check_release.py` 核对。各端不维护独立实现。发行 ZIP 包含方法入口、MATT 方法、团队流程与验证工具、适配补丁、许可和说明；业务配置与知识不放入发行包。

## 统一安装（推荐）

用 [skills CLI](https://github.com/vercel-labs/skills) 一次安装全部技能，Claude Code、Codex 与 Cursor 共用
`~/.agents/skills/` 下的同一份文件，一条命令同时更新所有客户端。CS 使用同一种方式安装。

```bash
npx skills add AdolphKevin/codestable-compact -g --skill '*' --agent claude-code codex cursor
npx skills add AdolphKevin/team-workflow -g --skill '*' --agent claude-code codex cursor
npx skills update -g          # 以后升级
npx skills list -g            # 核对来源与安装位置
```

必须用 `--skill '*'` 安装全部 16 个技能：主技能与 MATT 方法通过同级目录的相对路径互相引用，只装主技能会找不到配套方法。
安装后在新会话中使用 `/team-workflow`（Codex 为 `$team-workflow`），或直接调用 `/matt-implement` 等方法。
`npx skills update` 跟随默认分支，推送到 `main` 即发布；锁文件 `~/.agents/.skill-lock.json` 记录实际安装的目录哈希，
工具版本以 `workflow.py version` 输出为准。

## 插件方式（可选）

根目录 `plugin.json`（Codex、Cursor）与 `.claude-plugin/plugin.json`（Claude Code）仍作为插件入口保留，
适合需要固定到发行标签的场景。插件按客户端分别安装、分别固定版本，容易出现一端已升级另一端未升级，
因此不要与上面的统一安装混用，否则同名技能会出现两份。

```bash
claude plugin marketplace add AdolphKevin/team-workflow
claude plugin install team-workflow@team-workflow
codex plugin marketplace add AdolphKevin/team-workflow --ref <发行标签>
codex plugin add team-workflow@team-workflow
```

格式依据 [Claude Code 插件文档](https://code.claude.com/docs/en/plugins)与 [Codex 官方插件文档](https://developers.openai.com/plugins/build/plugins)。
本地试用可以不安装，直接以 `claude --plugin-dir <仓库目录>` 启动。从统一安装改用插件前，先运行
`npx skills remove -g` 移除同名技能；反之先卸载各客户端插件与插件目录登记。

## CS 与项目接入

使用本包任何开发技能前，先独立安装 CS，并按 CS 自身要求完成项目知识初始化。仅建立空目录不算完成。缺少前提时，本包报告缺口，不代为安装、初始化或重建。

CS 独立安装并完成项目知识初始化。工具通过公开命令与返回字段校验能力，缺失时明确报告，不自动安装或重建。不锁定 CS 版本、提交或源码哈希。CI 获取默认分支做真实接口验证，实际提交只记录在验证材料中。源码更新不代表已创建发行标签、插件包或修改全局安装。

独立 MATT 调用无需 `.team-workflow.json`。从 `team-workflow` 开始的新任务默认进入团队流程，按[接入指南](../skills/team-workflow/references/onboarding.md)采用第四版配置与任务。运行 `workflow.py schema` 可直接找到随技能安装的模板；将发现的 CS 目录传给 `--cs-skill` 或 `TEAM_WORKFLOW_CS_SKILL`，用 `project` 检查配置和必要能力。实际命令见[第四版工具约定](../skills/team-workflow/references/contracts-v4.md)。第二、三版任务保留原记录与兼容接口，不自动转换为新版完成证明。

## 版本切换

0.6.0-rc.1 是第四版流程的候选版。新任务采用新规则，在途任务继续使用其格式、配置和方案版本；显式切换时保存历史材料，列出方案、批准和证据缺项，再生成新版记录。任务开始记录实际工作流与 CS 版本，不在一次检查执行期间替换工具。新增能力不要求重建知识库。

集中升级只更新共享插件与独立 CS。项目中的业务测试、原文登记和必要配置继续由所属项目维护。每次发行核对 [MATT 来源](../upstream/matt.lock.json)、适配补丁和许可，发布升级说明与实际验收范围。

候选版可以用于试用。正式版仍要求真实成员双向交接、业务联合验证和后续知识检索全部通过；安装成功本身不证明这些条件已经满足。
