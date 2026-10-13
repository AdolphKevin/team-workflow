# 工具约定

所有任务、配置和记录使用本页的格式（`schema_version: 5`），工具不读取其他格式。运行环境为
Python 3.10+、Git 和项目自身的测试依赖。通用工具只使用标准库。

下文 `$WF` 是已安装技能的 `scripts/workflow.py` 路径，`$PROJECT` 是项目目录，
`$CS_SKILL` 是发现的独立 CS 技能目录。输入路径相对项目，输出使用命令返回的
`artifact.path`，不要假设公共固定文件名。默认返回 JSON，`--format text` 用于阅读。

## 配置与任务

```bash
python3 "$WF" schema --root "$PROJECT"
python3 "$WF" project --root "$PROJECT" --cs-skill "$CS_SKILL"
python3 "$WF" guidance --root "$PROJECT" [--scope project|global|all] [--file AGENTS.md] [--apply]
```

`project` 的 `version.status` 为 `current` 或 `tool-outdated`。项目配置的格式或
`workflow_version` 高于已安装工具时，所有读取该配置的命令返回 `tool-outdated`，先更新
已安装技能。规则见[接入指南](onboarding.md#更新与回退)。

`guidance` 默认预览，`--apply` 只写入标记块：项目指令文件得到[项目指引](../templates/guidance-project.md)，
本机 Claude Code 与 Codex 的用户级文件得到[全局指引](../templates/guidance-global.md)。项目规则只写
`AGENTS.md`（没有则新建）；`CLAUDE.md` 没有则新建并只放 `@AGENTS.md` 引用（[引用模板](../templates/guidance-claude.md)），
已含 `@AGENTS.md` 或 `@./AGENTS.md` 的保持不动；`--file` 只接受仓内相对路径，引用随之指向该文件。每个目标的
`action` 为 `create`、`append`、`update`、`unchanged`、`skipped`（该客户端目录不存在）或 `blocked`（标记损坏，
整次拒绝写入）。写入保留原文件的换行风格、权限和符号链接。`--home` 只用于试验，指向替代的用户目录。`schema` 返回随技能安装的[配置模板](../templates/profile.json)、[任务模板](../templates/task.json)
和[方案模板](../templates/design.json)。模板需要按实际项目填写；配置放在根目录
`.team-workflow.json`，手工任务输入及运行材料放在被 Git 忽略的 `.team-workflow/`。

| 配置字段 | 含义 |
| --- | --- |
| `schema_version`、`project` | 固定格式 5，以及项目稳定名称 |
| `context` | 必须读取的现有仓内文件 |
| `knowledge` | `provider: cs`，入口固定为 `.codestable/wiki/INDEX.md` |
| `checks` | 检查编号到具体命令、报告格式、用例及环境要求的映射 |
| `required_checks` | 分别为 `code`、`docs` 指定默认检查 |
| `risk_checks` | 风险到非空检查集合；缺少风险映射会报错 |
| `inputs` | 参与结果但被 Git 忽略的文件或目录 |
| `external_inputs` | 逻辑依赖及用途，本机位置另行提供 |
| `environment_versions` | 名称到只读版本查询命令数组 |
| `workflow_version` | 可选；配置所需的最低工具版本，高于已安装工具时拒绝执行 |

检查包含 `argv` 参数数组、`purpose`、仓内 `cwd`、秒数 `timeout`、`format`、
`required_cases`、`required_env` 和 `environment`。命令不经 shell，凭证通过环境传递，
只记录必要变量名；日志仍遵循项目脱敏规则。

`format` 可为 `command`、`go-json` 或 `junit`。普通命令只能证明退出结果，不能声明
用例。Go 解析 `go test -json`；JUnit 需要 `report: "{output}/results.xml"`，命令必须
生成这次运行的新报告。必要用例使用准确的 `包::测试名` 或 `classname::name`。未指定
必要子集时全部发现的用例均须通过；指定后仍拒绝任何失败、必要跳过、缺失和零用例。
额外产物放在 `{output}/` 内；已有业务场景审查要求继续保留，不能用工具摘要替代。

`environment` 必须明确为 `{"kind":"stateless"}`，或
`{"kind":"fixture","identity":["业务仓的只读命令","参数"]}`。前者只用于不依赖
可变外部数据的检查；后者必须真实表达服务、数据库或夹具的有关状态。身份无法核实时
不复用结果。`revision_sensitive: true` 仅用于实际依赖 Git 提交编号的检查。

任务使用 `schema_version: 5`，包含 `id`、真实存在的完整基准提交 `base`、`goal`、
`non_goals`、`kind`（`code` 或 `docs`）、`risks`、`acceptance`，以及关联的 `design_id`
和非空任务节数组 `section_ids`，以及 `acceptance_scope`（主需求 `requirement`，子任务 `task`）。子任务的 `parent` 指向方案所属主需求。验收项为 `{id, expectation, checks}`。`paths`、
`symbols` 和跨仓 `scopes` 提供知识读取范围；实际子任务可保留 `parent`。

支持的风险为 `authorization`、`persistence`、`concurrency`、`messaging`、
`public-contract`、`cross-service`。它们决定检查，不决定是否必须事前评审。父方案和
拆分任务分别评估；任务节的 `data.assessment` 可覆盖方案评估。具体方案和逐节批准格式
见[分节方案约定](designs.md)，不要根据父方案复杂度替代子任务判断。

## 开工材料、状态与方案

```bash
python3 "$WF" prepare --root "$PROJECT" --task "$TASK" --design "$DESIGN" \
  --cs-skill "$CS_SKILL"
python3 "$WF" status --root "$PROJECT" --context "$CONTEXT" --format text
```

平台任务也可用 `prepare --issue <完整Issue链接>` 读取共享任务和方案。已有批准使用
可重复的 `--approval`，历史方案用可重复的 `--design-history`，从第 1 版保留完整快照。
读取平台失败时报告缺口，不退回本地材料后声称平台交付完成。

`resume` 和 `status` 只读，不生成新的上下文文件。后续命令复用已有 `--context`；缺少时以当前方案和已有批准运行 `prepare`，无需再次请求批准。

`prepare` 返回上下文、任务、方案与开工简报引用。把上下文的 `artifact.path` 作为
`$CONTEXT`，后续 `--context` 自动补齐这些输入并检查内容。必须实际阅读简报；保存文件
不证明知识已经使用。新批准可显式传入 `--approval`，历史变化传 `--design-history`；
更新批准不需要重做开工简报，也不能用事后简报覆盖原读取记录。

```bash
python3 "$WF" design-diff --root "$PROJECT" --task "$TASK" --design "$NEW_DESIGN" \
  --design-history "$V1" --design-history "$V2"
```

`design-diff` 比较最后一份旧版和当前版，保留完整历史删除。`status` 和 `resume` 只读
汇总材料及缺口，统一不在此声明本轮业务验收、最终交付或允许关闭；这些结论由 `verify` 核对。

## 实施、批准与代码评审

```bash
python3 "$WF" run --root "$PROJECT" --context "$CONTEXT"
python3 "$WF" run --root "$PROJECT" --task "$TASK" --with-task "$OTHER_TASK"
```

任务、项目默认及风险检查取并集；`--with-task` 可重复。同一批次每项检查执行一次，
各任务仍单独验收。可重复 `--check` 做聚焦运行，最终核查仍要求全部必要检查。
结果绑定源码内容、逻辑依赖、检查定义及环境；源码或环境在运行期间变化不能通过。
知识文件、暂存布局和无关流程配置变化不会自动重复业务测试。运行期间的协作标记位于 `.team-workflow/validation-active/`；共享目录保持稳定。标记不拦截编辑器写入，起止指纹也不证明期间绝无改动。

本地评审输入写在任务输入目录，例如：

```json
{"reviewer":"实际评审人","confirmation":"具体确认依据"}
```

取得真实确认后生成记录：

```bash
python3 "$WF" approval-draft --root "$PROJECT" --context "$CONTEXT" \
  --record "$APPROVAL_INPUT" --run "$RUN"
```

也可不用上下文，明确传 `--task` 和 `--design`。输入可指定 `decision`、`section_ids`、
`deletion_ids`、`mode`；选择部分章节时需明确覆盖相应上游依据。简单任务默认合并评审，
中等、复杂任务默认方案评审；具体模式和删除选择见[分节约定](designs.md)。合并评审
绑定当前代码和传入运行材料。没有任何已配置必要检查的纯文档任务可以没有运行记录，
验收仍须真实评审证据；省略记录不能绕过已配置的检查。草稿不产生批准事实。

```bash
python3 "$WF" review-template --root "$PROJECT" --context "$CONTEXT" \
  --approval "$APPROVAL" --run "$RUN"
python3 "$WF" evidence --root "$PROJECT" --path <实际证据文件>
```

将默认未通过的模板复制为本任务的评审输入，实际阅读代码、需求与报告后填写：具体
`reviewer`、`standards`、`spec`、每个 `acceptance` 的通过状态、结论及非空证据，以及
当前风险、知识冲突处置和未解决问题。证据使用命令返回的路径与指纹；只引用测试源码
不能证明测试已通过。保留生成时的任务、源码、章节绑定，过期时重新评审。

## 先验收，再回写知识

```bash
python3 "$WF" delivery-template --root "$PROJECT" --context "$CONTEXT" \
  --approval "$APPROVAL" --run "$RUN" --review "$REVIEW"
python3 "$WF" verify --root "$PROJECT" --context "$CONTEXT" \
  --report "$DELIVERY" --phase acceptance --cs-skill "$CS_SKILL" \
  --out .team-workflow/acceptance-<本次唯一编号>.json
```

成功结果中的 `business_accepted` 为真，但 `delivery_complete`、`closable` 仍为假。
保存验收产物路径 `$ACCEPTANCE`，再按 CS 的完整规则写回最终结果。知识草稿使用：

```bash
python3 "$WF" knowledge-template --root "$PROJECT" --context "$CONTEXT" \
  --acceptance "$ACCEPTANCE" --cs-skill "$CS_SKILL"
```

把返回的 `artifact.path` 复制为待填写的 `$CS_PAYLOAD`。继续同一任务加 `--cs-task-id`。
工具通过 CS 的公开模板接口生成输入，保留实际验收引用与结构化任务关联；省略验收时
只生成 `in-progress` 和空 `items`。工作流不执行 CS 写入。

填写实际结果、验证和知识处置，不把未通过验收的
工作标为完成。外部关联写入 `task.external_refs`，不依赖请求正文包含链接。

```bash
python3 "$CS_SKILL/scripts/cs_knowledge.py" --root "$PROJECT" learn \
  --file "$CS_PAYLOAD" --dry-run --plan-out "$CS_PLAN"
python3 "$CS_SKILL/scripts/cs_knowledge.py" --root "$PROJECT" learn \
  --file "$CS_PAYLOAD" --plan-file "$CS_PLAN"
python3 "$CS_SKILL/scripts/cs_knowledge.py" --root "$PROJECT" doctor
```

`$CS_PLAN` 每次选择项目外的新路径。第一条明确成功并产生本次计划后才执行第二条；
失败立即停止，不能应用同名旧文件。CS 负责独占创建、并发和幂等保证，工作流不绕过它。

新增知识使查询结果变化时，追加 `brief --context "$CONTEXT"` 获取 `$FINAL_BRIEF`，
保留原来的 `$BRIEF`。随后只读捕获完成状态：

```bash
python3 "$WF" knowledge --root "$PROJECT" --context "$CONTEXT" \
  --acceptance "$ACCEPTANCE" --brief "$BRIEF" --final-brief "$FINAL_BRIEF" \
  --cs-task-id "$CS_TASK_ID" --disposition none --reason '<实际知识处置原因>' \
  --cs-skill "$CS_SKILL"
python3 "$WF" delivery-template --root "$PROJECT" --context "$CONTEXT" \
  --approval "$APPROVAL" --run "$RUN" --review "$REVIEW" --knowledge "$KNOWLEDGE"
python3 "$WF" verify --root "$PROJECT" --context "$CONTEXT" \
  --report "$FINAL_DELIVERY" --cs-skill "$CS_SKILL"
```

没有查询变化时可省略 `--final-brief`。`none/reused/updated/added` 描述实际知识处置，
不要求每次新增卡片。`knowledge` 不执行 CS 写入；它核对当前业务验收、规范任务记录、
结构化关联及相关来源。真正有知识使用影响时仍按 CS 保存证据。

最终核查默认阶段为 `delivery`。Issue 身份自动触发平台核查，漏传 `--issue` 不能绕过。
交付完整还需要当前交接无剩余事项、未决问题及未确认进度。关闭另需明确授权：报告可
记录 `close_authorization: {confirmed_by, reference}`；工具仅报告状态，不执行关闭。

### 回归自动化状态

`delivery_complete` 只表示验收、知识回写和交接记录齐全，不表示应沉淀的回归已经自动化。
报告可在 `delivery-template` 生成后手工加入可选的 `automation`，按场景声明回归状态；
每次重新生成模板后需再次加入。未声明时结果为 `automation_status: "not-declared"`。

```json
"automation": {"scenarios": [
  {"id": "S1", "acceptance": ["A1"], "guarantee": "<要保护的业务结果>", "status": "automated",
   "level": "interface", "check": "<已执行的检查>", "cases": ["<用例>"]},
  {"id": "S2", "acceptance": ["A2"], "guarantee": "<要保护的业务结果>", "status": "pending-automation",
   "level": "journey", "reason": "<尚无相应入口>", "finding": "<延期问题编号>", "due": "2026-11-15"},
  {"id": "S3", "acceptance": ["A3"], "guarantee": "<要保护的业务结果>", "status": "manual-only",
   "level": "manual", "reason": "<无法自动化的原因>", "owner": "<执行人>", "trigger": "<执行时机>"}
]}
```

每个条目只允许示例中对应状态列出的字段，缺项或多余字段都会被拒绝：

- `automated`：必填 `check`、`cases`。检查已在本次运行中执行，用例全部通过；检查的覆盖
  层次不低于声明的 `level`，`journey` 检查可覆盖 `interface` 或 `unit` 声明。
- `pending-automation`：必填 `reason`、`finding`、`due`。`finding` 必须是评审中 `deferred`
  的问题，由它携带确认人、确认依据、跟进任务和范围调整；`blocks` 写 `acceptance`，记录
  它若重新打开时阻塞的阶段。多个场景可引用同一问题；同一需求缺多类入口时，可合并为
  一个建设任务，也可分开登记。`due` 为 ISO 日期，过期仍可记录。
- `manual-only`：必填 `reason`、`owner`、`trigger`，`level` 为 `manual`。它声明后续人工执行
  责任，不证明已经观察过；本次人工观察的证据写在交付验收记录，尚未观察的列为未验证。

结果中的 `regression_pending` 在存在待建设条目时为真，文本输出逐条列出。工具只核对结构与
引用，不证明业务保证已被自动回归保护；状态的业务含义见
[项目验收方式与测试能力建设](test-capability.md)第 4 节。

## 平台草稿、跨仓和外部结果

`design-draft --issue ... --record ...`、`approval-draft --issue ... --record ...`、
`progress --issue ... --progress ...` 和 `handoff --issue ... --progress ...` 只生成共享
记录草稿。`handoff --kind design` 交接方案，默认 `--kind implementation` 交接实施。
平台输入和冲突规则见[任务协作与交接](coordination.md)。沿用已有授权发布，之后重新读取
平台状态；批准记录必须实际出现在对应任务上，单独本地文件不能冒充共享批准。

外部仓库输入为 `{"kind":"repository","repository":"owner/repo","role":"build"}`，
`role` 还可为 `modified` 或 `joint`；本机目录通过 `--repository owner/repo=/path` 或
本地映射提供。检查的 `repository` 决定实际运行目录，前端检查需在前端仓库执行。
`evidence --evidence-repository owner/repo --path <仓内路径>` 保留原仓身份和内容指纹。

需要导入 GitHub Actions 实际结果或做多仓联合验收时，读取[跨机器结果](portable.md)。
入口分别为 `run --portable`、`import-result --result <定位文件>` 和
`aggregate --joint <联合清单> --repository owner/repo=/path`。原始报告和平台运行来源始终
需要核对。

## 重试与清理

材料按任务和请求分目录保存。`--request-id` 用于同一完成请求的重试：同编号且输入相同
返回原结果；变更输入或需要重跑时使用新编号，保留失败及中断材料。`--out` 只接受运行
目录下的新文件，已有路径拒绝覆盖。失败输出给出原因及下一步；不要改指纹消除错误。

```bash
python3 "$WF" cleanup --root "$PROJECT" > "$CLEANUP_PLAN"
python3 "$WF" cleanup --root "$PROJECT" --apply --plan "$CLEANUP_PLAN"
```

计划放在项目外，先核对预览再显式应用。期间材料变化会要求重新预览；只清理已结束
任务中未被引用的请求目录。完成证明必须覆盖当时的请求清单；同一任务后来出现新请求或旧请求被改写时，整个任务重新受保护。在途任务、共享批准历史和全部被引用证据保留，不用清理
代替修复缺口。发布、提交、合并、关闭任务和技能安装仍沿用已有授权。

## 前置任务与只读状态

任务节的 `blocked_by` 需要实际业务验收证明。为每个前置项保存
`{"section":"T1","task":".team-workflow/.../task.json","report":".team-workflow/.../delivery.json"}`，
在 `prepare`、`handoff` 或生成交付模板时重复传 `--dependency <输入文件>`。
工具重新核对前置项的原始报告与批准，不能用 Issue 已关闭代替验收。准备结果把本次
核对的材料保存在 context 中，后续最终交付仍重新核对。

`status` 只读取材料和批准，不执行项目命令；`status --report` 也不重新运行环境身份命令，
因此不宣称本轮业务验收完成。需要核对原始报告及当前环境时明确运行 `verify`。


## 业务场景与证据

方案仍用稳定编号分节。`scope-global.data.requirement_acceptance` 是非空的主需求验收编号；
其验证层次为完整业务路径或人工观察。`scope-global.data.impact` 每项包含 `repository`、
`entrypoint`、`operations`、`producer`、`consumer`、`commit_owner` 和 `acceptance` 编号列表。
主需求任务必须覆盖所列验收；子任务通过只返回 `acceptance_scope: task`。

每个验收节的 `data` 除 `checks` 外必须包含：

- `scenario`：`actor`、`initial_state`、非空 `steps`、`expected`、非空 `negative_cases`，以及
  `sources`：预期所依据的业务原文，每项 `{ref, version, confirmed_by}`，分别为 SOP 或需求原文
  的位置、版本和确认人。方案历史中的早期修订可以没有该字段；`prepare` 在 `verification_gaps`
  中列出缺少来源的验收项，`verify` 拒绝本任务任一验收项缺少来源。工具只核对字段齐全，不判断来源是否
  真实、是否独立于实现；补充来源会改变方案指纹，需要重新批准。
- `verification`：`method` 为 `automatic` 或 `manual`，`coverage` 说明实际范围，`cases`
  列出必须在原始运行中通过的准确用例编号。普通命令不能编造用例编号。

方案与检查配置中的 `coverage` 使用相同字段：`level` 为 `unit`、`interface`、`journey` 或
`manual`；`entrypoints` 为非空入口列表，`environment` 为具体环境名称，`substitutes` 列出
替代依赖。`isolation` 为 `isolated`、`shared-reviewed` 或 `unresolved`，`isolation_evidence`
记录隔离依据；共享资源必须有依据，未解决的隔离禁止执行相应检查。它补充已有环境身份
命令，不替代实际身份核对。自动证据可以覆盖同级或更完整的层次，但入口与环境必须匹配，
实际替代依赖不能超出方案声明。覆盖声明本身仍需评审实际测试代码与报告。

评审的每个验收项新增非空 `observations`：自动观察为
`{kind:"execution",run:{path,sha256},check:"检查编号",cases:["实际用例编号"]}`，其中运行必须
已经列入本任务的 `runs` 并通过原始报告核对；人工观察为
`{kind:"manual",observer,at,steps,result,coverage,evidence:[{path,sha256}]}`，时间含时区，
步骤和证据非空。纯文档可使用人工观察，不能把只有源码链接的描述当成已经运行。

评审的 `reviewer` 和每个人工观察的 `observer` 不能与方案 `roles.implementation_owner` 相同，
比较时忽略大小写和多余空格；实施者为空时不能验收。工具只比较记录的身份，无法证明两个不同
名称属于不同的人或会话，团队应为成员和代理使用稳定、可区分的身份名称。

## 问题处置与交接

方案 `issues`、评审 `findings`、进度与交接 `questions` 使用同一对象：

```json
{"id":"Q1","summary":"具体未决问题","owner":"实际负责人","affects":["A1"],
 "blocks":["implementation","acceptance"],"state":"open","resolution":{}}
```

`affects` 为空表示全局；`blocks` 明确阻塞实施、验收或两者。评估中的 `uncertainties` 只引用这些问题编号，具体问题正文保存在 `issues`。`state` 为 `open`、`resolved`、
`accepted`、`deferred`。关闭问题的 `resolution` 含非空 `reason` 与 `evidence` 来源列表；
接受限制另需 `confirmed_by`、`confirmation`；延期同样需要这两项，并另需 `follow_up`、`scope_change`。
已记录问题的编号、责任和影响不能在后续记录中悄然改变或删除；若原记录有误，明确处置
原问题再记录新的问题。验收方面的问题无需重新批准无关方案，但其处置仍须明确。

提交给 `verify` 的评审问题会保留在不可覆盖的请求材料中，即使本次验收失败，下一次模板
也会带入。共享平台的方案、交接历史与进度问题同样纳入核对。工具无法从任意自由文本
识别全部遗漏，评审人必须先把讨论中的已知问题写入这些字段。

交接 `verified` 改为原始执行或业务验收文件引用 `{path,sha256}`，跨仓引用可加 `repository`。
接手者需要原件及被引用输出；通过共享材料包或现有 `import-result` 提供。只给源码链接
不构成验证证明，源码链接放在 `references`。缺失原件会在接手或最终核对中保留缺口。
