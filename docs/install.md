# 安装与升级

本仓发行包只包含 `team-knowledge`、插件元数据、许可和公开说明。运行命令需要 Python 3.10+ 与 Git。项目知识和本机材料保存在各项目中。

## 安装知识技能

用 [skills CLI](https://github.com/vercel-labs/skills) 安装固定发行标签：

```bash
npx skills add AdolphKevin/team-workflow#<发行标签> -g --skill team-knowledge --agent claude-code codex cursor
npx skills list -g
python3 ~/.agents/skills/team-knowledge/scripts/tw.py version --check-install
```

新版本经发布后使用其标签；main 用于开发。安装检查只核对知识技能自身及客户端目录内的同名副本，报告文件缺失、修改、多余文件与版本差异。多端共用同一份技能时，不需要分别维护运行时。

Claude Code 从 `CLAUDE_CONFIG_DIR`（默认 `~/.claude`）下的 `skills/` 加载全局技能，skills CLI 只链接到安装当次该变量指向的目录。使用自定义 `CLAUDE_CONFIG_DIR` 的（如多个账号各用一个配置目录），把 `~/.agents/skills/team-knowledge` 链进 `$CLAUDE_CONFIG_DIR/skills`。链接指向同一份技能，升级后自动生效：

```bash
mkdir -p <配置目录>/skills
ln -s ~/.agents/skills/team-knowledge <配置目录>/skills/team-knowledge
```

在设置了 `CLAUDE_CONFIG_DIR` 的环境中，`version --check-install` 另外核对该目录；缺少技能或链接失效时报告安装问题。

也可使用客户端已有的插件安装工具，来源为本仓、版本固定到发行标签。根目录 `plugin.json` 与 `.claude-plugin/plugin.json` 的名称、版本和描述一致；插件名仍为 `team-workflow`。选择一种安装方式，避免客户端同时加载两份同名技能。

本地候选版可从发行 ZIP 解压 `skills/team-knowledge/` 到隔离技能目录，再用其中的 `scripts/tw.py version --check-install --home <临时用户目录>` 检查。修改源码后运行 `python3 scripts/package.py --manifest` 更新清单。

## 项目初始化

下文的 `tw` 表示 `python3 <team-knowledge 技能目录>/scripts/tw.py`。

```bash
tw init                         # 预览；缺 README 时用 --source self:文档路径
tw init --apply --guidance       # 写入后填写 .tw/overview.md
tw brief --task "<任务>" --path <相关路径>
tw check
```

初始化仅维护知识布局、AGENTS.md 的项目知识块与 CLAUDE.md 的引入块，保留成员自写内容。已有旧知识目录的项目按[迁移指南](../skills/team-knowledge/references/migration.md)逐条核实。

## 从 0.x 升级

升级依据为[已批准方案第 5 节](proposals/2026-10-22-knowledge-only.md#5-已采用-tw-的项目如何升级)。先保留旧版安装和项目材料，以便完成在途任务或回退。下列涉及成员文件的动作由使用者按实际来源与范围执行；新版知识命令不会代替使用者清理。

### 技能与指引

1. 升级前用旧版完成或明确放弃在途的 `tw team` 任务，`.tw/local/` 材料原样保留；之后是否删除由成员确认。
2. 用安装工具列出技能来源，例如 `npx skills list -g`；项目级安装用不带 `-g` 的列表。只移除来源确认为本仓的 `team-workflow`、`playwright-acceptance` 与 15 个 `matt-*` 副本。skills CLI 使用 `npx skills remove -g <逐个确认的技能名>`；项目级不加 `-g`。插件安装使用原客户端的卸载或升级入口。手动安装先按旧版清单比对，保留成员修改，再只删除确认属于旧包的目录。不要按通配符删除其他来源的技能。
3. 按上文只安装新版 `team-knowledge`。需要 MATT 时从 [mattpocock/skills](https://github.com/mattpocock/skills) 自行选择上游方法及固定版本，例如 `npx skills add mattpocock/skills#<提交或标签> -g --skill <所需方法>`。成员另行安装的技能保持原样。
4. 检查全局 `~/.codex/AGENTS.md`、`~/.claude/CLAUDE.md` 以及项目 AGENTS.md、CLAUDE.md。团队块以 `<!-- team-workflow:guidance:global start -->` / `<!-- team-workflow:guidance:global end -->`，或 `<!-- team-workflow:guidance:project start -->` / `<!-- team-workflow:guidance:project end -->` 标记。逐块审阅后，只删除这对标记及其间的团队文字；也可替换为 sop-board 已发行的推荐文字。块外自写内容逐字保留，块内成员补写内容先移出保存；标记不成对时人工修复，不推断删除范围。
5. 保留 `team-workflow:guidance:knowledge` 的项目知识块，以及只引入 AGENTS.md 的 `team-workflow:guidance:claude` 块。需要更新知识指引时运行 `tw init --apply --guidance`；它不修改全局文件或团队块。

### 配置与测试引用

`.tw/` 中的规则、决策、教训、概览与词汇仍可用，`format` 与 `data_version` 保持原值。升级本身保留配置字节；`tw check` 对以下旧字段逐项给警告，在知识本身无错时以 0 退出。需要搬迁的内容先在新位置核对，完成后由成员另行编辑配置。

| 旧内容 | 去向 |
| --- | --- |
| `checks`、`required_checks`、`risk_checks` | 运行命令与必跑用例移入产品仓库脚本和 CI。CI 须发现用例被跳过、数量为零、或声明的必跑用例未执行；覆盖说明留在对应规则或验证手册。确认后删除旧字段 |
| `platform`、`inputs`、`external_inputs`、`environment_versions`、`.tw/platform.py` | 只服务于已移除的团队流程，可由成员删除；本机映射中的旧 `inputs` 不参与知识解析 |
| `guards` 的 `check:名称` | 另行改写为 `仓库:文件#测试名`；引用只表示可追溯，运行由 CI 证明 |
| `acceptance_entries`、`accounts` | 操作、账号类别、隔离、清理写进产品仓库真实验证手册；sop-board 工作区 `entries` 按它自己的契约重新填写并引用手册章节，`surface` 使用其取值，长篇说明放手册 |
| 在途任务和 `.tw/local/` 材料 | 用旧版完成或放弃任务，保留原始材料，成员确认后再清理 |

新版 `tw team ...` 只返回“团队流程已移除”、方案公开链接和非零退出码，不写文件。知识命令不执行测试或平台脚本。`self:文件#测试名` 继续核对文件和名称存在，错误引用仍报错。

### 旧场景迁入 sop-board

在产品仓库保存一份整理副本，逐条保留原来的角色、前置状态、步骤、业务预期与禁止副作用，核对 sop-board 当前契约再登记。

- 主体字段按 sop-board 契约整理，不直接复制旧配置的入口对象；入口操作说明引用产品仓库真实验证手册。
- 旧 `regression: {manual, owner, trigger}` 的人工说明，移入该场景的 `expected`，或产品仓库验证手册的“人工范围”一节。保留人工原因、负责人、触发时机及已有步骤、证据要求，然后删除旧 `regression` 字段。
- 旧 `regression: {check, cases}` 指向的测试命令与用例，按上表 `checks` 的去向写进产品仓库脚本与 CI，覆盖说明写进验证手册；需要追溯时在相关知识条目的 `guards` 写 `仓库:文件#测试名`，然后删除旧 `regression` 字段。
- 例如原 `manual: 需观察外部邮件`、`owner: 测试成员`、`trigger: 通知规则变更时`，整理为 expected 中的“人工范围：需观察外部邮件；负责人：测试成员；触发时机：通知规则变更时”，或等义的手册段落。不要把说明搬迁变成放宽业务预期。
- 把整理副本登记到已安装的 sop-board 工作区，按其帮助执行场景校验或 `sop-board check`，保留前后差异与输出。验收记录只有实际运行后才能填写通过。

本仓旧场景在 `docs/sop/archive/`，可用于隔离迁移练习；本仓自身的验收仍由独立代理直接执行当前场景，不接入 sop-board。
