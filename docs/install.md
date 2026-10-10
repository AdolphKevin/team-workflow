# 安装与升级

Codex、Cursor 与 Claude Code 使用同一个完整 `skills/` 目录。Codex 与 Cursor 读取根目录 `plugin.json`，Claude Code 读取 `.claude-plugin/plugin.json`；两份清单只声明入口，名称、版本和描述保持一致，由 `scripts/check_release.py` 核对。各端不维护独立实现。发行 ZIP 包含方法入口、MATT 方法、可选团队工具、适配补丁、许可和说明；业务配置与知识不放入发行包。

## Codex

在支持插件的 Codex 中登记本仓提供的插件目录，固定到候选版标签，再安装：

```bash
codex plugin marketplace add AdolphKevin/team-workflow --ref v0.4.0-rc.1
codex plugin add team-workflow@team-workflow
```

在新会话中使用 `$team-workflow`。如果客户端尚未支持这些命令，先更新客户端；也可以通过客户端的插件来源界面登记同一个 Git 仓库和版本。仓库中的 `.agents/plugins/marketplace.json` 是目录入口，根目录的 `plugin.json` 是插件入口。格式依据 [Codex 官方插件文档](https://developers.openai.com/plugins/build/plugins)。

## Claude Code

在 Claude Code 中登记本仓作为插件目录，再安装插件：

```bash
claude plugin marketplace add AdolphKevin/team-workflow
claude plugin install team-workflow@team-workflow
```

在新会话中使用 `/team-workflow`，或直接调用 `/matt-implement` 等各个 MATT 技能。仓库中的 `.claude-plugin/marketplace.json` 是目录入口，`.claude-plugin/plugin.json` 是插件入口，Claude Code 自动发现插件根目录下的 `skills/`。本地试用可以不登记目录，直接以 `claude --plugin-dir <仓库目录>` 启动。固定版本时在 `marketplace add` 后用 `claude plugin marketplace update` 跟随目录更新；升级插件用 `claude plugin update team-workflow@team-workflow`。格式依据 [Claude Code 插件文档](https://code.claude.com/docs/en/plugins)。

## Cursor

从本仓 Releases 下载同一版本的 ZIP 并核对发行校验值。将包内完整的 `team-workflow` 目录放到 `~/.cursor/plugins/local/team-workflow`，重新加载窗口或新开项目，在新会话中确认 `/team-workflow` 出现在技能选择中。使用实际目录，不以指向其他目录的符号链接代替。插件格式见 [Cursor 官方文档](https://cursor.com/docs/plugins)。

安装时若已有同名目录，先备份旧版本再替换；不要混合两个发行版的文件。插件安装不要求把脚本复制到业务项目。

## CS 与项目接入

使用本包任何开发技能前，先独立安装 CS，并按 CS 自身要求完成项目知识初始化。仅建立空目录不算完成。缺少前提时，本包报告缺口，不代为安装、初始化或重建。

CS 独立安装并完成项目知识初始化。工具通过公开命令与返回字段校验能力，缺失时明确报告，不自动安装或重建。不锁定 CS 版本、提交或源码哈希。CI 获取默认分支做真实接口验证，实际提交只记录在验证材料中。源码更新不代表已创建发行标签、插件包或修改全局安装。

普通 MATT 调用无需 `.team-workflow.json`。项目明确采用团队工具时，再按[接入指南](../skills/team-workflow/references/onboarding.md)配置，将发现的 CS 目录传给 `--cs-skill` 或 `TEAM_WORKFLOW_CS_SKILL`，用 `project` 检查配置。共享项目配置使用格式 3，旧配置明确拒绝；协作记录及可移植结果也使用第三版；具体命令见[工具约定](../skills/team-workflow/references/contracts.md)。

## 版本切换

任务开始记录工作流版本、源码身份和 CS 版本。正在进行的任务继续使用原版本；需要升级时，在同一任务中明确记录切换，并重新检查旧证据是否仍适用。不要在一次检查执行期间替换插件文件。

集中升级只更新共享插件与独立 CS。项目中的业务测试、原文登记和必要配置继续由所属项目维护。每次发行核对 [MATT 来源](../upstream/matt.lock.json)、适配补丁和许可，发布升级说明与实际验收范围。

候选版可以用于试用。正式版仍要求真实成员双向交接、业务联合验证和后续知识检索全部通过；安装成功本身不证明这些条件已经满足。
