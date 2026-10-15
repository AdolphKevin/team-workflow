# 工具约定

项目配置是 `.tw/config.json`，本地证据放在被 Git 忽略的 `.tw/local/`。配置、任务、方案、平台记录和本地证据统一使用
`data_version: 1`；迁移前旧目录中的证据不用于新的验收。
运行环境为 Python 3.10+、Git 和项目自身的测试依赖，通用工具只使用标准库。

下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`，团队命令写作 `tw team <命令>`；`$PROJECT`
是项目目录，`$TASK_ID` 是任务 `id`（本地编号或完整 Issue 地址），`$TASK` 是首次开工的任务文件。输入路径相对项目，输出使用命令返回的 `artifact.path`，不要假设公共固定文件名。默认返回 JSON，
`--format text` 用于阅读。

全局参数只有 `--root` 和可重复的 `--repository`，可写在团队子命令前后，也可由外层 `tw` 转发。
其余参数写在对应命令之后：`tw team --help` 列出命令，`tw team <命令> --help` 列出该命令可用的参数。
例如 `tw team --root "$PROJECT" run --task "$TASK_ID" --check unit`；业务验收用 `accept`，最终交付用 `verify`。

## 配置与任务

```bash
tw team schema --root "$PROJECT"
tw team project --root "$PROJECT"
tw init --root "$PROJECT" --guidance [--apply]
tw team guidance --root "$PROJECT" [--scope project|global|all] [--file AGENTS.md] [--apply]
```

`project` 同时核对安装完整性：`installation.integrity.status` 为 `intact`、`modified`（列出 `changed`、`missing`、
`unexpected`）或 `unknown`（缺少 `MANIFEST.json`）。正在运行的两个技能不是 `intact` 或不属于同一发行时返回
`error_code: tool-modified`，`accept` 和 `verify` 拒绝执行；客户端目录中其他副本被改动、版本不同或残留旧技能 cs，只列在 `warnings`。发现工具缺陷时报告缺陷并重装，不修改已安装的技能。确需带改动运行时加
`--allow-modified-tool`，结果中的 `tool.override` 为真并随记录保留。`project` 同时报告配置校验结果、
`tw check` 的错误数，以及两个技能是否来自同一发行（`tw version --check-install`）。
工具自身缺陷返回 `error_code: tool-defect`，保留请求目录作为证据。

项目配置的 `data_version` 高于已安装工具支持的版本时，工具拒绝读取并提示更新技能；
规则见[接入指南](onboarding.md#更新与回退)。

`tw init --guidance` 维护 AGENTS.md 中的知识指引块；`tw team guidance` 默认预览，`--apply` 只写入标记块：项目指令文件得到[项目指引](../templates/guidance-project.md)，
本机 Claude Code 与 Codex 的用户级文件得到[全局指引](../templates/guidance-global.md)。项目规则只写
`AGENTS.md`（没有则新建）；`CLAUDE.md` 没有则新建并只放 `@AGENTS.md` 引用（[引用模板](../templates/guidance-claude.md)），
已含 `@AGENTS.md` 或 `@./AGENTS.md` 的保持不动；`--file` 只接受仓内相对路径，引用随之指向该文件。每个目标的
`action` 为 `create`、`append`、`update`、`unchanged`、`skipped`（该客户端目录不存在）或 `blocked`（标记损坏，
整次拒绝写入）。写入保留原文件的换行风格、权限和符号链接。`--home` 只用于试验，指向替代的用户目录。`schema` 返回随技能安装的[团队配置模板](../templates/config.json)、[任务模板](../templates/task.json)
和[方案模板](../templates/design.json)。模板需要按实际项目填写；团队字段写入 `.tw/config.json`，
手工任务输入及运行材料放在被 Git 忽略的 `.tw/local/`。

| 配置字段 | 含义 |
| --- | --- |
| `format`、`data_version`、`project` | 由 `tw init` 生成：工具标识、数据版本 1、`{id, name}` 项目身份 |
| `context` | 必须读取的现有仓内文件 |
| `shared`、`documents` | 共享知识仓与原文登记，见 team-knowledge 写作规范 |
| `checks` | 检查编号到具体命令、报告格式、用例及环境要求的映射 |
| `required_checks` | 分别为 `code`、`docs` 指定默认检查 |
| `risk_checks` | 风险到非空检查集合；缺少风险映射会报错 |
| `inputs` | 参与结果但被 Git 忽略的文件或目录 |
| `external_inputs` | 逻辑依赖及用途，本机位置另行提供 |
| `environment_versions` | 名称到只读版本查询命令数组 |

检查包含 `argv` 参数数组、`purpose`、仓内 `cwd`、秒数 `timeout`、`format`、
`required_cases`、`required_env` 和 `environment`。命令不经 shell，凭证通过环境传递，
只记录必要变量名；日志仍遵循项目脱敏规则。

本地与可携带执行记录的 `argv` 均保存配置模板，保留 `{output}`；核查与当前模板比较，改动仍使该检查过期。启动进程时才将 `{output}` 展开为绝对路径。输出目录由 `stdout.txt` 等产物的相对路径确定，项目整体移动或复制不要求重跑。

`format` 可为 `command`、`go-json` 或 `junit`。普通命令只能证明退出结果，不能声明
用例。Go 解析 `go test -json`；JUnit 需要 `report: "{output}/results.xml"`，命令必须
生成这次运行的新报告。必要用例使用准确的 `包::测试名` 或 `classname::name`。未指定
必要子集时全部发现的用例均须通过；指定后仍拒绝任何失败、必要跳过、缺失和零用例。
额外产物放在 `{output}/` 内；已有业务场景审查要求继续保留，不能用工具摘要替代。

`environment` 必须明确为 `{"kind":"stateless"}`，或
`{"kind":"fixture","identity":["业务仓的只读命令","参数"]}`。前者只用于不依赖
可变外部数据的检查；后者必须真实表达服务、数据库或夹具的有关状态。身份无法核实时
不复用结果。`revision_sensitive: true` 仅用于实际依赖 Git 提交编号的检查。

任务使用 `data_version: 1`，包含 `id`、真实存在的完整基准提交 `base`、`goal`、
`non_goals`、`kind`（`code` 或 `docs`）、`risks`、`acceptance`，以及关联的 `design_id`
和非空任务节数组 `section_ids`，以及 `acceptance_scope`（主需求 `requirement`，子任务 `task`）。子任务的 `parent` 指向方案所属主需求。验收项为 `{id, expectation, checks}`；本地任务文件可只写 `{"id":"A1"}`，由 `start` 按本次方案同编号验收节的 `body` 和 `data.checks` 补全，完整任务保存进上下文并参与指纹。显式文字或检查清单不一致仍拒绝；平台任务块须写全。`paths`、
`symbols` 和跨仓 `scopes` 提供知识读取范围；实际子任务可保留 `parent`。

支持的风险为 `authorization`、`persistence`、`concurrency`、`messaging`、
`public-contract`、`cross-service`。它们决定检查，不决定是否必须事前评审。父方案和
拆分任务分别评估；任务节的 `data.assessment` 可覆盖方案评估。具体方案和逐节批准格式
见[分节方案约定](designs.md)，不要根据父方案复杂度替代子任务判断。

## 开工材料、状态与方案

```bash
tw team start --root "$PROJECT" --task "$TASK" --design "$DESIGN"
tw team start --root "$PROJECT" --task "$TASK_ID"
tw team status --root "$PROJECT" --task "$TASK_ID" --format text
```

平台任务也可用 `start --issue <完整Issue链接>` 读取共享任务和方案。已有批准使用
可重复的 `--approval`，历史方案用可重复的 `--design-history`，从第 1 版保留完整快照。
读取平台失败时报告缺口，不退回本地材料后声称平台交付完成。
所请求的 Issue 缺少任务块时返回 `issue-not-adopted`；已接入的子 Issue 所引用的父 Issue 缺块时，
返回 `parent-issue-not-adopted`，并指向父 Issue 的地址及 `issue-draft --task <parent-task.json>` 补齐命令。

`start` 首次建立准备上下文，返回 `continued: false`；任务内容、方案、批准、历史、前序依赖或授权变化时建立新上下文，`superseded_context` 指向被取代的记录。输入相同返回 `continued: true`，核对接续条件，只在自己的请求目录保存本次简报和 `start.json`。省略方案或批准时沿用原准备材料；同一任务的本机授权继续有效。平台任务首次可用 `--issue`，之后也可用 `--task <完整 Issue 地址>`。

两种结果都含任务身份、任务目录、当前上下文 `context.path`、实施条件、缺口和 `next_step`。后续用 `--task "$TASK_ID"` 自动补齐材料；也可显式指定 `--context <上下文路径>`。必须实际阅读简报；保存文件
不证明知识已经使用。新批准在 `start` 后传 `--approval` 会建立新上下文；实施后的代码批准也可传给 `review`、`accept` 和 `delivery-template`，保留原开工简报。历史变化传 `--design-history`。
`status` 从当前材料组或显式 `--context`、`--report` 读取已有批准，不接受 `--approval`。

### 当前材料组

任务目录的 `current.json` 使用 `data_version: 1`、`kind: current-materials`，每项材料为 `{path, sha256}`：

| 字段 | 材料 |
| --- | --- |
| `context`、`task`、`design`、`brief` | 准备上下文、补全的任务、方案、开工简报 |
| `design_history`、`approvals` | 方案历史和批准列表 |
| `runs` | 本上下文的全部运行列表，包含失败运行 |
| `review`、`acceptance` | 验收所用评审、通过的业务验收记录 |
| `review_markdown` | 提交成功的评审 Markdown 原文；兼容旧组中缺少此项 |
| `review_source` | 提交时的源码逐文件指纹；兼容旧组中缺少此项 |
| `delivery_report`、`delivery` | 交付报告、通过的最终交付记录 |

`start` 新上下文整组重置，接续不重置。`run` 追加实际运行，即使检查失败；其余命令成功后才更新。评审表和批准草稿的输出不登记；实际批准首次显式指定，评审由 `review --submit` 成功后登记。`selected_runs` 记录显式选用的运行，保留 `runs` 中的全部历史；新运行追加后恢复从全部记录选取。写入用临时文件加改名，并与清理共用锁；并发开工发生冲突时明确拒绝，换请求编号重试。

`run`、`status`、`review`、`approval-draft`、`accept`、`delivery-template`、`verify`、`handoff`、`progress`、`task-export` 均支持任务身份，也保留任务文件和显式路径。命令只补齐自身使用的材料；`verify` 自动读取交付报告，`delivery-template` 自动带上验收记录。显式材料优先，成功使用后登记；同身份显式切换上下文会完整换组，清除原组的运行与下游材料。跨身份上下文拒绝。

记录缺失、指纹变化时拒绝，结果点名材料并给出修正命令。平台方案/批准更新时执行命令拒绝，status 列出受影响的过期步骤并提示重新 `start`；不按文件时间猜材料。自动材料与显式材料一起参与请求指纹。同一请求编号换组仍拒绝，重复成功请求不重复追加材料。只有身份的 `status` 不写入；显式替换经成功核对后更新记录。

```bash
tw team design-diff --root "$PROJECT" --task "$TASK" --design "$NEW_DESIGN" \
  --design-history "$V1" --design-history "$V2"
```

`design-diff` 比较最后一份旧版和当前版，保留完整历史删除。`status` 和接续时的 `start` 汇总材料及缺口；业务验收由 `accept` 核对，最终交付和关闭条件由 `verify` 核对。

## 实施、批准与代码评审

```bash
tw team run --root "$PROJECT" --task "$TASK_ID"
tw team run --root "$PROJECT" --task "$TASK_ID" --with-task "$OTHER_TASK"
```

任务、项目默认及风险检查取并集；`--with-task` 可重复。同一批次每项检查执行一次，
各任务仍单独验收。可重复 `--check` 做聚焦运行，最终核查仍要求全部必要检查。
结果绑定源码内容、逻辑依赖、执行定义及环境；源码或环境在运行期间变化不能通过。

任务方案的范围（`scope`）要包含实际改动的全部文件，测试文件也算在内；否则验收报告未映射的文件。方案变化后的 `start` 建立新上下文，需要重新运行检查和评审；输入相同的接续保留原开工材料。因此修正方案范围最好在运行检查前完成。

执行定义是实际执行的内容（命令、目录、报告格式、环境声明、覆盖范围等）。`required_cases`、
`purpose` 和 `timeout` 只影响结果判定，不属于执行定义：修改它们后，核查用保存的原始报告按当前登记
重新判定，不需要重跑；验收结果的 `re_evaluated` 列出这些检查及原判定，`summary_markdown` 用平实语言说明。
第六版记录在交接和收尾说明中也采用相同的重新判定，保留原记录的状态与原始报告。
`run` 报告缺少登记用例时会列出报告中实际的用例名，便于发现前缀写错。`accept` 和 `verify` 的输出直接包含 `summary_markdown`，
`--format text` 时打印出来。登记变化仍会改变评审策略，需要重新生成评审。

每项检查独立选取结果。一份批次中某项检查过期，只影响这一项：用 `run --check <该项>` 聚焦重跑，
运行自动追加到当前组，必要时也可显式用 `--run` 选取。核查为每项检查选用当前有效的最新通过结果，失败、过期或被替代的记录列在
`superseded_execution` 中。环境只在业务验收（`accept`）时实际核对；之后的
最终 `verify` 使用验收时记录的环境（`environment_checked: recorded at acceptance`），
隔离数据库等夹具清理后已完成的验收仍然有效。源码、定义、评审和平台在每一步都重新核对。
旧候选的原始报告不符合当前用例要求时，只记录该候选的问题，继续选择其它候选；导入记录也遵守离线环境核查规则。
知识正文（`.tw/` 下的条目）、暂存布局和无关流程配置变化不会使按内容绑定的检查过期。运行期间的协作标记位于 `.tw/local/validation-active/`；共享目录保持稳定。标记不拦截编辑器写入，起止指纹也不证明期间绝无改动。

方案批准通常直接用具名参数生成，无需手写输入 JSON：

```bash
tw team approval-draft --root "$PROJECT" --task "$TASK_ID" --reviewer <姓名> --confirmation <说明> --mode plan
```

`confirmation` 可省略；简单任务在评审 Markdown 中选择合并批准。已有输入仍可用 `--record <输入文件>`，其 `reviewer` 必填，`confirmation` 可选；批准可以由他人代为记录。

也可使用任务文件，明确传 `--design`、`--run` 等路径。输入可指定 `decision`、`section_ids`、
`deletion_ids`、`mode`、可选 `revision`；选择部分章节时需明确覆盖相应上游依据。简单任务默认合并评审，
中等、复杂任务默认方案评审；具体模式和删除选择见[分节约定](designs.md)。合并评审
绑定当前代码和传入运行材料。没有任何已配置必要检查的纯文档任务可以没有运行记录，
验收仍须真实评审证据；省略记录不能绕过已配置的检查。草稿不产生批准事实。

`approval-draft --revision <提交号>` 记录批准时变更请求的完整提交号（40 或 64 位十六进制），
也可在 `--record` 输入中提供 `revision`。合并批准读取本地该提交的源码，计算与
`code_digest` 相同口径的摘要；不等时拒绝并说明“批准的提交与绑定的源码不一致”。本地
缺提交时明确报告缺口，不访问平台。方案批准只校验格式、记录在案；未带字段的记录行为不变。

```bash
tw team review --root "$PROJECT" --task "$TASK_ID"
# 编辑返回的 review.md，再提交
tw team review --root "$PROJECT" --task "$TASK_ID" --submit
# 也可提交另一处的 Markdown
tw team review --root "$PROJECT" --task "$TASK_ID" --submit --file <评审.md>
# 评审人已把填写后的完整 Markdown 作为变更请求评审提交时
tw team review --root "$PROJECT" --task "$TASK_ID" --from-platform
```

`--from-platform` 经项目平台脚本的 `task` 操作，选出含绑定区的最新 `kind: review` 条目，
将其原文走与 `--submit` 相同的绑定比对、逐项复核、问题历史和转换流程。与 `--file`、
`--submit` 二选一，不能混用来源。绑定或来源已变时拒绝，需重新生成复核稿。
导入时要求平台评审作者不同于该任务所有 `change` 条目的作者；缺少变更请求描述时报告
“无法核对平台身份”。评审 JSON 增加 `platform_author`、`platform_url`，验收仍核对
Markdown 姓名不能是实施负责人；以后复用也核对平台作者和已存原文。正文与评论中的讨论
不能替代 `review` 条目。平台上的合并批准选择经原文核对后可作为已共享批准。

任务目录的 `review.md` 是可编辑表，绑定未变的未提交文件只报告路径和填写进度。评审人实际阅读代码、需求与原始结果，填写评审人、知识冲突是否已处理（是/否）、规范与需求及各验收项的结论（通过/不通过）和理由。各轴及验收项可补充证据文件，每行一个项目内路径；工具计算指纹，自动验收的运行、检查、用例引用无需手写。人工观察的观察人、带时区的时间、操作、结果、数据及证据文件全部由人填写。只引用源码不能证明执行已通过。

绑定区包含任务、任务与源码指纹、校验策略、章节和运行；它与工具填写的结果、风险列表及变化说明均不可改动。提交只检查格式完整和绑定有效，拒绝时指出行号或小节；“不通过”、知识冲突未处理或含 open 阻塞问题的完整评审仍保存。独立性、实际检查与通过条件由 accept/deliver 核查，不因此放宽。成功后原文 `review.md`、现有格式的 `review.json` 与 `review-source.json` 保存到本次请求目录，登记为当前评审。下一条命令为 `deliver --task <身份> --reason <理由>`；需要更新知识则先 `accept --task <身份>`，写知识后再交付。清理保留引用的原文、JSON、源码指纹、运行和任务目录的未提交表。

问题按 `### 问题 Q1` 分节，以 `- 字段：值` 填写编号、负责人、影响范围、阻塞阶段、状态及摘要。已知问题身份不得改动或删除；新问题可新增同格式小节。状态为 open、resolved、accepted、deferred；非 open 要填写处置理由与处置证据，接受或延期还需确认人，延期须含跟进任务与范围调整，可附确认依据。完整字段由已知问题自动展开；没有已知问题时可按下表添加。

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

Markdown 评审格式为第 2 版，草稿绑定保存在任务目录的 `reviews/<草稿编号>/binding.json`，编辑与明确的上一轮提交记录保存在 `reviews/editor.json`。业务评审 JSON 仍用原格式。每次提交保存 `review-source.json`（`data_version: 1`、`kind: review-source`），包含被评审源码的逐文件指纹；变化比较使用保存的文件内容与属性，不使用时间。外部输入按 `[名称]/路径` 区分。新增、删除和修改文件均列在“变化”中；只改文件时间不会使评审过期。旧记录没有逐文件指纹且源码总指纹已变化时，明确说明无法还原精确差异，要求全部预填项重新核对；总指纹相同则可证明没有源码变化，不猜测历史。

已有提交的评审与当前任务、源码、校验策略、章节、风险或选中运行不同，再运行 `review --task <身份>` 会预填上一轮的评审人、知识冲突处理、规范与需求结论、各验收结论和证据、人工观察及问题清单。实际运行区换成当前结果，“变化”还列出运行结果改变的验收项。新增失败候选仍按既有规则选择通过的运行；选中运行不变时不会仅因多了失败候选而重开评审。绑定不变时只报告当前已提交评审仍然有效。

过期的未提交 `review.md` 会改名保存到 `reviews/archived-<唯一编号>.md`，结果的 `archived_draft` 给出原文路径与指纹；新稿优先预填该工作稿已填写的内容。绑定未变的工作稿仍保持原样。

所有预填的规范、需求、验收结论与人工观察分别带 `复核：待复核`。评审人核对后必须逐项改为 `复核：已复核`；即使改写结论或理由，也必须明确确认。删掉字段、只确认部分或使用其他值均不能提交；一次错误列出全部未确认小节和行号。自动证据取当前运行，补充证据路径重新核对指纹；人工观察内容不由工具改写，由人确认仍适用或填入新观察。问题身份沿用原有一致性核查，处置可以更新。

`status` 将绑定变化的已提交评审标为过期。没有当前复核稿时下一条命令是 `review`；新稿已生成后指向 `review --submit`，完成逐项确认后才能形成新的有效评审。

生成复核稿所用的上一轮评审、Markdown、源码快照和绑定引用也进入请求指纹。同一请求编号不能换一份前序评审；提交本身的同组幂等重试仍按原规则处理。

## 先验收，再更新知识

### 四命令交付入口

```bash
tw team start --root "$PROJECT" --task <任务文件> --design <方案>
tw team run --root "$PROJECT" --task "$TASK_ID"
# 编辑 run 返回的 review.md，填写评审及“批准方案与代码：是”
tw team review --root "$PROJECT" --task "$TASK_ID" --submit
tw team deliver --root "$PROJECT" --task "$TASK_ID" --reason <不需要更新知识的理由>
```

`run` 成功且本任务必需检查全部有可用的通过结果后，自动按现有评审/复核规则准备草稿，输出 `review_file` 和提交命令；失败或尚缺必需检查时不生成。任务需已有 `start` 上下文。绑定未变的未提交稿保持原样；绑定变化时按复核规则留存旧稿。手动 `review` 保留。

方案中当前任务评估为 simple 且尚缺有效合并批准时，评审信息增加“批准方案与代码”和可选“批准说明”。填“是”后，工具以评审人为批准人，按原合并批准规则绑定当前源码与选中运行、只覆盖本任务必需章节；批准与评审同为请求材料，成功后登记当前批准。填“否”或留空不产生批准，验收仍检查批准是否齐全；实施者的意见可以保存，但不会生成独立合并批准，业务验收仍拒绝自审。已具备事前方案批准的中等、复杂任务不显示这两个字段。源码或选中运行改变后，合并批准失效，预填的批准字段也须明确复核。带批准字段的草稿另绑定完整方案与历史内容，不能用旧稿批准新材料组中的方案评估。

`approval-draft` 可用 `--reviewer <姓名> [--confirmation <说明>] [--mode plan|combined] [--revision <完整提交号>]` 替代 `--record`；两种输入二选一。CLI 的 plan 对应既有记录中的 design 模式；combined 绑定当前源码与运行。`--record` 及原 JSON 格式保留。

`deliver` 顺序调用原来的 `accept`、`delivery-template`、`verify`，各步保留请求和材料并更新 `current.json`。先核对已有验收是否仍绑定当前任务、章节、源码和材料；可用则复用，否则实际重新验收。报告列出相对任务 base 的全部知识变化；没有变化必须提供 `--reason`。要改知识时仍先独立 `accept`，写完知识后 `deliver` 复用该验收。绑定和知识处置均有效的报告也可复用；已有理由不必再输入。

没有已提交评审且项目配置了平台时，`deliver` 先执行 `review --from-platform`；导入失败停在 `review` 步骤，已有提交不自动替换。本地项目仍给出 review.md 路径和提交命令。评审不通过时，accept/deliver 汇总规范、需求、验收项及相关阻塞问题和理由，并给出修复后重跑、复核命令。任何一步失败即停止，结果的 `steps`、`stopped_at` 和 `next_action` 给出已完成步骤、原因及下一条命令；最终输出保留 `delivery_complete`、`closable`、`summary_markdown` 及平台任务的 `close_note`。中断后用默认新请求编号或显式新编号继续，已登记且仍有效的验收和报告不重复生成；同一成功请求的同组重试仍幂等。平台核查、独立性、知识完整性及关闭授权不变，不执行发布或关闭。

```bash
tw team accept --root "$PROJECT" --task "$TASK_ID" \
  --out .tw/local/acceptance-<本次唯一编号>.json
```

成功结果中的 `business_accepted` 为真，但 `delivery_complete`、`closable` 仍为假。
`accept` 按身份取准备材料和运行，结合实际填写的评审生成验收报告，保存在自己的请求目录；已有报告仍可用 `--report`。批准可选，省略时使用当前组的批准；简单任务的代码批准须绑定本次运行。记录已有所需评审与批准时，后续 `accept --task "$TASK_ID"` 可以省略其路径。报告生成后仍完整核对实际运行、独立评审、观察与问题记录。

验收通过后，按 team-knowledge 的写作规范在同一分支直接修改 `.tw/` 条目：根因不明显的缺陷写 lesson，
难以逆转的选择写 decision，改变了必须保持的行为写 rule；没有可复用结论时不写。运行 `tw check`，修复全部错误。

交付报告的 `knowledge` 字段写知识处置：

```json
"knowledge": {"files": [".tw/lessons/2026-10-14-retry-storm.md"], "reason": ""}
```

`delivery-template` 根据任务 `base` 到工作区的 Git 差异预填 `files`；没有知识改动时 `files` 为空，
必须在 `reason` 写明不需要更新的理由。`.tw/.gitignore` 和 `config.json` 不算知识。多个 Issue 共用一次实现时，知识改动只写一次，各任务的报告分别列出。

```bash
tw check --root "$PROJECT"
tw team delivery-template --root "$PROJECT" --task "$TASK_ID"
tw team verify --root "$PROJECT" --task "$TASK_ID"
```

交付模板自动登记。需要填写理由、自动化声明或其他报告字段时，将模板复制为新文件填写，再用 `verify --task "$TASK_ID" --report <填写后的报告>` 显式指定；不要改动已经登记的文件后直接按身份核查。成功后记录该报告，之后可省略路径。

`verify` 只核查最终交付：报告的 `acceptance` 必须指向本任务通过的业务验收记录（上面
`accept --out` 的产物）。验收之后任务、方案章节、源码，以及交付报告引用的执行、评审、
批准材料都不能变化，否则用当前材料重新验收。`files` 必须正好列出本任务相对 `base` 改动的知识正文
（含删除、未跟踪的新文件），`delivery-template` 已按此预填；`tw check` 必须没有错误；`files` 为空时
`reason` 必填。工具不判断知识是否充分，这由评审人确认。知识正文不参与执行绑定，
提交知识不会使按内容绑定的检查过期。

Issue 身份自动触发平台核查，漏传 `--issue` 不能绕过。交付完整还需要当前交接无剩余事项、
未决问题及未确认进度。关闭另需明确授权：报告可记录 `close_authorization: {confirmed_by, reference}`；
工具仅报告状态，不执行关闭。

### 回归自动化状态

`delivery_complete` 只表示验收、知识处置和交接记录齐全，不表示应沉淀的回归已经自动化。
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
  的问题，由它携带确认人、跟进任务和范围调整（确认依据可选）；`blocks` 写 `acceptance`，记录
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
平台状态；批准记录或携带合并批准选择的绑定评审必须实际出现在对应任务上，单独本地文件不能冒充共享批准。

外部仓库输入为 `{"kind":"repository","repository":"host/group/repo","role":"build"}`，
`role` 还可为 `modified` 或 `joint`；本机目录通过 `--repository host/group/repo=/path` 或
本地映射提供。检查的 `repository` 决定实际运行目录，前端检查需在前端仓库执行。
`evidence --evidence-repository host/group/repo --path <仓内路径>` 保留原仓身份和内容指纹。

平台读取遵守[平台脚本契约](platform.md)；导入实际结果或做多仓联合验收时，读取[跨机器结果](portable.md)。
入口分别为 `run --portable`、`import-result --result <定位文件>` 和
`aggregate --joint <联合清单> --repository host/group/repo=/path`。原始报告和平台运行来源始终
需要核对。

## 重试与清理

材料按任务和请求分目录保存。`--request-id` 用于同一完成请求的重试：同编号且输入相同
返回原结果；`--allow-modified-tool`、`start --grant` 和 `--confirmed-by` 也属于请求输入。
变更这些选项、其它输入或需要重跑时使用新编号，保留失败及中断材料。`--out` 只接受运行
目录下的新文件，已有路径拒绝覆盖。失败输出给出原因及下一步；不要改指纹消除错误。

```bash
tw team cleanup --root "$PROJECT" [--cleanup-scope all --older-than 14] > "$CLEANUP_PLAN"
tw team cleanup --root "$PROJECT" --apply --plan "$CLEANUP_PLAN"
```

`--cleanup-scope all` 另外清理超过指定天数且未被任何记录引用的 `batches/`、`imports/` 目录和已结束进程留下的
验证标记。手工 `--out` 输出及其他目录不归工具管理，只在 `unmanaged` 中列出大小，从不删除。`totals` 给出
总体积、可回收体积和最大的 20 个文件。

`current.json` 引用的材料仍在使用，不会被清理。

证据只保存评审者能阅读的内容。`evidence` 与评审证据拒绝编译后的可执行文件（ELF、Mach-O、PE）；
构建产物用构建提交和命令说明，不复制进运行目录。超过 64 MiB 的文件需显式 `--allow-large-evidence`。
使用该选项时，引用中保存 `allow_large_evidence: true`；最终核查按引用中的布尔标记重新检查大小。
未带标记的引用仍受 64 MiB 限制，本地与外部仓库相同；标记不能覆盖编译产物限制。

计划放在项目外，先核对预览再显式应用。期间材料变化会要求重新预览；只清理已结束
任务中未被引用的请求目录。完成证明必须覆盖当时的请求清单；同一任务后来出现新请求或旧请求被改写时，整个任务重新受保护。在途任务、共享批准历史和全部被引用证据保留，不用清理
代替修复缺口。发布、提交、合并、关闭任务和技能安装仍沿用已有授权。

## 进度、恢复与统计

```bash
tw team status --root "$PROJECT" --task "$TASK_ID" --format text
tw team metrics --root "$PROJECT" [--task "$TASK"] [--since 2026-10-01] [--format text]
```

`status` 读取当前组和请求记录，列出六步状态及 `next_step`。只把核实有效的验收、交付记录放入 `verified_records`（键为 `acceptance`、`delivery`，值含 path/sha256），不返回恒为 false 的 business_accepted、delivery_complete、closable 等判断。它不执行检查或环境命令，不能代替新的业务验收。

步骤为 `done`、`pending`、`stale`、`failed`、`running-or-interrupted` 或 `not-recorded`；只有成功提交的评审算完成。已提交且绑定有效的评审后，验收、报告、最终核查均指向 `deliver`。平台方案/批准更新、显式传入不同内容的方案、源码或配置绑定变化时，受影响步骤过期；过期记录不列为有效。不同内容的显式方案不会被 status 悄然登记，须重新 start。相同内容换路径仍可经核对登记。

全部完成显示“已交付；关闭需要授权，工具不执行关闭”。平台任务的 `publication` 列出收尾说明/交接的实际发布状态、类型和评论地址；本地草稿不能证明发布。关闭须最终交付完成、收尾或完整交接已发布，且报告含 `close_authorization: {confirmed_by, reference}`；工具只报告 closable。详见[关闭步骤](team-delivery.md#状态与关闭-issue)。

会话中断后先查看 status；`rules_changed` 表示开工后团队规则文本有变化。运行记录仍按内容、配置及声明的提交敏感性核对；使用修改版工具的证据有明确标记。

`metrics` 只读本机运行目录，按任务统计各命令的请求次数、失败与未完成次数、耗时，以及每项检查的运行和重跑次数，
供每周复盘参考；它不联网，也不是质量结论。

## 前置任务与只读状态

任务节的 `blocked_by` 需要实际业务验收证明。为每个前置项保存
`{"section":"T1","task":".tw/local/.../task.json","report":".tw/local/.../delivery.json"}`，
在 `start` 或 `handoff` 时传 `--dependency <输入文件>`；准备上下文保留这些输入，`accept` 和交付模板沿用，变化时重新 `start`。
工具重新核对前置项的原始报告与批准，不能用 Issue 已关闭代替验收。准备结果把本次
核对的材料保存在 context 中，后续最终交付仍重新核对。

`status` 不执行项目命令；仅用身份查看不写材料，显式替换成功核对后更新当前组。`status --report` 也不重新运行环境身份命令，
因此不宣称本轮业务验收完成。需要核对原始报告及当前环境时明确运行 `accept`。


## 业务场景与证据

方案仍用稳定编号分节。`scope-global.data.requirement_acceptance` 是非空的主需求验收编号；
其验证层次为完整业务路径或人工观察。`scope-global.data.impact` 每项包含 `repository`、
`entrypoint`、`operations`、`producer`、`consumer`、`commit_owner` 和 `acceptance` 编号列表。
主需求任务必须覆盖所列验收；子任务通过只返回 `acceptance_scope: task`。

每个验收节的 `data` 除 `checks` 外必须包含：

- `scenario`：`actor`、`initial_state`、非空 `steps`、`expected`、非空 `negative_cases`，以及
  `sources`：预期所依据的业务原文，每项 `{ref, version, confirmed_by}`，分别为 SOP 或需求原文
  的位置、版本和确认人。方案历史中的早期修订可以没有该字段；`start` 在 `verification_gaps`
  中列出缺少来源的验收项，`accept` 和 `verify` 拒绝本任务任一验收项缺少来源。工具只核对字段齐全，不判断来源是否
  真实、是否独立于实现；补充来源会改变方案指纹，需要重新批准。
- `verification`：`method` 为 `automatic` 或 `manual`，`coverage` 说明实际范围，`cases`
  列出必须在原始运行中通过的准确用例编号。普通命令不能编造用例编号。

方案与检查配置中的 `coverage` 使用相同字段：`level` 为 `unit`、`interface`、`journey` 或
`manual`；`entrypoints` 为非空入口列表，`environment` 为具体环境名称，`substitutes` 列出
替代依赖。`isolation` 为 `isolated`、`shared-reviewed` 或 `unresolved`，`isolation_evidence`
记录隔离依据；共享资源必须有依据，未解决的隔离禁止执行相应检查。它补充已有环境身份
命令，不替代实际身份核对。自动证据可以覆盖同级或更完整的层次，但入口与环境必须匹配，
实际替代依赖不能超出方案声明。覆盖声明本身仍需评审实际测试代码与报告。

下述是工具生成的评审 JSON，评审人无需手写。每个验收项有非空 `observations`：自动观察为
`{kind:"execution",run:{path,sha256},check:"检查编号",cases:["实际用例编号"]}`，其中运行必须
已经列入本任务的 `runs`，且正是该检查选中的有效记录，并通过原始报告核对；不能引用失败或已被替代的记录来
借用另一记录的通过结果。人工观察为
`{kind:"manual",observer,at,steps,result,coverage,evidence:[{path,sha256}]}`，时间含时区，
步骤和证据非空；Markdown 中的“结果”和“数据”一起保存到 `result`，保持原 JSON 格式。纯文档可使用人工观察，不能把只有源码链接的描述当成已经运行。

评审的 `reviewer` 和每个人工观察的 `observer` 在业务验收时不能与方案 `roles.implementation_owner` 相同，
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
接受限制另需确认人 `confirmed_by`，确认依据 `confirmation` 可选，与方案批准一致；延期同样需要
确认人，并另需 `follow_up`、`scope_change`。
已记录问题的编号、责任和影响不能在后续记录中悄然改变或删除；若原记录有误，明确处置
原问题再记录新的问题。验收方面的问题无需重新批准无关方案，但其处置仍须明确。

成功提交的 Markdown 和交给 `accept`、`verify` 的既有 JSON 评审问题，都保留在不可覆盖的请求材料中；即使评审不通过或本次验收失败，问题仍进入历史，下一次评审表也会带入。共享平台的方案、交接历史与进度问题同样纳入核对。工具无法从任意自由文本
识别全部遗漏，评审人必须先把讨论中的已知问题写入这些字段。

交接 `verified` 改为原始执行或业务验收文件引用 `{path,sha256}`，跨仓引用可加 `repository`。
接手者需要原件及被引用输出；通过共享材料包或现有 `import-result` 提供。只给源码链接
不构成验证证明，源码链接放在 `references`。缺失原件会在接手或最终核对中保留缺口。
