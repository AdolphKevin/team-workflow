# 本仓收缩为项目知识库，SOP 验收与回归沉淀归 sop-board（草案修订 1）

> 状态：已批准，待实施。日期：2026-10-22。批准：AdolphKevin 2026-10-22 会话中答复“批准”（修订 1 全文）。
> 配套方案：sop-board 仓库 `docs/proposals/2026-10-22-acceptance-standard-and-distill.md`。
> 调查基线：本仓 `8be02e4`，sop-board `436d1ab`；对照的上游为 mattpocock/skills `5beb35b`、affaan-m/ECC（原 everything-claude-code）`90606c8`，均为 2026-10-22 调查时的提交。
> 修订 1：按用户 2026-10-22 的四项决定（第 8 节）与两轮独立审查修改。

## 0 摘要

1. **本仓只发行 `team-knowledge`**：`.tw/` 知识格式与 `tw brief/read/check/init/new/audit/cache/version`。成员用自己的工作流开发，在任何工作流里读写同一份项目知识。
2. **SOP 场景验收与回归沉淀只由 sop-board 发行。** 本仓删除 `tw team`（含场景验收）、业务验收标准、`playwright-acceptance` 副本；标准正文迁到 sop-board。
3. **MATT 由使用者自行安装上游**，本仓删除 15 个 `matt-*` 副本与补丁。
4. **`.tw/config.json` 的 `checks` 退出**：知识条目的 `guards` 直接写 `仓库:文件#测试名`；测试的运行命令与必跑要求进入产品仓库脚本与 CI。

## 1 依据

- **重复**：sop-board 已独立发行，不读取 `.tw/config.json`，场景格式由它自己的校验器定义；本仓的场景验收与之功能重叠，同时安装时其中一套多余。
- **团队流程不是好体验的来源**：一次评价良好的真实开发对话（2026-10-21，某多仓项目的认领规则修复）全程只调用了 `tw brief` 与 `tw check`，没有任何 `tw team` 命令。它的好体验来自：先确认业务规则、规则写成 `.tw` 条目、贴近上下文的任务说明、经真实入口自检并查库、实现后由用户一句话发起分层回归测试沉淀，以及条目 `guards` 指向这些测试。其中真实入口与独立验收的要求来自业务验收标准（迁往 sop-board），分工来自使用者自己的全局指引。
- **与 MATT、ECC 重叠**：方法选择、需求拆分、方案与批准、评审、交接、状态与恢复等能力，在 MATT 或 ECC 中有等价或部分对应。两者都没有的几项按第 2 节落位：评审绑定源码由 Git 平台分支保护（新推送使旧批准失效）承担；多仓版本与原始证据由 sop-board 承担；逐节批准失效、评论对账与流程请求统计随团队流程退出。

## 2 职责落位

| 职责 | 新位置 |
| --- | --- |
| 项目知识的读取、更新、结构检查 | team-knowledge（不变） |
| 业务验收标准、场景、独立执行、证据、复核、缺陷、复测、统计 | sop-board |
| 已确认场景沉淀为回归测试 | sop-board 随包技能，在开发会话或看板中使用 |
| 测试的运行与必跑要求 | 产品仓库脚本与 CI |
| 验收入口与测试账号的操作说明 | 产品仓库的真实验证手册（唯一正文）；sop-board 工作区只保存本机绑定并引用手册 |
| 测试账号的使用授权 | 任务开始时向用户取得一次授权，记录环境、账号范围与操作范围，同一任务沿用 |
| 方案、拆分、实现、评审方法 | 使用者自选（上游 MATT、ECC 或自有流程） |
| 独立评审与合并控制 | Git 平台：PR 评审、分支保护、代码负责人 |
| 问题处置、交接、关闭 | Issue/PR；长期结论写 `.tw` |

## 3 运行时与配置

保留顶层知识模块：`tw.py`、`cli`、`brief`、`read`、`check`、`entries`、`project`、`init`、`new`、`audit`、`cache`、`install`、`frontmatter`、`gitutil`、`globs`、`repo_paths`、`textmatch`、`files`。删除 `tw_runtime/team/` 与 `cli` 中的团队分发。

- `audit.py` 改用自己的本机目录分类与大小统计，不再导入 `team.cleanup`。
- 配置解析只认知识字段 `format/data_version/project/context/shared/documents` 与仓库映射。其余现有字段（`checks`、`required_checks`、`risk_checks`、`platform`、`inputs`、`external_inputs`、`environment_versions`、`acceptance_entries`、`accounts`）原样保留在文件中，`tw check` 逐项给出去向提示（见第 5 节）并以 0 退出。
- `guards`：`仓库:文件#名称` 照常校验文件存在且包含该名称；`check:名称` 给出改写提示。说明文字写明：引用存在只表示测试可追溯，测试是否运行由 CI 证明。
- `init`、`install`、`version --check-install` 只针对 team-knowledge 自身。`tw init --guidance` 只维护项目知识指引块。
- `tw team ...` 返回“团队流程已移除”与本方案链接，非零退出。
- `format` 标识保持 `channelwill/team-workflow`，已有项目无需修改配置。

## 4 技能、发行与本仓文档

- **删除**：`skills/team-workflow/`、`skills/playwright-acceptance/`、`skills/matt-*`、`upstream/`、`docs/upstream.md`，以及只属于 MATT 的许可文件。
- **team-knowledge 技能与参考文档**：技能正文补一句“与使用的开发流程无关”。`references/writing.md` 中 `guards` 的写法改为 `仓库:文件#测试名` 并写明“引用只表示可追溯，运行由 CI 证明”；`references/migration.md` 删除迁入检查配置与在途团队任务的步骤。
- **现行入口文档**：`README.md`、`AGENTS.md`、`docs/design.md`、`docs/install.md`、`docs/member-guide.md`、`docs/acceptance.md`、`docs/validation.md` 改写为只描述知识库；保留的验证记录中指向移动或删除文件的链接同步更新。
- **发行**：`scripts/check_release.py`、`scripts/release_text_rules.py`、`scripts/package.py`、`VERSION`、运行时版本、`MANIFEST.json`、`plugin.json`、`.claude-plugin/plugin.json` 与 `marketplace.json`、`.github/workflows/validate.yml` 改为单技能；发行包内容检查只含 team-knowledge 与公开文档。版本升为 `1.0.0`，CHANGELOG 写移除项与第 5 节迁移方法。
- **本仓知识**：引用拟删除目录的知识文件共 28 个（`.tw/overview.md`、`config.json`、2 条规则、3 条决策、21 条教训，以实施时 `rg` 的实际清单为准）。逐条处理：
  - 结论对知识层仍成立的，作用范围改到仍存在的位置；
  - 只关于团队流程实现的教训，并入 `decisions/2026-10-14-one-repository-one-runtime.md` 改写后的“放弃过的做法”，注明删除原因，条目删除；
  - `decisions/2026-10-14-one-repository-one-runtime.md` 改写为“本仓只发行知识库”；`2026-10-19-standalone-sop-verification.md`、`2026-10-19-playwright-acceptance-skill.md` 改写为“SOP 验收与沉淀由 sop-board 发行”；`2026-10-15-task-platform.md` 与 `rules/platform-contract.md` 删除，原因写入同一决策；`.tw/platform.py` 删除。
  - 完成后 `tw check` 0 错误，规则不放宽。
- **历史文档**：`docs/proposals/` 正文保持原样，指向已删除文件的链接改为固定提交的永久链接，文首加历史标记；`docs/sop/` 中 tw 团队流程的场景文件移入 `docs/sop/archive/`，同步其中的相对路径。
- **公开文本清理**：现行文档、历史方案、验证记录、夹具与知识条目中的内部仓库名、项目名、个人本机路径、站点与单号改为通用示例；不改写 Git 历史。

## 5 已采用 tw 的项目如何升级

| 现有内容 | 去向 |
| --- | --- |
| `.tw/` 知识条目 | 原样可用 |
| `checks`、`required_checks`、`risk_checks` | 运行命令与必跑用例写进产品仓库脚本与 CI；CI 需能发现用例被跳过、数量为零、或声明的必跑用例未被执行；覆盖说明留在对应规则或验证手册；之后删除这些字段 |
| `platform`、`inputs`、`external_inputs`、`environment_versions`、`.tw/platform.py` | 只服务于团队流程，删除 |
| `guards` 中的 `check:名称` | 改写为 `仓库:文件#测试名` |
| `acceptance_entries`、`accounts` | 操作、账号类别、隔离与清理写进产品仓库的真实验证手册；sop-board 工作区 `entries` 按其契约重新填写（例如 `surface` 取 sop-board 的取值，长篇说明放手册），并引用手册章节 |
| 场景文件 | 主体字段可复用；按 sop-board 契约整理后登记，旧 `regression` 人工说明移入场景 `expected` 或验证手册 |
| 在途的 `tw team` 任务与 `.tw/local/` 材料 | 升级前用旧版完成或放弃；材料原样保留，由成员确认后自行删除 |
| 已安装的 `team-workflow`、`playwright-acceptance` 及来自本仓的 `matt-*` | 用安装工具按来源移除；需要 MATT 时安装上游；保留成员自行安装的其他技能 |
| 全局与项目指引中的 team-workflow 团队块 | 由使用者删除或替换为 sop-board 提供的推荐文字；保留使用者自写内容 |

## 6 验收

新场景文件 `docs/sop/tw-knowledge-only.yaml`，由未参与实现的执行者经命令行真实入口在临时项目中执行。预期依据为本方案第 3、5 节与现行知识写作规范。

- **SOP-01 知识命令独立可用**：P01 只装新版 team-knowledge，`init`→`new`→`brief`→`read`→`check`→`audit` 完成一次开工读、完成后更新：`brief` 选中作用范围覆盖所改路径的条目并给出原因；与路径、任务词组、显式引用和关联都不匹配的条目不被选中。P02 跨仓 `shared` 映射的条目可经 `read` 读到原文。
- **SOP-02 从旧版升级**：P01 用带全部旧团队字段、`check:` 引用、`.tw/local/` 团队材料的项目升级：知识命令正常；`check` 逐项给去向提示并以 0 退出；`.tw/local/` 原样保留。P02 `tw team status` 返回移除说明并非零退出。N01 `guards` 指向不存在的测试名时 `check` 报错。
- **SOP-03 发行内容**：P01 本仓 CI 的检查与打包两步通过；ZIP 只含 team-knowledge 与公开文档；安装后 `version --check-install` 通过。N01 ZIP 中不含 `team-workflow`、`playwright-acceptance`、`matt-*`；全文检索不含内部标识。
- **SOP-06 旧场景迁入 sop-board**：P01 取本仓 `docs/sop/` 中一份带 `regression` 人工说明的旧场景文件，按第 5 节整理后经 `sop-board` 登记成功，人工说明保留在场景 `expected` 或验证手册中。
- **SOP-07 旧技能与指引清理**：P01 在装有旧版全部技能与全局、项目团队指引块的机器上按第 5 节升级：来自本仓的 `team-workflow`、`playwright-acceptance`、`matt-*` 被移除，成员另行安装的技能与指引中自写内容保持不变。
- **SOP-04 其他工作流中使用**：P01 在只装上游 MATT 与新版 team-knowledge 的会话中，代理按项目指引开工前运行 `brief`、完成后更新 `.tw` 并运行 `check`。
- **SOP-05 本仓知识**：P01 本仓 `tw check` 0 错误；第 4 节列出的每个条目都有处理记录。

两位真实团队成员在各自工作流中试用一周，记录 `brief` 是否找到了相关约束、放弃原因是否避免了重复错误，结果写入 `docs/validation.md`。

## 7 实施顺序

1. sop-board 完成配套方案 S1（标准迁入与推荐指引文字）并发行。
2. 本仓按第 3、4 节实施，发行 `1.0.0`。
3. sop-board 实施 S2（沉淀技能与关联记录），与本仓无依赖。

## 8 决定与待确认

用户 2026-10-22 已决定：本仓只保留知识库，不改名；MATT 由使用者自装；SOP 验收只归 sop-board；沉淀技能随 sop-board 发行，由本地 agent 在开发会话或看板调度中完成；`checks` 退出、运行交给 CI；沉淀产出留给开发者审核提交；sop-board S1 发布后，用户直接替换全局指引中引用本仓业务验收标准与 `start --grant` 的段落。

本仓自身的验收由独立代理执行第 6 节场景，结果写入 `docs/validation.md`；本仓不接入 sop-board（用户 2026-10-22 决定）。

待确认：无。
