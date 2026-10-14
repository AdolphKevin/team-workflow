# 安装与升级

Codex、Cursor 与 Claude Code 共用同一个完整的 `skills/` 目录，推荐通过 skills CLI 统一安装。Codex 与 Cursor 读取根目录 `plugin.json`，Claude Code 读取 `.claude-plugin/plugin.json`。两份清单只声明入口，名称、版本和描述保持一致，由 `scripts/check_release.py` 核对；各端不维护独立实现。

发行包包含：团队入口 `team-workflow`、知识入口 `team-knowledge`（唯一的 Python 运行时也在这里）、15 个 MATT 方法、适配补丁、许可和说明。业务配置与项目知识不放入发行包。

## 统一安装（推荐）

用 [skills CLI](https://github.com/vercel-labs/skills) 安装固定发行标签。Claude Code、Codex 与 Cursor 共用 `~/.agents/skills/` 下的同一份文件。

```bash
npx skills add AdolphKevin/team-workflow#<发行标签> -g --skill '*' --agent claude-code codex cursor
npx skills list -g            # 核对来源与安装位置
```

- 必须用 `--skill '*'` 安装全部技能。团队入口、知识入口和 MATT 方法之间通过同级目录的相对路径互相引用，CLI 不会自动补装依赖。
- 升级时显式选择新的发行标签，main 只用于开发；回退时重新安装上一个标签。
- 安装后运行 `python3 ~/.agents/skills/team-knowledge/scripts/tw.py version --check-install`，确认两个技能属于同一发行、文件未被改动。
- 从旧版本迁移时，先卸载 `cs` 和 `cs-analysis`：`npx skills remove -g cs cs-analysis`。

技能目录带有 `MANIFEST.json`，记录随发行的每个文件的指纹。已安装文件被修改、缺失或多出文件时，`tw team project` 与 `tw version --check-install` 会报告，团队流程的 `accept` 和 `verify` 拒绝执行。不要直接修改 `~/.agents/skills/` 下的文件；发现工具缺陷时在本仓修复并发布新标签。修改本仓技能后运行 `python3 scripts/package.py --manifest` 重新生成清单，`scripts/check_release.py` 会拒绝过期的清单。

## 插件方式（可选）

根目录 `plugin.json`（Codex、Cursor）与 `.claude-plugin/plugin.json`（Claude Code）仍作为插件入口保留。插件按客户端分别安装、分别固定版本，容易出现一端已升级、另一端未升级，因此不要与统一安装混用，否则同名技能会出现两份。

```bash
claude plugin marketplace add AdolphKevin/team-workflow
claude plugin install team-workflow@team-workflow
codex plugin marketplace add AdolphKevin/team-workflow --ref <发行标签>
codex plugin add team-workflow@team-workflow
```

格式依据 [Claude Code 插件文档](https://code.claude.com/docs/en/plugins)与 [Codex 官方插件文档](https://developers.openai.com/plugins/build/plugins)。本地试用可以不安装，直接以 `claude --plugin-dir <仓库目录>` 启动。

## 项目接入

- **全新项目**：运行 `tw init --apply`，填写 `.tw/overview.md`。
- **已有 `.codestable/` 或 `.team-workflow*` 的项目**：由代理按 team-knowledge 的迁移指南整理，用一个 PR 交给用户确认，不使用脚本。
- **独立调用 MATT**：只需要 `.tw/` 知识。
- **从 `team-workflow` 开始的任务**：还需要 `.tw/config.json` 中的团队字段，按[接入指南](../skills/team-workflow/references/onboarding.md)准备。实际命令见[工具约定](../skills/team-workflow/references/contracts.md)。

接入后，简单任务按 `start → run → review --submit → deliver --reason <理由>` 完成，中间由独立评审人填写自动生成的 review.md。中等以上任务先用 `approval-draft --reviewer <姓名> --mode plan` 取得方案批准；要更新知识时先 accept，通过后写知识并 tw check，再 deliver。之后各命令用 `--task <身份>` 补齐记录材料，显式路径仍可使用。升级后用 `status --task <身份>` 核对过期材料与下一步，用各命令的 `--help` 查参数；细节见[交付步骤](../skills/team-workflow/references/team-delivery.md)。

## 版本

- 只有两个版本轴：软件发行版本，以及项目的 `data_version`。没有破坏性变化时，升级技能不需要改动项目文件。
- 每次发行核对 [MATT 来源](../upstream/matt.lock.json)、适配补丁和许可，并发布升级说明与实际验收范围。
- 候选版可以试用。正式版仍要求两位真实成员双向接续；安装成功本身不证明这一点。
