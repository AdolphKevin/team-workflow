# 工具约定

## 工具做什么

工具读取配置、任务、方案、场景文件和平台记录，核对材料与绑定，运行登记的检查，登记场景轮次，生成草稿和报告，报告 `closable` 等结论。发布评论、提交、推送、合并、关闭任务、修改安装文件，由成员按自己的授权执行；平台只读。

项目配置是 `.tw/config.json`，本地证据放在被 Git 忽略的 `.tw/local/`。配置、任务、方案、平台记录和本地证据统一使用 `data_version: 1`。运行环境为 Python 3.10+、Git 和项目自身的测试依赖，通用工具使用标准库。

下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`，团队命令写作 `tw team <命令>`；`$PROJECT` 是项目目录，`$TASK_ID` 是任务 `id`（本地编号或完整 Issue 地址），`$TASK` 是首次开工的任务文件。输入路径相对项目，输出路径以返回的 `artifact.path` 为准。默认返回 JSON，`--format text` 用于阅读；下一步由 `error_code` 决定。

全局参数 `--root` 和可重复的 `--repository` 可写在团队子命令前后，也可由外层 `tw` 转发。其余参数写在对应命令之后：`tw team --help` 列出命令，`tw team <命令> --help` 列出可用参数。例如 `tw team --root "$PROJECT" run --task "$TASK_ID" --check unit`；业务验收用 `accept`，最终交付用 `verify`。

## 配置与任务

```bash
tw team schema --root "$PROJECT"
tw team project --root "$PROJECT"
tw init --root "$PROJECT" --guidance [--apply]
tw team guidance --root "$PROJECT" [--scope project|global|all] [--file AGENTS.md] [--apply]
```

`project` 核对安装完整性：`installation.integrity.status` 为 `intact`、`modified`（列出 `changed`、`missing`、`unexpected`）或 `unknown`（缺少 `MANIFEST.json`）。正在运行的两个技能完整且属于同一发行时，`accept` 和 `verify` 可执行；其余情况返回 `error_code: tool-modified`。客户端目录中其他副本的修改、版本差异及残留技能 cs 列在 `warnings`。发现工具缺陷时报告并重装；确需带改动运行时加 `--allow-modified-tool`，结果中的 `tool.override` 为真并随记录保留。`project` 同时报告配置校验、`tw check` 错误数和发行核对结果（`tw version --check-install`）。工具自身缺陷返回 `error_code: tool-defect`，保留请求目录。

项目配置的 `data_version` 高于工具支持的版本时，按[接入指南](onboarding.md#更新与回退)更新技能。

`tw init --guidance` 维护 AGENTS.md 中的知识指引块；`tw team guidance` 默认预览，`--apply` 写入标记块：项目指令文件使用[项目指引](../templates/guidance-project.md)，本机 Claude Code 与 Codex 用户级文件使用[全局指引](../templates/guidance-global.md)。项目规则写入 `AGENTS.md`，缺文件时新建；缺少 `CLAUDE.md` 时新建并放入 `@AGENTS.md` 引用（[引用模板](../templates/guidance-claude.md)），已有 `@AGENTS.md` 或 `@./AGENTS.md` 时保留。`--file` 接受仓内相对路径，引用随之指向该文件。每个目标的 `action` 为 `create`、`append`、`update`、`unchanged`、`skipped`（客户端目录缺失）或 `blocked`（标记损坏，整次拒绝写入）。写入保留换行风格、权限和符号链接。试验时用 `--home` 指向替代用户目录。`schema` 返回[团队配置模板](../templates/config.json)、[任务模板](../templates/task.json)和[方案模板](../templates/design.md)。按项目填写模板，将团队字段写入 `.tw/config.json`，手工任务输入和运行材料放在 `.tw/local/`。

| 配置字段 | 含义 |
| --- | --- |
| `format`、`data_version`、`project` | `tw init` 生成的工具标识、数据版本 1、`{id, name}` 项目身份 |
| `context` | 必须读取的现有仓内文件 |
| `shared`、`documents` | 共享知识仓与原文登记，见[知识写作规范](../../team-knowledge/references/writing.md) |
| `checks` | 检查编号到命令、报告格式、用例及环境要求的映射 |
| `required_checks` | 为 `code`、`docs` 指定默认检查 |
| `risk_checks` | 风险到非空检查集合；缺少风险映射时报错 |
| `inputs` | 参与结果但被 Git 忽略的文件或目录 |
| `external_inputs` | 逻辑依赖及用途，本机位置另行提供 |
| `environment_versions` | 名称到只读版本查询命令数组 |
| `acceptance_entries` | 验收入口，见[场景与证据](#场景与证据) |

检查包含 `argv` 参数数组、`purpose`、仓内 `cwd`、秒数 `timeout`、`format`、`required_cases`、`required_env` 和 `environment`。命令直接启动进程，凭证通过环境传递，记录必要变量名；日志遵循项目脱敏规则。本地与可携带记录的 `argv` 保存含 `{output}` 的配置模板，启动进程时展开为绝对路径；输出目录由 `stdout.txt` 等产物的相对路径确定。

`format` 为 `command`、`go-json` 或 `junit`。`command` 记录命令退出结果；Go 解析 `go test -json`；JUnit 使用 `report: "{output}/results.xml"`，命令生成本次运行的新报告。逐项报告的通过条件：用例数大于零，全部发现的用例为通过或跳过，必要用例齐全并通过。`required_cases` 指定必要用例，名称为准确的 `包::测试名` 或 `classname::name`；空数组表示全部发现的用例均为必要用例。Go 的必要父用例另要求其子用例全部通过。额外产物放在 `{output}/` 内；证据含义见[业务验收术语](business-acceptance.md#1-术语)。

`environment` 写 `{"kind":"stateless"}`（检查独立于可变外部数据），或 `{"kind":"fixture","identity":["业务仓的只读命令","参数"]}`（表达服务、数据库或夹具状态）。身份核对成功后复用结果。`revision_sensitive: true` 用于依赖 Git 提交编号的检查。

任务包含 `data_version: 1`、`id`、真实存在的完整基准提交 `base`、`goal`、`non_goals`、`kind`（`code` 或 `docs`）、`risks`、`acceptance`、`design_id`、非空任务节数组 `section_ids` 和 `acceptance_scope`（主需求 `requirement`，子任务 `task`）。子任务的 `parent` 指向方案所属主需求。本地文件和平台任务块的验收均写 `[{"id":"A1"}]`；带正文或检查清单时返回“验收项只写编号，内容以方案为准”。读取后按所选方案展开 `expectation` 和 `checks`，子任务使用父方案；完整副本留在上下文，需求摘要与 `requirements_signature` 按编号计算。`paths`、`symbols`、跨仓 `scopes` 提供知识读取范围。

风险支持 `authorization`、`persistence`、`concurrency`、`messaging`、`public-contract`、`cross-service`。任务评估、批准路径和方案格式见[分节方案](designs.md#内容与依赖)。

## 开工材料、状态与方案

```bash
tw team start --root "$PROJECT" --task "$TASK" --design "$DESIGN"
tw team start --root "$PROJECT" --task "$TASK_ID"
tw team status --root "$PROJECT" --task "$TASK_ID" --format text
```

平台任务也可用 `start --issue <完整Issue链接>` 读取任务和方案。已有批准用可重复的 `--approval`，历史方案用可重复的 `--design-history`，从修订 1 保留完整快照。平台读取失败时报告缺口。请求的 Issue 缺少任务块时返回 `issue-not-adopted`；子 Issue 引用的父 Issue 缺块时返回 `parent-issue-not-adopted`，并给出父地址及 `issue-draft --task <parent-task.json>` 补齐命令。

`start` 首次建立上下文，返回 `continued: false`；任务、方案、批准、历史、前序依赖或授权变化时建立新上下文，`superseded_context` 指向原记录。输入相同返回 `continued: true`，核对接续条件，在自己的请求目录保存本次简报和 `start.json`。省略方案或批准时沿用原准备材料；同一任务的本机授权继续有效。平台任务首次可用 `--issue`，之后可用 `--task <完整 Issue 地址>`。

两种结果均含身份、任务目录、`context.path`、实施条件、缺口和 `next_step`。`pending_sections` 按文档顺序列编号、标题和原因，含所需章节、依赖与待确认删除；`next_action` 给批准命令，子任务指向持有方案和批准的父任务。阅读返回的简报；后续用身份或 `--context` 补材料。新批准用 `start --approval` 建新上下文；实施后也可传给 `review`、`accept`、`delivery-template`，保留开工简报。历史用 `--design-history`。`status` 从当前材料组或显式 `--context`、`--report` 读取批准。

### 当前材料组

任务目录的 `current.json` 使用 `data_version: 1`、`kind: current-materials`，每项材料为 `{path, sha256}`：

| 字段 | 材料 |
| --- | --- |
| `context`、`task`、`design`、`brief` | 准备上下文、补全的任务、方案、开工简报 |
| `design_history`、`approvals` | 方案历史和批准列表 |
| `runs` | 本上下文的全部运行，含失败运行 |
| `review`、`acceptance` | 验收所用评审、通过的业务验收记录 |
| `review_markdown`、`review_source` | 可选：提交成功的评审原文、提交时的源码逐文件指纹 |
| `case_imports`、`case_coverage`、`scenario_rounds` | 可选：用例导入列表、覆盖配对文件、场景轮次列表 |
| `delivery_report`、`delivery` | 交付报告、通过的最终交付记录 |

`start` 新上下文重建准备与交付材料，保留用例导入、覆盖配对和场景轮次；接续保留当前组。`run` 追加实际运行，含失败结果；其他材料在相应命令成功后更新。批准首次显式指定；评审成功提交后登记。`selected_runs` 记录显式选用的运行，`runs` 保存全部历史；新运行追加后从全部记录选取。写入使用临时文件加改名，与清理共用锁；并发开工冲突时换请求编号重试。

`run`、`status`、`review`、`approval-draft`、`accept`、`delivery-template`、`verify`、`handoff`、`progress`、`task-export` 支持任务身份、任务文件和显式路径。命令补齐自身使用的材料；`verify` 读取交付报告，`delivery-template` 带上验收记录。显式材料优先，成功使用后登记；同身份显式切换上下文会换组并清除下游材料，跨身份上下文拒绝。

记录缺失或指纹变化时，结果点名材料并给出修正命令。平台方案或批准更新时重新 `start`；`status` 列出受影响的过期步骤。自动和显式材料一起参与请求指纹，同一请求编号对应固定输入，重复成功请求复用原结果。仅用身份查看 `status` 时只读；显式替换经核对成功后更新记录。

```bash
tw team design-diff --root "$PROJECT" --task "$TASK" --design "$NEW_DESIGN" \
  --design-history "$V1" --design-history "$V2"
```

`design-diff` 比较历史末版和当前版，保留完整删除历史。`status` 和接续的 `start` 汇总材料与缺口；`accept` 核对业务验收，`verify` 核对最终交付和关闭条件。

## 实施、批准与代码评审

### 记录绑定

绑定用内容指纹标识记录适用的输入：

| 记录 | 绑定内容 |
| --- | --- |
| 运行结果 | 源码内容及逻辑依赖、执行定义、记录格式与解码器版本、环境；声明 `revision_sensitive` 时另含提交号 |
| 场景轮次 | 每条结果的场景内容指纹、产品指纹；保存提交时的源码指纹、轮次编号和执行时间 |
| 评审 | 任务、源码总指纹与逐文件指纹、校验策略、章节、风险、选中运行、场景文件与轮次；含合并批准字段的草稿另绑定完整方案与历史 |
| 方案批准 | 方案身份、评估、所选章节指纹及确认的删除 |
| 合并批准 | 方案批准的内容，加源码摘要与运行引用；提供 `revision` 时另核对该提交的源码摘要 |
| 章节指纹 | `own` 覆盖本节正文、标签、场景文件摘要和排序后的逻辑依赖；`effective` 另覆盖上游依据及影响本节的实施决定 |

表中内容变化时记录过期；其他变化下记录继续有效。场景文件按每条场景的内容指纹重新判定结果，产品变化后的复用见[场景与证据](#场景与证据)。

**验收材料**是本任务的方案原文（文件头 `design`、`task` 与本任务相同的 Markdown）及其验收节引用的场景文件。改动范围排除验收材料。**产品指纹**是排除验收材料后的源码指纹，供场景轮次判定使用；检查运行绑定完整源码指纹，含场景文件。

```bash
tw team run --root "$PROJECT" --task "$TASK_ID"
tw team run --root "$PROJECT" --task "$TASK_ID" --with-task "$OTHER_TASK"
```

任务、项目默认及风险检查取并集；`--with-task` 可重复，同一批次每项检查执行一次，各任务单独验收。可重复 `--check` 聚焦运行，最终核查要求全部必要检查。运行期间源码和环境须保持稳定。

任务 `scope` 覆盖实际改动的全部文件，含测试；验收列出未映射文件。方案范围需调整时，先修订方案并 `start` 新上下文，再运行检查与评审。

执行定义含命令、目录、报告格式、环境声明和覆盖范围等。`required_cases`、`purpose`、`timeout` 属于结果判定字段；修改后用原始报告按当前登记重新判定；重新判为通过的记录在 `re_evaluated` 列出检查和原判定。交接和收尾说明中的检查记录采用相同判定，保留原状态与原始报告。`run` 缺少登记用例时列出实际用例名；`accept`、`verify` 返回 `summary_markdown`，文本模式打印该摘要。登记变化后重新生成评审。

每项检查选用当前有效的最新通过结果；失败、过期、被取代的记录列入 `superseded_execution`。某项过期时用 `run --check <该项>` 重跑并追加材料，必要时用 `--run` 显式选取。候选原始报告未满足当前用例要求时，记录问题并继续选择其他候选。`accept` 实际核对环境；之后 `verify` 使用验收记录的环境，返回 `environment_checked: recorded at acceptance`，并重新核对源码、定义、评审和平台。导入记录遵循相同的离线环境核查规则。运行期间的协作标记位于 `.tw/local/validation-active/`。

```bash
tw team approval-draft --root "$PROJECT" --task "$TASK_ID" --reviewer <姓名> --confirmation <说明> --mode plan
```

`confirmation` 可省略；也可用 `--record <输入文件>` 提供必填 `reviewer` 和可选说明，由他人代为记录批准。任务文件可显式传 `--design`、`--run`；记录可指定 `decision`、`section_ids`、`deletion_ids`、`mode`、`revision`。默认模式、批准范围及 `--sections` 见[批准与变化](designs.md#批准与变化)。无必要检查的文档任务可用空运行列表，并通过场景验收。

`revision` 可选，使用 `approval-draft --revision <提交号>` 或写入 `--record` 输入，值为 40 或 64 位十六进制完整提交号。方案批准记录它；合并批准读取本地该提交，按 `code_digest` 核对源码摘要，不符时报“批准的提交与绑定的源码不一致”，缺提交时报告缺口。

```bash
tw team review --root "$PROJECT" --task "$TASK_ID"
# 编辑返回的 review.md，再提交
tw team review --root "$PROJECT" --task "$TASK_ID" --submit
# 提交另一处的 Markdown
tw team review --root "$PROJECT" --task "$TASK_ID" --submit --file <评审.md>
# 导入变更请求上的完整评审
tw team review --root "$PROJECT" --task "$TASK_ID" --from-platform
```

`--from-platform` 经项目平台脚本的 `task` 操作，按 `updated_at` 选含绑定区的最新 `kind: review` 条目，按本地提交规则核对绑定、逐项复核、问题历史并转换。平台来源单独使用，本地来源用 `--submit [--file <路径>]`；绑定或来源变化时重新生成复核稿。评审 JSON 的 `platform_author`、`platform_url` 用于后续核对作者和原文；姓名独立性见[场景与证据](#场景与证据)。平台合并批准经原文核对后作为已共享批准。

`review.md` 是可编辑表；绑定有效的工作稿保留并报告填写进度。评审人核对代码、需求、原始结果和预填的场景执行，填写姓名、知识冲突处置（是/否）、规范与需求及逐项验收的结论（通过/不通过）和理由。补充证据每行一个仓内路径，工具计算指纹和运行引用。自动验收的“用例”可选，每行一个或用 `、` 分隔；方案与评审均省略时，评审稿及收尾注明“未指明用例，证据为整项检查通过”。

隐藏的 `tw-record` HTML 注释是绑定区；它和工具填写的结果、风险列表、变化说明保持原样。格式完整、绑定有效的评审可提交，含“不通过”、知识冲突待处理或 `open` 阻塞问题的意见；拒绝时指出行号或小节。`accept`、`deliver` 核对独立性、实际检查与通过条件。提交成功后在请求目录保存 `review.md`、`review.json`、`review-source.json`，登记当前评审，下一步为 `deliver --task <身份> --reason <理由>`。清理保留引用材料和任务目录的未提交表。

问题字段与处置见[问题处置与交接](#问题处置与交接)。按 `### 问题 Q1` 分节填写，已有问题保持身份；新问题可增加同格式小节：

```markdown
### 问题 Q1
- 编号：Q1
- 负责人：负责人姓名
- 影响范围：A1
- 阻塞阶段：acceptance
- 状态：open
- 摘要：实际问题
```

### 变化后逐项复核

绑定区 `format_version` 为 2。草稿绑定保存在 `reviews/<草稿编号>/binding.json`，编辑与上一轮提交记录保存在 `reviews/editor.json`。每次提交保存 `review-source.json`（`data_version: 1`、`kind: review-source`），按文件内容和属性比较差异；外部输入用 `[名称]/路径` 区分，新增、删除、修改列入“变化”。评审记录缺少逐文件指纹时：源码总指纹相同，证明源码未变；总指纹变化，要求全部预填项重新核对。

已提交评审的绑定变化时，`review --task <身份>` 预填上一轮姓名、知识冲突处置、规范与需求结论、验收结论和证据、问题清单。运行与场景执行区采用当前结果，“变化”列出受影响验收项与场景。绑定有效时返回当前评审仍有效。

过期工作稿改名保存为 `reviews/archived-<唯一编号>.md`，`archived_draft` 给出路径与指纹；新稿优先预填工作稿已填写内容。预填结论带 `复核：待复核`，逐项核对后改为 `复核：已复核`；即使重写结论或理由，也填写确认。提交一次列全待确认小节及行号，补充证据重新核对指纹，问题处置可更新。

`status` 将绑定变化的已提交评审标为过期；缺少当前复核稿时指向 `review`，生成后指向 `review --submit`。上一轮评审、原文、源码快照和绑定引用参与请求指纹；重试规则见[重试与清理](#重试与清理)。

## 先验收，再更新知识

### 五步交付入口

```bash
tw team start --root "$PROJECT" --task <任务文件> --design <方案>
tw team run --root "$PROJECT" --task "$TASK_ID"
tw team scenarios pending --root "$PROJECT" --task "$TASK_ID"
# 独立执行者按清单执行后登记结果
tw team scenarios submit --root "$PROJECT" --task "$TASK_ID" --results <结果文件>
tw team review --root "$PROJECT" --task "$TASK_ID"
# 评审人填写返回的 review.md，再提交
tw team review --root "$PROJECT" --task "$TASK_ID" --submit
tw team deliver --root "$PROJECT" --task "$TASK_ID" --reason <不需要更新知识的理由>
```

`run` 在必需检查有有效通过结果、场景状态均为 `passed` 或 `blocked` 时准备评审稿，返回 `review_file` 和提交命令；存在待执行或失败场景时指向 `scenarios pending`。登记场景结果后运行 `review` 获取评审稿。任务需已有 `start` 上下文。

当前任务需合并批准且缺少有效批准时，评审信息显示“批准方案与代码”和可选“批准说明”。独立评审人填“是”后，以其为批准人生成批准并登记；填“否”、留空或评审人为实施负责人时保存意见，验收继续核对批准和独立性。批准范围及绑定见[批准与变化](designs.md#批准与变化)和[记录绑定](#记录绑定)。预填批准字段也逐项复核。

`approval-draft` 的姓名、说明、模式和提交号参数与 `--record` 二选一；`--sections` 可覆盖输入的 `section_ids`。命令行 `plan` 对应记录的 `design` 模式，批准输入为 JSON。

`deliver` 依次调用 `accept`、`delivery-template`、`verify`，保留各步材料并更新 `current.json`。有效验收和知识处置报告直接复用；无知识变化时给 `--reason`。平台任务每次比较最新含绑定区评审的 `updated_at` 与本地登记时间，采用较新者；平台较新时先导入，失败停在 `review`。本地文件记登记时间，平台导入记地址及 `updated_at`；本地任务采用最后提交。评审未通过时列各结论、阻塞问题、理由及重跑复核命令。失败即停止，`steps`、`stopped_at`、`next_action` 给步骤和下一步；结果含 `delivery_complete`、`closable`、`summary_markdown` 和平台 `close_note`。中断后用新请求编号继续。

```bash
tw team accept --root "$PROJECT" --task "$TASK_ID" \
  --out .tw/local/acceptance-<本次唯一编号>.json
```

`accept` 按任务身份取准备材料、运行和已填写评审，核对运行、独立性、场景与问题处置，保存验收报告；已有报告可用 `--report`。批准省略时取当前材料组，也可显式补充。成功返回 `business_accepted: true`、`delivery_complete: false`、`closable: false`。

通过后按 [team-knowledge 的完成步骤](../../team-knowledge/SKILL.md#完成后)在同一分支更新知识并运行 `tw check`，再交付。报告的 `knowledge` 写知识处置：

```json
"knowledge": {"files": [".tw/lessons/2026-10-14-retry-storm.md"], "reason": ""}
```

`delivery-template` 按任务 `base` 到工作区的 Git 差异预填全部知识正文，含删除和未跟踪新文件；`.tw/.gitignore`、`config.json` 归配置。`files` 为空时填写 `reason`。多个任务共用知识时写一次，各报告分别列出。

```bash
tw check --root "$PROJECT"
tw team delivery-template --root "$PROJECT" --task "$TASK_ID"
tw team verify --root "$PROJECT" --task "$TASK_ID"
```

交付模板自动登记；补充理由或其他字段时，复制为新文件填写，用 `verify --task "$TASK_ID" --report <新报告>` 指定，成功后可省略路径。

`verify` 要求报告的 `acceptance` 指向本任务通过的业务验收记录，并按[记录绑定](#记录绑定)核对当前材料；变化时重新验收。`knowledge.files` 与实际知识差异一致，`tw check` 错误数为零。平台收尾按[单人任务的收尾说明](coordination.md#单人任务的收尾说明)准备，关闭授权及发布核对见[关闭步骤](team-delivery.md#状态与关闭-issue)。

回归状态由场景的 `regression` 生成，见[场景与证据](#场景与证据)。`delivery_complete` 表示验收、知识处置和交接记录齐全；整体交付条件见[业务验收标准](business-acceptance.md#5-交付报告)。

## 平台草稿、跨仓和外部结果

`design-draft --issue ... --record ...`、`approval-draft --issue ... --record ...`、`progress --issue ... --progress ...`、`handoff --issue ... --progress ...` 生成共享记录草稿。`handoff --kind design` 交接方案，默认 `--kind implementation` 交接实施。平台输入与冲突见[任务协作](coordination.md)。平台批准记录或含合并批准的绑定评审须在对应任务上共享。

外部仓库输入为 `{"kind":"repository","repository":"host/group/repo","role":"build"}`，`role` 还可为 `modified`、`joint`；本机目录通过 `--repository host/group/repo=/path` 或本地映射提供。检查的 `repository` 决定执行目录；`evidence --evidence-repository host/group/repo --path <仓内路径>` 保留原仓身份和内容指纹。

平台读取遵守[平台契约](platform.md)；外部运行和联合验收见[跨机器结果](portable.md)，入口为 `run --portable`、`import-result --result <定位文件>`、`aggregate --joint <联合清单> --repository host/group/repo=/path`。核对原始报告与平台运行来源。

## 重试与清理

材料按任务和请求分目录保存。`--request-id` 用于重试：同编号且输入相同返回原结果；输入包括 `--allow-modified-tool`、`start --grant`、`--confirmed-by`。输入变化或重跑使用新编号，保留失败和中断材料。`--out` 接受运行目录下的新文件；已有路径报错，按返回的原因和下一步修正输入。

```bash
tw team cleanup --root "$PROJECT" [--cleanup-scope all --older-than 14] > "$CLEANUP_PLAN"
tw team cleanup --root "$PROJECT" --apply --plan "$CLEANUP_PLAN"
```

计划放在项目外，核对预览后应用；材料变化时重新预览。清理对象是已结束任务中未被引用的请求目录，完成证明须覆盖当时的请求清单；任务新增请求或请求被改写时整项重新受保护。`--cleanup-scope all` 另含超过指定天数且未被引用的 `batches/`、`imports/` 目录和已结束进程的验证标记。`current.json` 引用材料、在途任务、共享批准历史与被引用证据保留。手工 `--out` 和其他目录由成员管理，列入 `unmanaged`；`totals` 给总体积、可回收体积和最大 20 个文件。

`evidence` 与评审证据使用可阅读内容，拒绝 ELF、Mach-O、PE 编译产物；构建产物记录构建提交和命令。文件上限 64 MiB，显式 `--allow-large-evidence` 后引用保存 `allow_large_evidence: true`；最终核查据此放宽大小限制，本地与外部仓库相同。编译产物仍按类型拒绝。

## 进度、恢复与统计

```bash
tw team status --root "$PROJECT" --task "$TASK_ID" --format text
tw team metrics --root "$PROJECT" [--task "$TASK"] [--since 2026-10-01] [--format text]
```

`status` 只读取记录，业务结论以新的 accept 为准。`task_phase` 为 `closed` 或 `in-progress`：平台已关闭时报告各步骤最后记录，概要和 `next_action` 为“任务已关闭”，`next_step` 为 null；进行中按当前材料核对步骤，有效验收与交付列入 `verified_records`（`acceptance`、`delivery` 含 `path`、`sha256`）。

评审在成功提交后计为完成。步骤状态为 `done`、`pending`、`stale`、`failed`、`running-or-interrupted`、`not-recorded`。场景验收步骤列通过、失败、受阻、待执行数量；待执行或失败时指向 `scenarios pending`。采用有效评审后指向 `deliver`；绑定变化时受影响步骤过期。显式方案内容变化时重新 `start`，相同内容换路径可经核对登记。

`publication` 按平台记录列收尾或交接的发布状态、类型、评论地址。关闭条件和 `close_authorization` 见[关闭步骤](team-delivery.md#状态与关闭-issue)。会话中断后先查 `status`；`rules_changed` 表示开工后团队规则文本变化，运行记录按其绑定核对，修改版工具证据带标记。

`metrics` 读取本机运行目录，按任务列请求、失败、未完成、耗时、检查运行与重跑次数，以及各场景轮次和一次通过率，供每周复盘；场景统计口径见[场景与证据](#场景与证据)。

## 前置任务与只读状态

任务节 `blocked_by` 使用实际业务验收证明。每个前置项写 `{"section":"T1","task":".tw/local/.../task.json","report":".tw/local/.../delivery.json"}`，在 `start` 或 `handoff` 传 `--dependency <输入文件>`；上下文保存输入，`accept` 和交付模板沿用，变化时重新 `start`。工具核对前置项原始报告和批准，将材料保存在上下文，最终交付重新核对。

`status` 读取记录和声明；显式替换成功核对后更新当前组。需要核对原始报告和当前环境时运行 `accept`。

## 场景与证据

`scope-global.data.requirement_acceptance` 列非空主需求验收编号；`impact` 每项含 `repository`、`entrypoint`、`operations`、`producer`、`consumer`、`commit_owner`、`acceptance`。主需求覆盖所列验收，子任务结果的 `acceptance_scope` 为 `task`。

每个任务的验收节用 `- 场景：docs/sop/<批次>.yaml#SOP-02、SOP-03` 引用场景文件和节点，解析为 `data.scenarios` 的 `{path, sha256, nodes}` 列表；文件用 YAML 子集或 JSON。场景格式、配对示例、结果文件及网页、命令行、智能体三种交付形态的执行方法见[场景指南](scenarios.md)。

### 场景与入口

`scenarios check <文件>` 核对 `metadata.sources`、编号唯一、每节点正向场景及反向场景或 `negative_exempt` 理由、反向 `negative_type`、场景的 `verify` 入口。场景内容指纹覆盖 `initial_state`、`steps`、`expected`、`forbidden_effects`，错误给原文行号。

`.tw/config.json` 的 `acceptance_entries` 以入口名映射 `surface`、`operate`、非空 `observe`、非空 `evidence`、`isolation`；可选 `address_env` 为环境变量名，`accounts` 引用已声明账号编号。每条场景用 `verify` 选择入口；纯文档也声明自己的入口。

场景的 `metadata.sources` 与验收节的 `依据`（`data.sources`）均使用 `{ref, version, confirmed_by}`，登记已确认业务原文的位置、版本和确认人。验收节缺少来源时 `verification_gaps` 列出验收项，`accept` 拒绝。`检查` 为登记检查编号；非空时填写 `验证：自动`，内部为 `{method:"automatic", cases, substitutes}`，后两项默认空数组；检查为 `无` 时省略验证标签。

检查覆盖声明位于 `checks.<编号>.coverage`：`level` 为 `unit/interface/journey/manual`，`entrypoints` 非空，`environment` 为环境名，`substitutes` 列替代依赖；`isolation` 为 `isolated/shared-reviewed/unresolved`。共享环境填写 `isolation_evidence`，隔离解决后执行。业务验收核对检查通过、隔离已解决、替身获准和方案及评审指定用例通过；声明的业务适用性由独立评审确认。准备阶段的 `verification_gaps` 给改法，标题“验收无法满足”，作为提示返回。

### 用例导入与覆盖

`scenarios import-cases --task <身份> <文件>` 读取 YAML 子集或 JSON，顶层 `test_cases` 或 `cases` 数组中每条含 `id`、`title`，其余字段原样保存在快照。`case_imports` 按导入顺序累积，同编号采用最后一次完整内容。

代理按业务语义把用例转换为团队场景，写配对文件后运行 `scenarios coverage --task <身份> --pairs <文件>`。每条已导入用例恰好归入 `covered` 或 `disposed`；`conflict`、缺归类、重复归类或引用未知编号时报 `scenario-coverage-incomplete`。`covered`、`conflict` 含 `case`、`scenarios`、`note`；`disposed` 含 `case`、`state`（`blocked/deferred/out-of-scope`）、`reason`、`confirmed_by`。通过后保存 `case_coverage`。覆盖的语义及充分性由评审确认。

### 待执行清单与结果

`scenarios pending --task <身份>` 按本任务引用节点列当前场景。相同场景编号与内容指纹的最近结果用于判定：

| 输入 | 当前状态与处理 |
| --- | --- |
| 当前产品上的 `pass`，或此前 `pass` 且 `regression` 指定检查和用例在当前源码有效运行中通过 | `passed` |
| 最近结果为 `fail` | `failed`，进入待执行清单 |
| 最近结果为 `blocked` 或 `skip` | `blocked`，交验收核对问题处置 |
| 新场景、内容指纹变化，或此前通过但产品变化且回归尚未通过 | `pending`，进入待执行清单 |

清单给场景内容、入口声明、内容指纹、原因、当前 `source_digest` 和 `product_digest`。独立执行者经声明入口执行，按行写 JSON 对象，再运行 `scenarios submit --task <身份> --results <文件>`。必填 `scenario`、`status`、`actual`、`executed_at`、`executor`、`evidence`；可选 `session`、`finding`、`note`。每个场景每文件一条结果；状态为 `pass/fail/blocked/skip`，`blocked`、`skip` 填 `finding`，时间为带时区且截至当前的 ISO 时间。证据路径相对结果文件目录，`pass`、`fail` 至少一份。

提交须覆盖全部待执行及失败场景，也可包含本任务其他场景。工具核对执行者独立性、证据文件与复制期间指纹、提交期间源码及场景内容稳定，将证据复制到本轮目录并登记轮次。结果文件和原始证据放在仓库外或 `.tw/local/` 下；仓内普通未跟踪文件参与产品指纹。代理、人和项目看板均通过同一契约登记。

### 轮次、验收与回归

轮次保存逐场景结果与通过、失败、受阻、跳过数；`metrics` 的每轮通过率为通过数除以本轮结果数。`first_pass` 按登记轮次取当前场景内容的首次结果，通过数除以首次为 `pass` 或 `fail` 的场景数，空分母返回 null。`by_executor` 按规范化执行者身份取当前场景内容的最新结果；`agreement` 在至少两位执行者有通过或失败结果的场景中，统计所有结果均通过的比例。

`accept` 要求检查通过、场景均为 `passed` 或受阻已处置；`blocked`、`skip` 对应问题在评审中为 `accepted` 或 `deferred`，按[问题处置](#问题处置与交接)填写确认人及依据。复杂任务需导入测试同事的用例；任务有导入时，`accept` 用当前用例并集重新核对覆盖；没有导入的中等、简单任务按自写场景验收。

评审观察种类为 `execution` 和 `scenarios`：前者含 `{run:{path,sha256}, check, cases}`，运行属于本任务且为选中的有效结果；后者含本任务轮次引用 `rounds`。评审稿预填场景状态、实际结果、执行者、轮次和证据；受阻场景的问题按验收负责人及受影响验收节补入清单。`reviewer` 与场景 `executor` 均独立于 `roles.implementation_owner`，姓名比较折叠大小写和多余空格，实施负责人必填。成员和代理使用稳定、可区分的身份。

每条场景的 `regression` 写 `{check, cases}`、`{manual, owner, trigger}` 或 `{pending}`，分别表示仓内回归、保留人工责任、待沉淀的问题编号；缺省表示待沉淀。工具生成 `automation_status` 的 `automated`、`manual-only`、`pending` 列表：检查及指定用例在当前源码有效运行中通过时归入 `automated`；人工责任归入 `manual-only`；其他归入 `pending`。`regression.pending` 引用评审中 `deferred` 的问题。`verify` 存在待沉淀场景时返回 `regression_pending: true` 并逐条列出，摘要写明整体交付未完成（[业务验收标准](business-acceptance.md)第 5 节）。

## 问题处置与交接

方案 `issues`、评审 `findings`、进度与交接 `questions` 使用同一对象：

```json
{"id":"Q1","summary":"具体未决问题","owner":"实际负责人","affects":["A1"],
 "blocks":["implementation","acceptance"],"state":"open","resolution":{}}
```

`affects` 为空表示全局；`blocks` 指实施、验收或两者。评估的 `uncertainties` 引用问题编号，正文保存在 `issues`。`state` 为 `open`、`resolved`、`accepted`、`deferred`；`open` 的 `resolution` 为 `{}`，其他状态填非空 `reason` 与 `evidence` 来源列表。`accepted` 另填 `confirmed_by`；`deferred` 另填确认人、`follow_up`、`scope_change`；`confirmation` 可选。

已知问题保留编号、摘要、责任、影响与阻塞阶段；原记录有误时明确处置后再新增问题。成功提交的 Markdown、交给 `accept` 或 `verify` 的 JSON 评审，以及平台方案、交接和进度的问题均进入历史，验收失败时也保留，后续草稿带入。评审人将讨论中的已知问题写入这些字段。

交接 `verified` 使用原始执行或业务验收引用 `{path,sha256}`，跨仓可加 `repository`。通过共享材料包或 `import-result` 提供原件和引用输出；源码与说明链接放入 `references`，证据类别见[业务验收术语](business-acceptance.md#1-术语)。接手或最终核对时，缺失原件列为缺口。
