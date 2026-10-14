# 团队流程的接入、更新与回退

从 `team-workflow` 开始新任务时使用团队流程。独立 MATT 方法仍只要求独立 CS
及已初始化的项目知识，不要求团队配置。先读取项目约定、真实测试入口和所用环境。

## 首次接入

1. 发现 CS 安装位置并执行只读预检，确认知识初始化已完成。缺项如实报告；已有初始化
   授权按 CS 执行，普通技能升级不重建知识库。
2. 运行 `workflow.py schema`，从返回的安装位置取得 `profile.json`、`task.json` 和方案
   模板。模板与技能一起安装，无须查找发行包外的示例。按项目实际代码替换占位内容。
3. 将配置保存为项目根的 `.team-workflow.json`，格式为 5；把运行目录 `.team-workflow/`
   加入项目忽略规则。业务检查和环境脚本继续由业务仓库维护，通用脚本直接从技能目录运行。
   项目的真实验证操作手册与本仓专属验收补充登记到 `context`，最低内容见
   [业务验收与质量改进标准](business-acceptance.md)第 6 节。手册按
   [项目验收方式与测试能力建设](test-capability.md)第 2 节为本项目设计，使用
   [项目验收方案](../templates/project-verification.md)模板，经项目开发与测试同事确认；
   尚无自动化入口的部分按该页记录过渡状态。通用规则不复制进项目文件。
4. 运行 `project --root <项目> --cs-skill <CS技能目录>` 检查配置和公开能力，再按
   [工具约定](contracts.md)准备任务及开工材料。模板和环境声明不代表已执行验证。
5. 运行 `guidance --root <项目>` 预览，确认后 `guidance --apply`：在项目的 AGENTS.md 写入
   “团队开发流程、需求完成门槛、安全边界”标记块，没有则新建；项目规则统一维护在
   AGENTS.md。CLAUDE.md 没有则新建，只放一行 `@AGENTS.md` 引用，已引用的保持不动。
   本机 `~/.claude/CLAUDE.md` 与 `~/.codex/AGENTS.md` 写入“需求交付与验收”标记块。工具只维护
   标记之间的内容，文件其余部分原样保留；项目文件随任务提交，本机文件不进仓库。
   技能升级后再次运行同步标记块；本仓专属补充写在标记块之外或 `context` 登记的文件里。

团队流程需要 CS 提供原文、回执核对、任务文件、结构化外部任务关联、独占计划文件和分类
复核提示能力。工具根据返回字段检查，不锁定 CS 的版本或源码提交。

## 测试账号与登录

在 `.team-workflow.json` 中用可选的 `accounts` 声明验收会用到的账号：

```json
"accounts": [
  {"id": "e2e-owner", "kind": "synthetic", "environment": "本地验收环境 localhost:3010",
   "login": "agent-after-authorization", "isolation": "每次运行独立的数据库与邮件捕获",
   "credential_env": ["E2E_OWNER_EMAIL"]},
  {"id": "shopify-partner", "kind": "real", "environment": "Shopify 合作伙伴后台", "login": "user"}
]
```

`real` 账号只能写 `login: user`。`synthetic` 账号必须说明隔离方式；`credential_env` 只写环境变量名，不写值。
`prepare` 在有可由代理登录的账号时返回 `authorizations_needed` 和要问用户的问题；用户同意后用
`prepare --grant synthetic-login --confirmed-by <用户>` 记录授权。授权只在本机准备上下文中有效，不随交接带出，
接手的会话需重新询问。未声明的账号按真实账号处理。

## 检查、环境和本机位置

默认检查、任务验收和风险映射取并集。鉴权、持久化、消息、并发及跨服务风险使用能证明
相关行为的真实入口检查，不能用普通单元测试扩大解释。拆分任务的风险按自身评估声明；
父方案的总体风险不自动复制给每一项。

每项检查明确声明 `environment`：完全不依赖可变外部状态时使用 `stateless`；依赖测试
数据库、服务或夹具时使用 `fixture`，由业务仓的只读命令返回可重复核对的身份。身份必须
体现影响结果的状态，不能用固定字符串掩盖变化。环境准备仍由业务仓负责。

共享配置仅保存规则、仓内路径与逻辑依赖。`.team-workflow/local.json` 的 `repositories`
和 `inputs` 只映射本机位置，不能覆盖检查要求。`--repository`、`--input` 的显式位置优先。
生成材料使用返回的任务与请求路径，不维护公共“当前任务”文件。

## 更新与回退

配置、任务和方案使用 `schema_version: 5`，本地证据使用 `schema_version: 6`。更新工具后运行：

```bash
python3 "$WF" adopt --root "$PROJECT"            # 预览
python3 "$WF" adopt --root "$PROJECT" --apply    # 写入 workflow_version，提交由成员自行完成
```

预览列出需要更新的配置字段，以及按任务分组的第六版之前的证据。旧证据不改写、不删除；列出的任务用当前
工具重跑一次检查，重新生成评审与交付报告后再验收。可选的
`workflow_version` 写明项目所需的最低工具版本；它或配置格式高于已安装工具时，所有读取
该配置的命令返回 `tool-outdated`，提示运行 `npx skills update -g`，不用旧工具解释新配置。
配置变化会使依赖整份配置指纹的执行结果过期，需重跑检查。

工具升级、CS 更新、消费项目配置调整分别进行。记录实际运行版本，不在检查过程中替换
工具。保留上一候选包和项目原配置以便回退，回退不清空 CS。源码更新不代表成员安装已更新，
通过 `workflow.py version` 与 `project` 核对当前工具和能力。

清理默认只预览。显式应用前核对计划，保留在途任务、所有被引用材料、共享批准历史及
交付证据；默认只删除已结束任务中未被引用的请求目录，`--cleanup-scope all` 另外处理过期且无引用的批次与导入。不要手工删运行目录来消除核查缺口。

本地 ZIP 构建不等于外部发布或团队推广。候选版可用于受控试用；正式推广仍须两位真实
成员双向接续并完成后续知识检索，实际缺口单独记录。
