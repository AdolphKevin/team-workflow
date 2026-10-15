# 本机状态的边界方案

> 状态：草案，待批准 · 日期：2026-10-15 · 方案负责人：Claude
>
> 前置：[合并重构方案](2026-10-14-unified-redesign.md) v4.2 的 L1、L2、T3 节，[以 Issue 和变更请求承载流程](2026-10-15-issue-and-change-request-flow.md) v3。
>
> - v1 → v2：撤回“状态移到 `git rev-parse --git-path tw`”。本机状态留在 `.tw/local/`，改为修正边界；原做法见第 7 节。
>
> 本方案不改入库知识、三道门和执行绑定的语义。

## 批准记录

| 时间 | 批准人 | 范围 | 依据 |
| --- | --- | --- | --- |

## 0 摘要

本机状态继续放在 `.tw/local/`，位置不变，只修正四条边界：

- 共享仓映射分两层：用户级默认值放在 `~/.config/tw/`，`.tw/local/repositories.json` 作为本检出目录的覆盖。新开 worktree 不必重新配置。
- 已提交的知识和文档不引用 `.tw/local/` 下的具体材料，由检查报告。
- 工具不管理的目录由 `tw audit` 列出；手工材料放在仓库外。
- 成员说明写清楚整目录删除和 `git clean -fdx` 的后果，清理统一用 `tw team cleanup`。

已有项目不需要迁移。是否把映射提升到用户级，由使用的代理按项目情况决定。

## 1 问题

| 数据 | 实际重要性 | 现在的问题 |
| --- | --- | --- |
| `cache/` | 可随时重建 | 无 |
| `repositories.json` | 本机配置，长期有效 | 每个 worktree 要各配一份 |
| 进行中任务的材料 | 交付前必不可少；离线任务的方案和批准只存在这里 | 整目录删除或 `git clean -fdx` 会丢失，成员说明没有写明 |
| 已交付任务的证据 | 复盘和核对时要用 | 已由 `team cleanup` 处理 |

另外两个现象：

- 被忽略的目录被当成杂物堆。本仓 33MiB 中大部分是 `team cleanup` 列为“不归工具管理”的手工试点目录。
- 已提交的 `docs/validation.md` 引用了 `.tw/local/batch*/` 和 `.tw/local/migration/`，别人检出后都是死链，违反“一个事实只有一个正文归属”（P5）。

清理逻辑的复杂度来自“交付前的材料必须保护”，与目录放在哪里无关，本方案不改动它。

## 2 设计

### 2.1 位置不变

`.tw/local/` 仍是唯一的项目内本机目录，按检出目录隔离，由嵌套的 `.tw/.gitignore` 忽略。项目中只有 `.tw/` 一个工具目录；`docs/` 等原文由项目自己拥有，`.tw/` 只登记引用。

### 2.2 共享仓映射分两层

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

- `tw check` 检查知识条目和已登记原文，发行检查另外扫描本仓 `docs/`：路径以 `.tw/local/` 开头、且第一级不是工具管理的名称（`tasks`、`batches`、`imports`、`validation-active`、`agents`、`cache`、`repositories.json`）时报错。
- 说明布局的写法（如 `.tw/local/tasks/<身份>/`）不受影响。
- `docs/validation.md` 中三处引用改为写明结论和关键数据，并注明原件只保留在执行者本机、未提交。

### 2.4 不归工具管理的目录

- `tw audit` 的本机用量报告增加“不归工具管理”的条目及大小，复用 `team cleanup` 的分类。
- 成员说明写明：试点和手工输出放在仓库外（如系统临时目录），不放进 `.tw/local/`。

### 2.5 删除后果写进成员说明

在 `docs/member-guide.md` 中写明：

- 各子目录的用途，以及整目录删除后的影响（进行中任务需重走，离线任务的方案和批准无法找回，已交付任务失去原始证据）。
- `git clean -fdx` 同样会删除 `.tw/local/`；需要清理构建产物时用 `git clean -fd`，或加 `-e .tw/local`。
- 清理用 `tw team cleanup` 预览后再应用。
- 任务只要对别人重要，就开 Issue。方案、批准、交接和交付结论以草稿形式发布到 Issue 或变更请求上，本机材料丢失后仍能找回；没有 Issue 的离线任务只能在本机恢复。

## 3 并行开发的影响

- `.tw/local/` 本来就按检出目录隔离，位置不变，隔离方式也不变。
- 新增的用户级映射文件工具只读，多个 worktree 同时运行时只读不写，不产生冲突。
- 入库文件的冲突（同一条知识、`config.json`、`docs/validation.md`）与现在相同，由 PR 评审合并解决。

## 4 决定

| 编号 | 问题 | 结论 | 状态 |
| --- | --- | --- | --- |
| D1 | 本机状态是否移出工作区 | 不移，留在 `.tw/local/`，也不新增目录 | 已确认（2026-10-15） |
| D2 | 共享仓映射几层 | 两层：用户级默认，检出目录覆盖 | 已确认（2026-10-15） |
| D3 | 旧项目怎么迁 | 不强制迁移；是否提升映射由使用的代理决定，工具不做自动迁移 | 已确认（2026-10-15） |
| D4 | 排期 | agent-py 推广之前完成 | 已确认（2026-10-15） |

## 5 验收标准

| 编号 | 内容 | 方式 |
| --- | --- | --- |
| A1 | 同一项目的两个 worktree：用户级把 `common` 映射到 X，worktree A 的 `.tw/local/repositories.json` 覆盖为 Y，B 没有覆盖。A 解析到 Y，B 解析到 X；A 的任务材料在 B 的 `status` 中不可见 | 自动测试，先写失败测试 |
| A2 | 查找顺序为命令行 > 检出目录 > 用户级，按别名逐项覆盖；用户级文件格式错误时报错并指出文件；都没有时提示两层文件的位置 | 自动测试 |
| A3 | 知识条目、已登记原文或本仓 `docs/` 引用 `.tw/local/batch0/x` 时报错；引用 `.tw/local/tasks/<身份>/` 时不报错 | 自动测试 |
| A4 | `tw audit` 列出不归工具管理的目录及大小 | 自动测试 |
| A5 | 没有用户级文件的已有项目，行为与现在完全相同 | 现有测试不改动即通过 |
| A6 | `python3 scripts/test.py`、`python3 scripts/check_release.py`、`tw check` 全部通过 | 实际运行 |
| A7 | 在一个声明了 `shared` 的已迁移项目中，只配置用户级映射，新建 worktree 后直接运行 `tw brief` 和 `tw team start`，共享仓解析正确 | 由未参与实现的代理或用户独立验收 |

## 6 影响范围

- 运行时：`project.py`、`team/common.py`（合并映射读取）、`check.py`、`audit.py`、`cli.py` 的参数说明。
- 发行检查：`scripts/check_release.py` 扫描 `docs/`。
- 文档：`docs/member-guide.md`、`docs/design.md`、`docs/validation.md`，team-knowledge 的 `writing.md` 与 `migration.md`（受篇幅预算约束）。
- 测试：新增 A1–A4，现有测试不改。
- 外部：无。
- 知识：批准后改写 `.tw/decisions/2026-10-14-one-repository-one-runtime.md`，补充用户级映射层，并把第 7 节的做法记入“放弃过的做法”。

## 7 放弃过的做法

- **本机状态移到 `git rev-parse --git-path tw`，记录中的路径改用 `local:` 前缀**（v1）
  - 好处只有两点：`git clean -fdx` 不会删除，编辑器和搜索看不到。
  - 放弃原因：工具数据从一处变成三处（`.tw/`、`.git/` 下的状态目录、用户级配置），更难理解和维护；worktree 的状态目录在工作区外，要为记录路径另设前缀、改写路径校验和约 10 处写死的路径；live-chat 的 worktree 依赖工具要跟着改；清理逻辑的复杂度并不因此降低。
  - 重新考虑的条件：实际出现因整目录删除或 `git clean -fdx` 丢失进行中任务的事故，且成员说明不足以避免。
