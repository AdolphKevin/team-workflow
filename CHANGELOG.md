# 未发布

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
