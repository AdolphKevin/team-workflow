# 未发布（0.9.0-dev，合并重构）

- 方案只读仓库 Markdown 原文，新增解析、渲染和字段对照，删除 JSON 方案模板；发布记录仅引用本地 git 提交中的路径与摘要，PR 描述展示原文。任务、方案发布、批准、交接、进度及评审绑定改用安全的隐藏 `tw-record` 注释；旧代码块拒绝并要求重新生成，正文去掉首尾空行及行尾空白，渲染加入排版空行；单值标签直接书写，多值项只按实际分隔符加必要引号。分节指纹与局部重审语义不变。
- 接入指南新增“项目平台脚本”五步：调查、用户确认、按契约生成、真实任务检查与决策评审，以及可选平台模板和本地任务方式；`tw init`（含 `--guidance`）在有 git 远端但未配置平台时提示该节，不阻止初始化。接入指南登记 4,000 字符预算。
- 方案和批准可记在变更请求描述及评审，分节批准与局部重审不变；批准新增可选 `revision`，合并批准核对本地提交源码。新增 `review --from-platform`，`deliver` 在没有已提交评审时自动导入平台评审，保留绑定、逐项复核、问题历史及姓名核查；平台作者与地址只作记录，不限制评审账号。中等、复杂任务先评审草稿变更请求中的方案再实施，作为团队约定。
- 平台读取改由项目登记的只读脚本完成，删除内置 GitHub 读取；新增四操作契约、原始响应存档及 `tw team platform --check`。任务与仓库身份支持任意主机，持续集成导入保留来源、归属、摘要及二次读取核查。
- `tw brief`：完整条目的来源改为摘要（首个链接或首项，加总数）；任务路径与条目的守护测试文件相同时按 scope 选中；related 双向扩展一层，并按写入仓的配置解析跨仓别名；“继续阅读”等导航按行截断，不再整节消失，输出不超过预算。JSON 新增 `listed`，表示条目在输出中可见；回放脚本改报 `recall_full`、`recall_visible`。迁移指南的准备步骤补充：守护测试需要的环境先确认能运行。
- 破坏性变化：team-workflow 与 CS 合并为一个仓库、一个运行时。新增知识入口 `team-knowledge`，命令行为 `tw`；团队命令改为 `tw team <命令>`。项目内只保留 `.tw/` 一个目录：入库的 `config.json`、`overview.md`、`glossary.md`、`rules/`、`decisions/`、`lessons/`，以及被忽略的 `local/`。`.codestable/`、`.team-workflow.json`、`.team-workflow/` 不再使用，已接入项目由代理按迁移指南整理，不提供迁移脚本。
- 知识直接编辑 Markdown，与代码在同一个 PR 评审。`tw check` 只查客观缺陷，`tw brief` 有字符预算，并会提醒“放弃过的做法”。删除计划令牌、锁、回执、内容指纹、`future_use`、11 类目录与任务记录入库。
- 团队流程删除与 CS 的桥接：`knowledge`、`knowledge-template`、`adopt` 命令，以及 `--cs-skill`、`--profile` 参数。交付报告的 `knowledge` 改为“改动的知识文件或不需要的理由”。只提交知识不再使按内容绑定的检查过期。
- 最终交付必须引用本任务通过的业务验收记录：`delivery-template --acceptance` 写入交付报告的 `acceptance`，`verify` 核对它属于本任务，且验收后任务、方案章节、源码以及执行、评审、批准材料都没有变化；收尾说明引用这份原件。`knowledge.files` 必须正好列出本任务相对 `base` 改动的知识文件（含删除）；缺少处置时说明要列出文件或写明理由。请求编号的输入指纹包含 `--acceptance` 与当前知识内容，改了其中任何一项都需要新的请求编号。
- 安装检查分两层：正在运行的两个技能决定 `verify` 是否放行（`tool-modified`）；客户端目录中被改动、含符号链接或版本不同的副本，以及残留的旧技能 cs，只作提示（`project` 的 `warnings`），`tw version --check-install` 对两者都返回非零。
- 本地任务目录为可读名称加完整身份的哈希，Issue 地址相近的仓库不再落到同一目录。
- 流程简化（T7）：团队命令新增 `start`（取代 prepare、resume）、`review`（取代 review-template 和手写评审 JSON）、`accept`（取代 `verify --phase acceptance`）、`deliver`（依次完成业务验收、交付报告和最终核查）；参数归入各自的子命令，全局只保留 `--root` 与 `--repository`。不改知识的简单任务只需 `start`、`run`、`review --submit`、`deliver` 四条命令。
- 每个任务记录当前材料组（`current.json`），`start` 之后各命令只需 `--task <身份>`；材料缺失、被改动、平台方案更新时拒绝，并给出修正命令。
- 评审改为 Markdown：评审人只写结论和理由，运行结果、证据引用与问题历史由工具生成；源码或运行变化后生成复核稿，逐项改为“已复核”才能提交；不通过的评审也可以提交，问题会保留。`run` 成功后自动生成评审稿；简单任务的方案与代码合并批准随评审提交；`approval-draft` 支持 `--reviewer`、`--confirmation`、`--mode`。
- `status` 只列已核实的记录，删除恒为 False 的字段，失败步骤给出修复命令；关闭须最终交付完成、收尾说明或交接已发布，并记录关闭授权，工具不执行关闭。
- 执行记录按检查配置的命令模板保存，其余参与核对的路径均为相对路径；检出目录搬动或复制后，原有运行、评审与验收仍然有效，不必重跑。
- `scripts/test.py` 按用例并行运行全量测试（默认最多 8 个进程，`--workers 1` 顺序运行），汇总为同一份 JUnit；本机全量从约 12 分钟降到约 3 分钟。
- 版本只保留软件发行版本与项目 `data_version` 两个轴；安装改为固定发行标签。
- MATT：锁文件如实记录为 `main@b0618bc`；改为通过 team-knowledge 读取知识；词汇表与 ADR 遵循原文优先，并用日期加 slug 命名；修复悬空的 tracker doc 与词汇表引用；规格、拆分、实现、多任务实现和复盘五个方法恢复上游的“只允许显式调用”。

# 0.8.0-rc.1（合并前的最后候选）

- 独立试用后的修正：安装被修改时 `verify`、`knowledge` 与 `project` 统一返回 `error_code: tool-modified`（CS 被修改同样如此，`project` 在顶层给出原因）；`project` 的 `tool` 带 `override`；`verify` 输出直接包含 `summary_markdown`、`re_evaluated`、`close_note` 与 `tool`；缺少登记用例时列出报告中实际的用例名；方案范围缺口改为可读说明；收到 SIGTERM 时停止检查的进程组并清除验证标记；`status` 把最近一次中断或失败的尝试作为下一步，已被后续成功取代的失败记为未记录，优先采用未使用 `--allow-modified-tool` 的结果，最终交付步骤包含 `delivery-template`；配置模板的 `workflow_version` 与工具版本一致并由发布检查核对。
- 修复交接核对的崩溃：带 `verified` 原始记录的完成交接调用了未导入的 `read`，交接时抛出 `NameError`。`verified` 指向源码文件时给出明确缺口，不再报 JSON 解析错误。新增两仓共用、字节相同的 `scripts/lint_undefined_names.py`（基于编译器作用域表，只用标准库），`check_release.py` 运行它并逐个导入工具模块；未预期的异常返回 `error_code: tool-defect` 并写出请求结果。
- 一条 CS 任务记录可以绑定多个 Issue 的验收：`knowledge-template` 的 `--acceptance` 可重复，配合 `--with-task`；草稿写入 `task.source.workflow_acceptances` 与每个任务的 `external_refs`，全部验收后才为 `completed`，返回 `pending_acceptance`。`knowledge` 只传本任务的验收，核对 CS 记录包含其当前指纹，不再要求整表相等。原单值 `workflow_acceptance` 不再生成。
- 证据模型（本地证据记录升为 `schema_version: 6`；配置、任务、方案与平台记录仍为 5，不需要改写 Issue）：执行定义不再包含 `required_cases`、`purpose`、`timeout`，修改用例登记后用原始报告重新判定，无需重跑；每项检查独立选取当前结果，批次中一项过期只需 `run --check` 聚焦重跑，结果列出 `superseded_execution`；环境只在业务验收时实际核对，`knowledge` 与最终 `verify` 使用验收记录的环境，夹具清理后已完成的验收仍有效；工具升级不再使所有执行记录过期（执行绑定改为结果解码版本）。
- 登录按账号类型区分：配置可选 `accounts` 声明真实账号（只能由用户登录）与本地隔离测试账号；`prepare` 返回 `authorizations_needed` 与要问用户的问题，`--grant synthetic-login --confirmed-by` 记录一次性授权；分发指引与业务验收标准同步改写，未声明的账号按真实账号处理。
- `status` 列出任务步骤、状态和填好路径的下一条命令（`--format text` 可直接阅读），中断后据此继续；准备上下文记录 `rules_digest`，规则在任务中途变化时提示。每个请求记录命令、阶段、完成时间与耗时；新增只读 `metrics` 统计请求、失败、耗时与检查重跑次数，供每周复盘参考。
- 单人任务收尾：交接新增 `close` 类型。被指派人只有实施负责人、没有修改或联合仓库、没有跨服务风险时，最终 `verify` 生成“收尾说明”草稿（`close_note`）代替单独的实施交接，发布后 `resume` 返回 `closed: true`；其他情况仍要求实施交接并说明原因。
- 新增 `issue-draft`：为没有结构化任务块的 Issue 一次生成正文、方案评论和给具体评审人的评审请求草稿，原有说明逐字保留；读取平台的命令遇到这类 Issue 返回 `issue-not-adopted` 并给出命令。
- 交接缺口“存在未共享的改动”现在列出具体文件，并提示把 `.DS_Store` 等本机文件加入 `.git/info/exclude`，不必为此推送提交。
- 验收与最终核查结果新增 `summary_markdown`：用平实语言说明验证了什么、哪些检查通过、还有什么没做、交付和关闭状态。
- 新增 `adopt`：预览或写入配置的 `workflow_version`，按任务列出第六版之前的证据；旧证据只保留为历史。
- `cleanup --cleanup-scope all` 清理过期且无引用的批次、导入与结束进程的验证标记，列出不归工具管理的手工输出及大小、可回收体积和最大文件；`evidence` 与评审证据拒绝编译后的可执行文件，超过 64 MiB 需显式允许。
- 安装完整性：技能目录附带 `MANIFEST.json`（`scripts/package.py --manifest` 生成，`check_release.py` 校验）；`version` 与 `project` 报告 `integrity`，已安装副本被修改时 `project` 返回 `tool-modified`，`verify` 与 `knowledge` 拒绝执行，除非显式 `--allow-modified-tool`（记入结果的 `tool.override`）。要求 CS 声明 `contract_version: 1`、`task-source-acceptances`、`install-integrity` 且自身完整。

- 只保留当前记录格式（`schema_version: 5`）：配置、任务、方案、批准、交接、执行、导入与联合清单不再读取或转换第一至四版。删除 `migrate`、`upgrade`、`adopt`、`stage-draft` 命令及阶段流程、旧版约定、旧版结果导入与交接代码；`workflow_version` 只用于在项目要求更新的工具时提示更新，不再提示项目升级。`agents` 子代理台账保留，说明移入业务验收标准的派遣协议。
- 文件去掉版本后缀：`contracts.md`、`coordination.md`、`portable.md`、`commands.py`、`contracts.py`、`portable.py`（合并原跨机器结果模块）及对应测试；真实 CS 检查分为 `check_cs_knowledge.py` 与 `check_cs_delivery.py`。删除旧版示例配置和历史验证快照，验证记录只保留当前版本。
- `verify` 对非对象的执行记录给出明确错误，不再抛出未处理异常。
- 方案批准只要求写明批准人，确认依据 `confirmation` 改为可选；批准、方案、交接和进度记录不再要求评论作者本人就是记录中的批准人或负责人，可由他人代为记录。每条平台记录保留实际发布评论的账号 `recorded_by`，`load` 返回 `approval_records`，同时列出批准人和记录人以便追责。问题处置标为接受限制或延期时同样只要求确认人 `confirmed_by`，`confirmation` 可选。
- 业务验收标准扩展为团队共同标准：首次验收由未参与实现的测试同事、用户或 AI 执行；回归按业务保证选择单元、集成或 E2E，缺陷回归须保留原问题的失败证据；E2E 写清起终点与替代依赖；本机与 CI 入口、交付证据范围、缺陷关联与每周开发测试共同复盘。新增交付验收、缺陷复验与保护、每周质量复盘三份记录模板。
- 新增[项目验收方式与测试能力建设](skills/team-workflow/references/test-capability.md)：指导成员或代理调查项目事实、列出关键业务保证、选定层次与观察点，为各项目设计匹配的验收方式，记入新增的[项目验收方案](skills/team-workflow/templates/project-verification.md)模板并经开发与测试确认，项目之间不照搬工具与命令；项目尚无集成或 E2E 入口时，人工验收通过后整体交付写为“人工验收通过，自动回归未完成（待建设）”，由首个需要的需求建设最小入口并提供干净运行、重复运行、故意失败和 CI 实跑证据；给出浏览器、接口与数据库、消息接收端、消息消费者与定时任务、模型与智能体输出的常见检查要点，其他入口按共同理念推导；接口与数据库要点吸收了确切值断言、负向场景清单、业务仓维护的数据库运行器约定和“受阻”判定，不再依赖成员本机技能；模型与智能体输出按确定性合同程序断言、场景驱动真实对话并冻结证据、未参与实现的 AI 或人独立语义复核三层验收，复核结论与运行状态分离。
- 交付报告新增可选 `automation`，按场景声明 `automated`、`manual-only`、`pending-automation`；待建设条目须引用延期问题并给出期限。`verify` 结果新增 `automation_status` 与 `regression_pending`，`delivery_complete` 含义不变，`assurance` 说明它不代表回归已自动化。未声明时结果为 `not-declared`，旧报告不受影响。
- 分发指引恢复五条常驻的需求完成门槛，正文仍只在业务验收标准维护。
- 验收场景新增 `sources`（业务原文位置、版本、确认人）：`prepare` 列出缺少来源的验收项，`verify` 拒绝缺少来源的验收；方案历史中的早期修订仍可读取，补充来源需重新批准。`verify` 拒绝评审人或人工观察人与方案实施者相同的验收。
- 修正 `profile.json` 模板：示例检查 `unit` 的覆盖层次改为 `unit`，避免照抄后夸大覆盖范围。
- 新增随技能分发的[业务验收与质量改进标准](skills/team-workflow/references/business-acceptance.md)：需求完成门槛、主代理与子代理派遣协议、从 SOP 到自动回归的四步流水线、交付报告最低内容、项目真实验证操作手册的最低内容。主技能、团队交付和接入指南引用该页；项目文件只保留本仓专属补充。
- 新增 `guidance`：默认预览，`--apply` 在项目 AGENTS.md（没有则新建，CLAUDE.md 只放 `@AGENTS.md` 引用）与本机 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md` 写入标记块，内容来自随技能分发的 `templates/guidance-*.md`；只维护标记之间的内容，未安装的客户端跳过，标记损坏时拒绝写入。
- 项目配置的 `workflow_version` 或格式高于已安装工具时，所有命令返回 `tool-outdated` 并提示 `npx skills update -g`。

# 0.5.0-rc.1

- 新增显式开启的阶段流程：S0–G3 阶段、G1/G3 用户确认关卡、决策项、硬暂停触发器和固定汇报格式；默认仍按目标选择方法。
- 父 Issue 评论中的 `team-workflow-stage` 记录作为唯一状态源；推进阶段不修改需求正文，不影响已有交接和审查。
- 新增只读 `status`（阶段、等用户决定的事、子任务与父任务能否关闭）和 `stage-draft`（只生成阶段评论草稿）。
- 新增 `agents` 子代理台账：恢复会话时复用已完成结果，其余由当前代理串行补做或询问用户，不再自动重新并发启动；降级必须写明未覆盖范围。
- 规格、任务拆分、多任务实现和审查方法在阶段流程下增加决策项、入口层测试接缝、子 Issue 验收块、禁止额外检出时的串行模式，以及"规格轴对照原始需求"。

# 0.3.0

- 建立独立公开发行源码，使用新的干净 Git 历史。
- 直接复用 MATT 1.3.1 的 15 个技能与配套资源，保留来源、许可及可校验差异。
- 连接独立 CS 2.1.0，统一检索原文与经验；交付绑定原文状态。
- 保留原有执行、审查、跨仓聚合和失败语义，增加真实 CS 接口验证。
