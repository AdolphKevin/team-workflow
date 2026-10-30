# 知识库验证记录

当前依据是[已批准方案](proposals/2026-10-22-knowledge-only.md)与[验收场景](sop/tw-knowledge-only.yaml)。[0.x 验证记录](archive/validation-0.x.md)仅说明旧版本的历史结果。

## TW-KO-1（1.0.0，2026-10-22）

依据：[已批准方案](proposals/2026-10-22-knowledge-only.md)；场景：[tw-knowledge-only.yaml](sop/tw-knowledge-only.yaml)（7 个节点、15 条场景）。

### 实现方自检

实现者 Codex 在交付前用自己派出的代理跑过全部场景，并在公开文本清理后再次全文复验。这些属于实现方自检，用于交付准备，不计入独立验收。

### 独立验收

执行者为主代理另行派出、未参与实现与审核的代理，经命令行真实入口在临时目录执行；SOP-04 使用 `claude -p --setting-sources project,local --strict-mcp-config` 的真实会话，只加载候选版 team-knowledge 与上游 mattpocock/skills `5beb35b` 的工程类技能。

| 轮次 | 被测提交 | 范围 | 结果 |
| --- | --- | --- | --- |
| 1 | `f13db5c` | 全部 15 条 | 14 条通过；SOP-03-N01 不通过：归档验证记录与历史方案中残留其他项目的单号、提交号与代码路径 |
| 2 | `7616804` | SOP-03-P01、N01 | P01 通过；N01 不通过：历史方案、旧版验证记录与发行技能 `references/writing.md` 中仍有其他项目的提交号、单号、代码路径与例外编号 |
| 3 | `55ef73b` | SOP-03-P01、N01，以及使用了被修改归档场景的 SOP-06-P01、N01 | 4 条通过；之后按复测意见泛化一处示例路径、修正两处空格（文本措辞，不改变场景输入） |

第 1 轮其余 14 条通过的场景，其输入在第 2、3 轮之间只有公开文本措辞变化；SOP-06 使用的归档场景文件被修改，因此在第 3 轮重跑。

### 未完成范围

- 远端 CI 在合并时运行；第 1 轮独立验收用 Python 3.13 与 uv 提供的 3.10.19 运行了发行检查与打包。
- 两位真实团队成员各自一周的试点尚未执行。
- 历史提交中的内部标识仍可在 Git 历史中查到；本次只清理当前版本，不改写历史（方案第 4 节）。

## 安装检查按 CLAUDE_CONFIG_DIR 核对（2026-10-30）

依据：[验收场景](sop/tw-knowledge-only.yaml)（metadata version 2）及其 `metadata.sources`：[已批准方案](proposals/2026-10-22-knowledge-only.md)第 3–6 节（修订 1），以及用户 2026-10-30 确认的补充要求。第二轮时该要求写为“安装检查另外核对 CLAUDE_CONFIG_DIR 指向的 Claude Code 技能目录，该目录缺少技能时提示；默认目录照常核对，未设置时行为不变”；第一轮时写为“安装检查按 CLAUDE_CONFIG_DIR 核对 Claude Code 的技能目录，该目录缺少技能时提示；未设置时行为不变”。范围是新增的 SOP-03-P02、N02、P03，以及受改动影响的 SOP-03-P01、SOP-03-N01、SOP-05-N01。

### 候选版

两轮都基于 `26e9922` 的未提交改动：修改 `docs/install.md`、`docs/sop/tw-knowledge-only.yaml`、`skills/team-knowledge/MANIFEST.json`、`skills/team-knowledge/scripts/tw_runtime/install.py`，新增 `.tw/lessons/2026-10-30-claude-config-dir-skills.md`。下表摘要均为 SHA-256，`git diff HEAD` 不含 docs/validation.md；每轮执行场景前后各计算一次，结果相同。

| 轮次 | `git diff HEAD` | 新增教训 | 发行 ZIP |
| --- | --- | --- | --- |
| 1 | `829e6021edf0f668b57894f0acc368d198d627a582faec072bc66d672a723e37` | `263bae4b3b6a8adfefd8f96d0ba098eb311d66d529c2877b5f9f0066c79768e4` | `d710b26b8257ea293cb582976f4236281a1b84bbb7f85b9db72581bf97716531` |
| 2 | `71c51a95ec12881d9de67c8aa95543abe5e57d71e958bc2098ee9bc74758a9a3` | `7cc47f2f4e8cf4a41f303145fc3a954613528124011497cb4c3c551d4033e459` | `db33797ec023f044efc149d0885b9ca334c5401a4802692577e72b93db2131d8` |

第二轮的临时检出另含当时的本记录（docs/validation.md 为第一轮写入后的内容，SHA-256 `e71c08d6671de5667ae967c4db8d2043bff6a76e2c7b18332b9cf62fb846668e`）。

### 实现方自检

实现者（主代理）交付前做过自检，不计入独立验收。

### 独立验收

执行者为主代理另行派出、未参与实现与审核的 Claude 代理，两轮做法相同，经命令行真实入口在仓库外的临时目录执行：

- 干净检出：把本仓 clone 到临时目录，套用当轮的 diff 与新增文件后 `git add -A`，不提交；暂存区相对 `26e9922` 的 diff 摘要与上表一致。
- 候选版技能取自该检出打出的 ZIP，每条场景复制到各自的临时 HOME 的 `.agents/skills/`，运行其中的 `scripts/tw.py`。
- 每次安装检查都显式写 `env CLAUDE_CONFIG_DIR=<临时配置目录>` 或 `env -u CLAUDE_CONFIG_DIR`，并传 `--home <临时 HOME>`。真实用户目录未参与；未启动 Claude 或 Codex 会话，未联网。
- 每次安装检查前后，对临时 HOME、配置目录与工作目录记录快照（路径、类型、链接目标、大小、SHA-256、权限、修改时间），前后全部相同。
- 本机 Python 3.13.14；发行检查与打包另用 uv 已安装的 Python 3.10.19 各运行一次。完整 JSON 输出与快照留在执行者本机临时目录，下表摘录关键字段。

| 轮次 | 范围 | 结果 |
| --- | --- | --- |
| 1 | 6 条；当时 SOP-03-P02 为两步 | 6 条通过。补充观察：设置 `CLAUDE_CONFIG_DIR` 时安装检查只核对该目录，同一临时 HOME 的 `.claude/skills` 中的改动副本未报告（退出 0）。主代理判定为缺陷并修复，SOP-03-P02 增加第 3 步覆盖这一情形 |
| 2 | 6 条全部重跑；SOP-03-P02 为三步 | 6 条通过，证据见下表 |

第二轮各场景：

| 场景 | 结果 | 实际操作与关键证据 |
| --- | --- | --- |
| SOP-03-P01 | 通过 | `check_release.py` 在 3.13 与 3.10 下均退出 0（`ok: true`，94 个源文件，文档检查 0 错误）；`package.py --output <仓库外>` 均退出 0，63 个文件，两次 ZIP 摘要相同，条目清单与第一轮相同。ZIP 的技能目录只有 `team-knowledge`，与检出中的技能逐文件相同；没有 `skills/team-workflow`、`playwright-acceptance`、`matt-*`、`upstream/`（包根目录 `team-workflow/` 是保留的插件名）。ZIP 技能装入临时 HOME 后，`env -u CLAUDE_CONFIG_DIR … version --check-install --home <临时 HOME>` 退出 0，`ok`、`installed_ok` 为 true，`integrity.status` 为 `intact`，`other_copies` 与两类问题为空；另放 `team-workflow`、`playwright-acceptance`、`matt-tdd` 占位技能和 `.claude/skills` 链接后重跑，结果相同，输出未提及这些技能。`plugin.json`、`.claude-plugin/plugin.json`、`VERSION`、运行时 `VERSION`、`MANIFEST.json` 均为 1.0.0 |
| SOP-03-N01 | 通过 | 在检出的 94 个已跟踪文件（含新增教训与本记录）与解压后的 63 个 ZIP 文件（含本记录）中，按内部仓库名与项目名（含执行机上同级的内部仓库名）、个人用户名、个人邮箱、个人本机绝对路径、真实站点与内网地址、`#数字` 与工单式编号、提交号检索。内部组织名只出现在 format 标识中（`.tw/config.json`、运行时 `FORMAT`、方案与场景对该标识的描述）；本机路径类检索只命中 `scripts/check_release.py` 中检测本机路径的规则文本；URL 为本仓公开地址、公开上游项目、示例地址，以及插件 schema、SVG 命名空间与历史方案引用的第三方公开地址；编号为本仓公开 Issue 与 PR、上游公开 Issue 与标明的示例编号；提交号均属本仓或方案文首列出的公开上游基线，另有示例占位。相对 `26e9922` 新增的 131 行（含本记录）没有内部标识 |
| SOP-05-N01 | 通过 | 在 README.md、AGENTS.md、docs/design.md、docs/install.md、docs/member-guide.md、docs/acceptance.md 与 skills/team-knowledge 中检索 `tw team`、`team-workflow`、`matt-`、`playwright-acceptance`、`checks`、`acceptance_entries`，命中清单与第一轮相同。文档中的 `tw team`（2 处）、`matt-`、`playwright-acceptance`、`checks`（2 处）、`acceptance_entries` 都在 install.md“从 0.x 升级”一节；`team-workflow` 是仓库名、插件名、发行包文件名、指引块标记、旧目录迁移说明，以及升级步骤中移除旧技能；运行时命中是格式标识、团队命令的移除提示链接、旧字段去向提示、旧字段与旧目录清单、工具版本号检查规则和英文注释中的普通词 checks。以上命中都属于升级说明、名称标识、指引标记或去向提示；install.md 新增段落与 install.py 改动没有命中 |
| SOP-03-P02 | 通过 | 临时 HOME 没有 `.claude/skills`，目录 A 的副本改动了 `SKILL.md`。第 1 步 `env CLAUDE_CONFIG_DIR=<目录 A> … version --check-install --home <临时 HOME>` 退出 1，`other_copies` 只有目录 A 的副本（`modified`，改动 `SKILL.md`），问题为“`<目录 A>/skills/team-knowledge` 的文件被改动：改动 SKILL.md”。第 2 步把副本换成指向 `<临时 HOME>/.agents/skills/team-knowledge` 的链接，退出 0，`installed_ok` 为 true，问题为空。第 3 步变量仍指向目录 A，在 `<临时 HOME>/.claude/skills` 放入改动了 `references/writing.md` 的副本，退出 1，问题为“`<临时 HOME>/.claude/skills/team-knowledge` 的文件被改动：改动 references/writing.md” |
| SOP-03-N02 | 通过 | 临时 HOME 的 `.claude/skills/team-knowledge` 是指向 `.agents` 副本的完好链接，目录 B 的 `skills/` 为空。`env CLAUDE_CONFIG_DIR=<目录 B> …` 退出 1；放入指向不存在路径的链接后重跑，仍退出 1。两次的问题均为“`<目录 B>/skills/team-knowledge` 不存在或链接失效：CLAUDE_CONFIG_DIR 指向的 Claude Code 读不到 team-knowledge，把 `<临时 HOME>/.agents/skills/team-knowledge` 链接到这里” |
| SOP-03-P03 | 通过 | `env -u CLAUDE_CONFIG_DIR`。临时 HOME 没有 `.claude/skills` 时退出 0，问题为空，输出中没有 Claude Code 技能目录的提示；在 `<临时 HOME>/.claude/skills` 放入改动了 `references/writing.md` 的副本后重跑，退出 1，问题为“`<临时 HOME>/.claude/skills/team-knowledge` 的文件被改动：改动 references/writing.md” |

补充观察（第二轮，不计入场景结论）：

- 对照：SOP-03-P03 两步的布局下，第二轮候选版的输出与 `26e9922` 旧版在路径归一后逐字段相同。SOP-03-P02 第 3 步的布局下，第一轮候选版退出 0、问题为空，第二轮候选版退出 1。第一轮对照中，旧版在 SOP-03-P02、N02 第 1 步的布局下均退出 0。
- 按 docs/install.md 的两条链接命令（`HOME` 指向临时 HOME）给一个尚无 `skills/` 的配置目录建立链接：建立前检查退出 1 并提示缺少，建立后退出 0。
- 变量指向含改动副本的目录 A，同时 `<临时 HOME>/.claude/skills` 另有一份改动副本时，两份各报告一次，退出 1；变量指向 `<临时 HOME>/.claude` 且该处副本被改动时，只报告一次。
- 在候选检出运行 `tw check`：19 个条目，0 个错误，4 个警告（4 条既有教训没有 guards）。

### 未完成范围

- 未在真实 Claude Code 会话中验证技能加载：使用自定义 `CLAUDE_CONFIG_DIR` 并按安装说明链接后，会话的技能列表能否出现 team-knowledge 尚未核实。两轮都只核对了安装检查的命令行为与链接命令。
- 远端 CI 未运行；本机用 Python 3.13.14 与 3.10.19 运行了发行检查与打包。
- 候选版技能由发行 ZIP 复制到临时目录，未经 skills CLI（`npx skills add`）真实安装。
- 两轮都只执行上述 6 条场景，其余场景未重跑。
- 两位真实团队成员各自一周的试点仍待执行。
