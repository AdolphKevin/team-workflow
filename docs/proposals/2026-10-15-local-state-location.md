---
design: "D-local-state"
task: "https://github.com/AdolphKevin/team-workflow/issues/5"
revision: 1
assessment: {"complexity":"medium","risks":["public-contract"],"effort":"约 1 代理日","drivers":["改动 tw 读取共享仓映射的查找顺序，影响所有项目","新增已提交内容的引用检查"],"uncertainties":[],"required_skills":["Python","git worktree"]}
roles: {"design_owner":"Claude","implementation_owner":"Codex","acceptance_owner":"AdolphKevin"}
---

# 本机状态的边界方案

> 状态：已批准 · 日期：2026-10-15 · 方案负责人：Claude
>
> 前置：[合并重构方案](2026-10-14-unified-redesign.md) v4.2 的 L1、L2、T3 节，[以 Issue 和变更请求承载流程](2026-10-15-issue-and-change-request-flow.md) v3。
>
> - v1 → v2：撤回“状态移到 `git rev-parse --git-path tw`”。本机状态留在 `.tw/local/`，改为修正边界；原做法见第 7 节。
> - 方案第 2 版（实施中）：第 1 节与 A3 中的示例路径改为不直接写出完整的本机路径，避免被本方案新增的引用检查误报；含义不变。
> - 验证写法改为新格式（[验收绑定简化](2026-10-15-acceptance-binding-and-flow-fixes.md)）：A1–A7 的验证行只写方式和允许的替身，覆盖范围以检查登记为准；方案历史按对账从第 1 版重新开始，业务内容不变。
>
> 本方案不改入库知识、三道门和执行绑定的语义。

## 批准记录

| 时间 | 批准人 | 范围 | 依据 |
| --- | --- | --- | --- |
| 2026-10-15 | AdolphKevin | 本方案全文 | 会话中批准方案，并授权 Claude 在 PR 上代为发布批准 |
| 2026-10-16 | AdolphKevin | 新验证写法重新发布的第 1 版 | 批准验收绑定简化方案（D8：重新开始方案历史、全部章节重新批准） |

## 0 摘要
<!-- tw-section id=scope-global type=global-scope -->

本机状态继续放在 `.tw/local/`，位置不变，只修正四条边界：

- 共享仓映射分两层：用户级默认值放在 `~/.config/tw/`，`.tw/local/repositories.json` 作为本检出目录的覆盖。新开 worktree 不必重新配置。
- 已提交的知识和文档不引用 `.tw/local/` 下的具体材料，由检查报告。
- 工具不管理的目录由 `tw audit` 列出；手工材料放在仓库外。
- 成员说明写清楚整目录删除和 `git clean -fdx` 的后果，清理统一用 `tw team cleanup`。

已有项目不需要迁移。是否把映射提升到用户级，由使用的代理按项目情况决定。

- 需求级验收：A1、A7

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | tw brief、tw team start/status 的共享仓解析 | 读取共享仓映射 | 成员或代理编辑的映射文件 | tw 运行时 | team-workflow | A1、A2、A5、A7 |
| self | tw check、发行检查、tw audit | 检查已提交内容的本机引用；报告本机目录用量 | 知识条目与 docs/ | 评审人与成员 | team-workflow | A3、A4、A6 |

## 1 问题
<!-- tw-section id=problem type=scope depends=scope-global -->

| 数据 | 实际重要性 | 现在的问题 |
| --- | --- | --- |
| `cache/` | 可随时重建 | 无 |
| `repositories.json` | 本机配置，长期有效 | 每个 worktree 要各配一份 |
| 进行中任务的材料 | 交付前必不可少；离线任务的方案和批准只存在这里 | 整目录删除或 `git clean -fdx` 会丢失，成员说明没有写明 |
| 已交付任务的证据 | 复盘和核对时要用 | 已由 `team cleanup` 处理 |

另外两个现象：

- 被忽略的目录被当成杂物堆。本仓 33MiB 中大部分是 `team cleanup` 列为“不归工具管理”的手工试点目录。
- 已提交的 `docs/validation.md` 引用了 `.tw/local/` 下的旧批次目录（`batch*`）和迁移目录（`migration`），别人检出后都是死链，违反“一个事实只有一个正文归属”（P5）。

清理逻辑的复杂度来自“交付前的材料必须保护”，与目录放在哪里无关，本方案不改动它。

## 2 设计
<!-- tw-section id=design type=scope depends=scope-global -->

### 2.1 位置不变

`.tw/local/` 仍是唯一的项目内本机目录，按检出目录隔离，由嵌套的 `.tw/.gitignore` 忽略。项目中只有 `.tw/` 一个工具目录；`docs/` 等原文由项目自己拥有，`.tw/` 只登记引用。

### 2.2 共享仓映射分两层
<!-- tw-section id=mapping type=interface depends=scope-global -->

- 用户级文件：`${XDG_CONFIG_HOME:-~/.config}/tw/repositories.json`，按 `config.json` 的 `project.id` 分组，每组的内容与现在的 `.tw/local/repositories.json` 相同：

  ```json
  {"projects": {"github.com/acme/core": {"repositories": {"common": "~/src/common"}}}}
  ```

- 查找顺序：命令行 `--repository` > `.tw/local/repositories.json` > 用户级。按别名逐项覆盖，不整份替换。
- 两个文件都由人或代理编辑，工具只读不写，因此多个 worktree 并行时不存在写入冲突。
- 现在有两处读取映射（`project.py` 的 `mapping` 与 `team/common.py` 的 `location_settings`），合并为一个函数，各自的键含义不变。
- 缺少映射时仍只提示，不猜测、不自动克隆；提示中同时给出两层文件的位置。
- live-chat 的 worktree 依赖工具写的是检出目录内的文件，不受影响。

### 2.3 已提交内容不引用本机材料
<!-- tw-section id=references type=scope depends=scope-global -->

- `tw check` 检查知识条目和已登记原文，发行检查另外扫描本仓 `docs/`：路径以 `.tw/local/` 开头、且第一级不是工具管理的名称（`tasks`、`batches`、`imports`、`validation-active`、`agents`、`cache`、`repositories.json`）时报错。
- 说明布局的写法（如 `.tw/local/tasks/<身份>/`）不受影响。
- `docs/validation.md` 中三处引用改为写明结论和关键数据，并注明原件只保留在执行者本机、未提交。

### 2.4 不归工具管理的目录
<!-- tw-section id=audit type=scope depends=scope-global -->

- `tw audit` 的本机用量报告增加“不归工具管理”的条目及大小，复用 `team cleanup` 的分类。
- 成员说明写明：试点和手工输出放在仓库外（如系统临时目录），不放进 `.tw/local/`。

### 2.5 删除后果写进成员说明
<!-- tw-section id=guide type=scope depends=scope-global -->

在 `docs/member-guide.md` 中写明：

- 各子目录的用途，以及整目录删除后的影响（进行中任务需重走，离线任务的方案和批准无法找回，已交付任务失去原始证据）。
- `git clean -fdx` 同样会删除 `.tw/local/`；需要清理构建产物时用 `git clean -fd`，或加 `-e .tw/local`。
- 清理用 `tw team cleanup` 预览后再应用。
- 任务只要对别人重要，就开 Issue。方案、批准、交接和交付结论以草稿形式发布到 Issue 或变更请求上，本机材料丢失后仍能找回；没有 Issue 的离线任务只能在本机恢复。

## 3 并行开发的影响
<!-- tw-section id=parallel type=scope depends=scope-global -->

- `.tw/local/` 本来就按检出目录隔离，位置不变，隔离方式也不变。
- 新增的用户级映射文件工具只读，多个 worktree 同时运行时只读不写，不产生冲突。
- 入库文件的冲突（同一条知识、`config.json`、`docs/validation.md`）与现在相同，由 PR 评审合并解决。

## 4 决定
<!-- tw-section id=decisions type=scope depends=scope-global -->

| 编号 | 问题 | 结论 | 状态 |
| --- | --- | --- | --- |
| D1 | 本机状态是否移出工作区 | 不移，留在 `.tw/local/`，也不新增目录 | 已确认（2026-10-15） |
| D2 | 共享仓映射几层 | 两层：用户级默认，检出目录覆盖 | 已确认（2026-10-15） |
| D3 | 旧项目怎么迁 | 不强制迁移；是否提升映射由使用的代理决定，工具不做自动迁移 | 已确认（2026-10-15） |
| D4 | 排期 | agent-py 推广之前完成 | 已确认（2026-10-15） |

## 5 验收标准
<!-- tw-section id=verification type=scope depends=scope-global -->

每项验收都写明角色、步骤、预期与反例；A1 与 A7 覆盖完整业务路径，A7 由未参与实现的人执行。

### A1 两个 worktree 分别解析共享仓
<!-- tw-section id=A1 type=acceptance -->
同一项目的两个 worktree：用户级把 common 映射到 X，worktree A 的 .tw/local/repositories.json 覆盖为 Y，B 没有覆盖；A 解析到 Y，B 解析到 X；A 的任务材料在 B 的 status 中不可见。

- 角色：在多个 worktree 并行开发的成员
- 初始状态：用户级映射文件已把 common 指向 X；worktree A 有本机覆盖 Y，worktree B 没有
- 步骤：在 A 运行 tw brief 与 tw team start；在 B 运行 tw brief 与 tw team status
- 预期：A 解析到 Y，B 解析到 X；B 的 status 看不到 A 的任务材料
- 反例：B 误用 A 的覆盖；A 的任务材料出现在 B
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

### A2 映射查找顺序与错误提示
<!-- tw-section id=A2 type=acceptance -->
查找顺序为命令行 > 检出目录 > 用户级，按别名逐项覆盖；用户级文件格式错误时报错并指出文件；都没有时提示两层文件的位置。

- 角色：配置共享仓的成员
- 初始状态：三层映射分别提供不同别名与重叠别名
- 步骤：运行带 --repository 的命令；删掉检出目录覆盖再运行；把用户级文件写坏再运行
- 预期：同名别名按优先级取值、其余别名逐项合并；坏文件报错并给出路径；缺失时提示两个位置
- 反例：整份替换而非逐项覆盖；坏文件被静默忽略
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

### A3 已提交内容不引用本机材料
<!-- tw-section id=A3 type=acceptance -->
知识条目、已登记原文或本仓 docs/ 引用 `.tw/local/` 下的 `batch0/x` 时报错；引用 .tw/local/tasks/<身份>/ 这类布局说明时不报错。

- 角色：写知识或文档的成员
- 初始状态：条目与 docs 中分别出现具体本机材料引用和布局说明
- 步骤：运行 tw check；运行发行检查
- 预期：具体材料引用报错并指出文件；布局说明不报错
- 反例：布局说明被误报；docs/ 中的死链未被发现
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit、release
- 验证：自动；替身 项目平台脚本夹具

### A4 列出不归工具管理的本机目录
<!-- tw-section id=A4 type=acceptance -->
tw audit 列出 .tw/local/ 下不归工具管理的目录及大小。

- 角色：清理本机空间的成员
- 初始状态：.tw/local/ 下有工具目录和手工目录
- 步骤：运行 tw audit
- 预期：手工目录及大小单独列出，工具目录不在其中
- 反例：工具目录被列为不归管理
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

### A5 没有用户级文件时行为不变
<!-- tw-section id=A5 type=acceptance -->
没有用户级文件的已有项目，行为与现在完全相同；现有测试不改动即通过。

- 角色：未配置用户级文件的已有项目
- 初始状态：只有 .tw/local/repositories.json
- 步骤：运行全量测试
- 预期：现有测试不改动全部通过
- 反例：现有断言需要修改才能通过
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit
- 验证：自动；替身 项目平台脚本夹具

### A6 全量检查通过
<!-- tw-section id=A6 type=acceptance -->
python3 scripts/test.py、python3 scripts/check_release.py、tw check 全部通过。

- 角色：交付者
- 初始状态：实现完成
- 步骤：运行全量测试、发行检查与 tw check
- 预期：三项全部通过
- 反例：任何一项失败
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：unit、release
- 验证：自动；替身 项目平台脚本夹具

### A7 新 worktree 只配用户级映射即可使用共享仓
<!-- tw-section id=A7 type=acceptance -->
在一个声明了 shared 的已迁移项目中，只配置用户级映射，新建 worktree 后直接运行 tw brief 和 tw team start，共享仓解析正确。

- 角色：未参与实现的验收者
- 初始状态：已迁移项目（声明了 shared），用户级映射已配置，新 worktree 中没有 .tw/local/repositories.json
- 步骤：新建 worktree；运行 tw brief 与 tw team start；核对共享仓的检出目录与 HEAD
- 预期：共享仓解析到用户级映射的目录，无需在 worktree 中再配置
- 反例：新 worktree 提示缺少映射；解析到错误目录
- 依据：位置 docs/proposals/2026-10-15-local-state-location.md；版本 v2；确认人 AdolphKevin
- 检查：无
- 验证：人工

## 6 影响范围
<!-- tw-section id=impact type=scope depends=scope-global -->

- 运行时：`project.py`、`team/common.py`（合并映射读取）、`check.py`、`audit.py`、`cli.py` 的参数说明。
- 发行检查：`scripts/check_release.py` 扫描 `docs/`。
- 文档：`docs/member-guide.md`、`docs/design.md`、`docs/validation.md`，team-knowledge 的 `writing.md` 与 `migration.md`（受篇幅预算约束）。
- 测试：新增 A1–A4，现有测试不改。
- 外部：无。
- 知识：批准后改写 `.tw/decisions/2026-10-14-one-repository-one-runtime.md`，补充用户级映射层，并把第 7 节的做法记入“放弃过的做法”。

### T1 两层共享仓映射
<!-- tw-section id=T1 type=task depends=mapping -->

实现用户级映射与查找顺序，合并两处读取，补 A1、A2 测试并保持 A5。

- 验收：A1、A2、A5、A7
- 范围：skills/team-knowledge/scripts/tw_runtime/project.py、skills/team-knowledge/scripts/tw_runtime/team/common.py、skills/team-knowledge/scripts/tw_runtime/cli.py、tests
- 前置任务：无

### T2 已提交内容的本机引用检查
<!-- tw-section id=T2 type=task depends=references -->

tw check 与发行检查报告具体本机材料引用；改写 docs/validation.md 中引用本机材料的地方。

- 验收：A3、A6
- 范围：skills/team-knowledge/scripts/tw_runtime/check.py、scripts/check_release.py、docs/validation.md、tests
- 前置任务：无

### T3 audit 用量、成员说明与知识
<!-- tw-section id=T3 type=task depends=audit,guide -->

tw audit 列出不归工具管理的目录；更新成员说明、设计说明与相关参考，改写一库一运行时的决策，登记本方案与变更说明。

- 验收：A4、A6
- 范围：skills/team-knowledge/scripts/tw_runtime/audit.py、docs/member-guide.md、docs/design.md、docs/proposals/2026-10-15-local-state-location.md、skills/team-knowledge/references、.tw/decisions、CHANGELOG.md、skills/team-knowledge/MANIFEST.json、skills/team-workflow/MANIFEST.json、tests
- 前置任务：无

## 7 放弃过的做法
<!-- tw-section id=abandoned type=scope depends=scope-global -->

- **本机状态移到 `git rev-parse --git-path tw`，记录中的路径改用 `local:` 前缀**（v1）
  - 好处只有两点：`git clean -fdx` 不会删除，编辑器和搜索看不到。
  - 放弃原因：工具数据从一处变成三处（`.tw/`、`.git/` 下的状态目录、用户级配置），更难理解和维护；worktree 的状态目录在工作区外，要为记录路径另设前缀、改写路径校验和约 10 处写死的路径；live-chat 的 worktree 依赖工具要跟着改；清理逻辑的复杂度并不因此降低。
  - 重新考虑的条件：实际出现因整目录删除或 `git clean -fdx` 丢失进行中任务的事故，且成员说明不足以避免。
