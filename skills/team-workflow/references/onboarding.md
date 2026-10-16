# 团队流程的接入、更新与回退

从 `team-workflow` 开始新任务时使用团队流程。独立 MATT 方法的接入要求见[方法与知识约定](matt-integration.md)。先读取项目约定、真实测试入口和所用环境。下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`。

## 首次接入

1. 项目还有 `.codestable/` 或 `.team-workflow*` 时，先按 team-knowledge 的迁移指南迁移；全新项目运行 `tw init`（预览）和 `tw init --apply`，再填写 `overview.md`。
2. 运行 `tw team schema` 取得随技能安装的团队配置、任务和方案模板。按项目实际代码，把 `context`、`checks`、`required_checks`、`risk_checks`、`inputs`、`environment_versions` 等团队字段写进 `.tw/config.json`。业务检查和环境脚本继续由业务仓库维护。
   项目的真实验证操作手册与本仓专属验收补充登记到 `context`，最低内容见[业务验收与质量改进标准](business-acceptance.md)第 6 节。手册按[项目验收方式与测试能力建设](test-capability.md)第 2 节为本项目设计，使用[项目验收方案](../templates/project-verification.md)模板，经项目开发与测试同事确认；尚无自动化入口的部分按该页记录过渡状态。通用规则通过链接引用。
3. 运行 `tw team project` 检查配置、知识和安装，再按[工具约定](contracts.md)准备任务及开工材料。
4. 运行 `tw init --guidance` 与 `tw team guidance` 预览，确认后加 `--apply`：
   - 项目的 AGENTS.md 写入知识指引块和“团队开发流程、需求完成门槛、安全边界”标记块，项目规则统一维护在 AGENTS.md；
   - CLAUDE.md 只放 `@AGENTS.md` 引用，已有引用的保持不动；
   - 本机 `~/.claude/CLAUDE.md` 与 `~/.codex/AGENTS.md` 写入“需求交付与验收”标记块。
   工具维护标记之间的内容。项目文件随任务提交，本机文件保存在本机。
5. 声明 `acceptance_entries` 验收入口，按需为项目搭建复测看板或转换脚本；格式与接入方法见[场景指南](scenarios.md)。将位置、启动方式和维护人写入项目验收方案并登记到 `context`。

## 项目平台脚本

初始化时，由代理按以下五步接入。使用本地任务时省略 `platform`。

1. **调查**：在项目根目录执行 `git remote -v`、`command -v gh glab tea`，确认远端和可用的平台命令行工具；用 `rg --files --hidden -g '!.git/**'` 查找并阅读已有 Issue、变更请求模板与持续集成配置。按远端选择已安装的客户端，用其只读列表命令查看现有 Issue、变更请求及关联关系，整理记录习惯与配置位置。
2. **确认**：向用户确认平台、方案和批准的位置、任务与变更请求的关联方式、是否导入持续集成结果。确认后生成脚本；选择本地任务则省略此项。
3. **生成**：按[平台契约](platform.md)生成项目脚本，并在 `.tw/config.json` 登记 `platform`。优先调用平台自己的命令行工具，其次用环境变量中的凭据发 HTTP 请求；只用 Python 3.10+ 标准库，只读平台。分页、重定向和已删除对象的处理见契约的[参数与输出](platform.md#参数与输出)，凭据处理见[错误与凭据](platform.md#错误与凭据)。
4. **验证**：挑一个评论较多的真实任务，对照平台原文人工核对读取完整性，运行 `tw team platform --check --id <真实任务地址>`；声明导入持续集成结果时，按契约补齐 `--locator <JSON>` 等参数。失败就修正，直到全部通过，保留检查结果供评审。
5. **记录**：按 team-knowledge 的[决策写法](../../team-knowledge/references/writing.md)写 `.tw/decisions/<日期>-task-platform.md`：记录背景与决定、备选及不采用理由、后果；写明平台、方案和批准的位置、Issue 与变更请求的关联方式、凭据来源（仅客户端或环境变量名）、脚本路径，`scope` 包含 `self:<脚本路径>`，`source` 指向确认依据。决策与脚本一起随变更请求评审提交。

变更请求描述只展示方案原文；任务如何找到变更请求，由项目平台脚本识别，例如在 Issue 正文中写变更请求地址。

用户同意时更新平台模板，提示中等以上任务先开方案草稿变更请求；记录按[方案格式](designs.md)追加。任务列验收编号，评审对照方案原文逐项核对预期、依据和证据。

## 接入后的任务

任务按[团队交付](team-delivery.md)执行，批准路径见[内容与依赖](designs.md#内容与依赖)。用 `--task <身份>` 读取材料，显式路径仍可用。`status` 列出有效记录和下一步。

## 测试账号与登录

在 `.tw/config.json` 中用可选的 `accounts` 声明验收会用到的账号：

```json
"accounts": [
  {"id": "e2e-owner", "kind": "synthetic", "environment": "本地验收环境 localhost:3010",
   "login": "agent-after-authorization", "isolation": "每次运行独立的数据库与邮件捕获",
   "credential_env": ["E2E_OWNER_EMAIL"]},
  {"id": "shopify-partner", "kind": "real", "environment": "Shopify 合作伙伴后台", "login": "user"}
]
```

`real` 账号写 `login: user`。`synthetic` 账号说明隔离方式；`credential_env` 写环境变量名。
`start` 在有可由代理登录的账号时返回 `authorizations_needed` 和要问用户的问题；用户同意后用
`start --grant synthetic-login --confirmed-by <用户>` 记录授权。登录操作与授权范围见[登录标准](business-acceptance.md#6-真实验证操作手册的最低内容)。

## 检查、环境和本机位置

默认检查、任务验收和风险映射取并集。鉴权、持久化、消息、并发及跨服务风险使用能证明
相关行为的真实入口检查。拆分任务的风险按自身评估声明。

每项检查明确声明 `environment`：独立于可变外部状态时使用 `stateless`；依赖测试
数据库、服务或夹具时使用 `fixture`，由业务仓的只读命令返回可重复核对的身份。身份必须
体现影响结果的状态。环境准备仍由业务仓负责。

共享规则与本机位置按[配置与外部引用](../../team-knowledge/references/writing.md#配置-twconfigjson)维护。
生成材料使用返回的任务与请求路径。

## 更新与回退

- 项目数据版本为 `data_version`；数据版本高于工具支持的版本时，工具拒绝读取并提示更新技能。
- 用 `npx skills add <仓库>#<标签> -g --skill '*'` 安装固定发行；升级时显式选择新标签，安装后运行 `tw version --check-install` 确认两个技能属于同一发行、文件未被改动。
- 工具升级与项目配置调整分开进行，并记录实际运行的版本。配置变化会使依赖整份配置指纹的执行结果过期，需要重跑检查。
- 回退时重新安装上一个标签。
