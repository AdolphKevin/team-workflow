# 第四版工具约定

> 历史资料，仅供读取原记录。当前任务统一使用[第五版约定](contracts-v5.md)，先 `adopt` 补齐缺项；不按本页继续旧执行流程。

新任务使用本页；第二、三版在途任务继续读取[原工具约定](contracts.md)。运行环境为
Python 3.10+、Git 和项目自身的测试依赖。通用工具只使用标准库。

下文 `$WF` 是已安装技能的 `scripts/workflow.py` 路径，`$PROJECT` 是项目目录，
`$CS_SKILL` 是发现的独立 CS 技能目录。输入路径相对项目，输出使用命令返回的
`artifact.path`，不要假设公共固定文件名。默认返回 JSON，`--format text` 用于阅读。

## 配置与任务

```bash
python3 "$WF" schema --root "$PROJECT"
python3 "$WF" project --root "$PROJECT" --cs-skill "$CS_SKILL"
python3 "$WF" upgrade --root "$PROJECT" [--record "$UPGRADE_INPUT"] [--apply]
```

`project` 的 `version.status` 为 `current`、`project-outdated` 或 `tool-outdated`。
项目较旧时用 `upgrade` 预览、`--apply` 写入；项目较新时返回 `tool-outdated`，先更新
已安装技能。规则见[接入指南](onboarding.md#升级与回退)。

`schema` 返回随技能安装的[配置模板](../templates/profile.json)、[任务模板](../templates/task.json)
和[方案模板](../templates/design.json)。模板需要按实际项目填写；配置放在根目录
`.team-workflow.json`，手工任务输入及运行材料放在被 Git 忽略的 `.team-workflow/`。

| 第四版配置字段 | 含义 |
| --- | --- |
| `schema_version`、`project` | 固定格式 4，以及项目稳定名称 |
| `context` | 必须读取的现有仓内文件 |
| `knowledge` | `provider: cs`，入口固定为 `.codestable/wiki/INDEX.md` |
| `checks` | 检查编号到具体命令、报告格式、用例及环境要求的映射 |
| `required_checks` | 分别为 `code`、`docs` 指定默认检查 |
| `risk_checks` | 风险到非空检查集合；缺少风险映射会报错 |
| `inputs` | 参与结果但被 Git 忽略的文件或目录 |
| `external_inputs` | 逻辑依赖及用途，本机位置另行提供 |
| `environment_versions` | 名称到只读版本查询命令数组 |
| `workflow_version` | 最近一次对齐配置的工具版本，由 `upgrade --apply` 写入 |

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

任务使用 `schema_version: 4`，包含 `id`、真实存在的完整基准提交 `base`、`goal`、
`non_goals`、`kind`（`code` 或 `docs`）、`risks`、`acceptance`，以及关联的 `design_id`
和非空任务节数组 `section_ids`。验收项为 `{id, expectation, checks}`。`paths`、
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
知识文件、暂存布局和无关流程配置变化不会自动重复业务测试。

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
保存验收产物路径 `$ACCEPTANCE`，再按 CS 的完整规则写回最终结果。首次任务关联示例：

```bash
python3 "$CS_SKILL/scripts/cs_knowledge.py" --root "$PROJECT" template \
  --title '<实际任务标题>' --external-ref 'github=https://github.com/owner/repo/issues/123' \
  --output "$CS_PAYLOAD"
```

本地任务改用 `--external-ref 'team-workflow=<实际任务ID>'`；继续已有 CS 任务时使用
`template --task-id <实际CS任务ID>`。填写实际结果、验证和知识处置，不把未通过验收的
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

## 平台草稿、跨仓和外部结果

`design-draft --issue ... --record ...`、`approval-draft --issue ... --record ...`、
`progress --issue ... --progress ...` 和 `handoff --issue ... --progress ...` 只生成共享
记录草稿。`handoff --kind design` 交接方案，默认 `--kind implementation` 交接实施。
平台输入和冲突规则见[第四版协作与交接](coordination-v4.md)。沿用已有授权发布，之后重新读取
平台状态；批准记录必须实际出现在对应任务上，单独本地文件不能冒充共享批准。

外部仓库输入为 `{"kind":"repository","repository":"owner/repo","role":"build"}`，
`role` 还可为 `modified` 或 `joint`；本机目录通过 `--repository owner/repo=/path` 或
本地映射提供。检查的 `repository` 决定实际运行目录，前端检查需在前端仓库执行。
`evidence --evidence-repository owner/repo --path <仓内路径>` 保留原仓身份和内容指纹。

需要导入 GitHub Actions 实际结果或做多仓联合验收时，读取[第四版可移植结果](portable-v4.md)。
入口分别为 `run --portable`、`import-result --result <定位文件>` 和
`aggregate --joint <联合清单> --repository owner/repo=/path`。旧版材料保留原有可信范围，
不自动转换成新版验证；原始报告和平台运行来源始终需要核对。

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
