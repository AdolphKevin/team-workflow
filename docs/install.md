# 安装与升级

Codex 与 Cursor 使用同一个 `plugin.json` 和完整 `skills/` 目录。两端不维护独立实现。发行 ZIP 包含工作流、MATT 方法、适配补丁、许可和说明；业务配置与知识不放入发行包。

## Codex

在支持插件的 Codex 中登记本仓提供的插件目录，固定到候选版标签，再安装：

```bash
codex plugin marketplace add AdolphKevin/team-workflow --ref v0.4.0-rc.1
codex plugin add team-workflow@team-workflow
```

在新会话中使用 `$team-workflow`。如果客户端尚未支持这些命令，先更新客户端；也可以通过客户端的插件来源界面登记同一个 Git 仓库和版本。仓库中的 `.agents/plugins/marketplace.json` 是目录入口，根目录的 `plugin.json` 是插件入口。格式依据 [Codex 官方插件文档](https://developers.openai.com/plugins/build/plugins)。

## Cursor

从本仓 Releases 下载同一版本的 ZIP 并核对发行校验值。将包内完整的 `team-workflow` 目录放到 `~/.cursor/plugins/local/team-workflow`，重新加载窗口或新开项目，在新会话中确认 `/team-workflow` 出现在技能选择中。使用实际目录，不以指向其他目录的符号链接代替。插件格式见 [Cursor 官方文档](https://cursor.com/docs/plugins)。

安装时若已有同名目录，先备份旧版本再替换；不要混合两个发行版的文件。插件安装不要求把脚本复制到业务项目。

## CS 与项目接入

CS 独立安装，版本和源码提交固定在 [dependencies.json](../dependencies.json)。0.4 候选版使用 CS 2.1.0、知识格式 4；依赖的提交已公开，合并状态见 [CS 变更](https://github.com/AdolphKevin/codestable-compact/pull/1)。将该提交中的 `skills/cs` 目录作为 `--cs-skill`，或设置 `TEAM_WORKFLOW_CS_SKILL`。不要用旧版全局 CS 代替锁定版本。

运行主技能提供的 `project` 命令检查项目配置和 CS。已有第二版 `.team-workflow.json` 继续可读，旧执行记录按原范围解释；新协作记录和可移植结果使用第三版，不要求逐仓重写配置。具体命令见[工具约定](../skills/team-workflow/references/contracts.md)。

## 版本切换

任务开始记录工作流版本、源码身份和 CS 版本。正在进行的任务继续使用原版本；需要升级时，在同一任务中明确记录切换，并重新检查旧证据是否仍适用。不要在一次检查执行期间替换插件文件。

集中升级只更新共享插件与独立 CS。项目中的业务测试、原文登记和必要配置继续由所属项目维护。每次发行核对 [MATT 来源](../upstream/matt.lock.json)、适配补丁和许可，发布升级说明与实际验收范围。

候选版可以用于试用。正式版仍要求真实成员双向交接、业务联合验证和后续知识检索全部通过；安装成功本身不证明这些条件已经满足。
