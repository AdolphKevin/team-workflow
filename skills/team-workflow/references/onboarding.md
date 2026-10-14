# 团队流程的接入、更新与回退

从 `team-workflow` 开始新任务时使用团队流程。独立 MATT 方法只要求项目已有 `.tw/` 知识，不要求团队配置。先读取项目约定、真实测试入口和所用环境。下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`。

## 首次接入

1. 项目还有 `.codestable/` 或 `.team-workflow*` 时，先按 team-knowledge 的迁移指南迁移；全新项目运行 `tw init`（预览）和 `tw init --apply`，再填写 `overview.md`。
2. 运行 `tw team schema` 取得随技能安装的团队配置、任务和方案模板。按项目实际代码，把 `context`、`checks`、`required_checks`、`risk_checks`、`inputs`、`environment_versions` 等团队字段写进 `.tw/config.json`。业务检查和环境脚本继续由业务仓库维护。
   项目的真实验证操作手册与本仓专属验收补充登记到 `context`，最低内容见[业务验收与质量改进标准](business-acceptance.md)第 6 节。手册按[项目验收方式与测试能力建设](test-capability.md)第 2 节为本项目设计，使用[项目验收方案](../templates/project-verification.md)模板，经项目开发与测试同事确认；尚无自动化入口的部分按该页记录过渡状态。通用规则不复制进项目文件。
3. 运行 `tw team project` 检查配置、知识和安装，再按[工具约定](contracts.md)准备任务及开工材料。模板和环境声明不代表已执行验证。
4. 运行 `tw init --guidance` 与 `tw team guidance` 预览，确认后加 `--apply`：
   - 项目的 AGENTS.md 写入知识指引块和“团队开发流程、需求完成门槛、安全边界”标记块，项目规则统一维护在 AGENTS.md；
   - CLAUDE.md 只放 `@AGENTS.md` 引用，已有引用的保持不动；
   - 本机 `~/.claude/CLAUDE.md` 与 `~/.codex/AGENTS.md` 写入“需求交付与验收”标记块。
   工具只维护标记之间的内容。项目文件随任务提交，本机文件不进仓库。

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

共享配置仅保存规则、仓内路径与逻辑依赖。`.tw/local/repositories.json` 的 `repositories`
和 `inputs` 只映射本机位置，不能覆盖检查要求。`--repository`、`--input` 的显式位置优先。
生成材料使用返回的任务与请求路径，不维护公共“当前任务”文件。

## 更新与回退

- 项目数据只有一个版本号 `data_version`。没有破坏性变化时，升级技能不需要改动项目文件；数据版本高于已安装工具支持的版本时，工具拒绝读取并提示更新技能。
- 用 `npx skills add <仓库>#<标签> -g --skill '*'` 安装固定发行；升级时显式选择新标签，安装后运行 `tw version --check-install` 确认两个技能属于同一发行、文件未被改动。
- 工具升级与项目配置调整分开进行，并记录实际运行的版本。配置变化会使依赖整份配置指纹的执行结果过期，需要重跑检查。
- 回退时重新安装上一个标签。
