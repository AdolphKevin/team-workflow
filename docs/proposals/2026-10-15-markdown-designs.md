> 历史文档：保留当时的方案或验证记录；现行能力与使用方式见 [README](../../README.md)。

# 方案以 Markdown 原文为准（v1.1）

> 状态：已批准 · 日期：2026-10-15 · 方案负责人：Claude
>
> 前置：[合并重构方案](2026-10-14-unified-redesign.md) v4.2、[流程简化方案](2026-10-15-process-simplification.md)、[以 Issue 和变更请求承载流程](2026-10-15-issue-and-change-request-flow.md) v3。
>
> v1 → v1.1：评审人不读 JSON。发布到平台的方案、批准、评审都以 Markdown 呈现，工具数据放进 HTML 注释（渲染后不可见）；PR 描述就是方案原文。修订第 3 节，新增第 3.1 节。
>
> 本方案只改方案的书写与存放形式，不改分节指纹、局部重审、批准绑定、验收字段和三道门的语义。

## 批准记录

| 时间 | 批准人 | 范围 | 依据 |
| --- | --- | --- | --- |
| 2026-10-15 | AdolphKevin | 本方案全文；D1–D5 均按建议执行 | 会话中答复“D1-D5 按你的建议执行” |
| 2026-10-15 | AdolphKevin | v1.1：PR 采用方案原文 Markdown，平台上不出现给人读的 JSON | 会话中要求“PR 也要采用真实的 markdown 方案，而不是JSON，因为方案评审人，不会看 JSON” |

## 0 摘要

- 方案只有一份正文：仓库里的 Markdown 文件，例如 `docs/proposals/<日期>-<slug>.md`。工具解析这份原文，不再接受 JSON 方案。
- 章节用标题标识，标题行后的一行 HTML 注释写章节编号、类型和依赖。渲染后看不到，源码和 diff 里可见。
- 验收项、任务、影响范围用固定的标签行和表格书写，现有每个字段都有对应写法。
- 平台上的方案记录只放文件路径、提交号和内容摘要；工具从本地 git 读取该提交的原文并解析。
- 指纹、局部重审、批准和交付核对，继续在解析出的同一内部结构上进行，语义不变。

## 1 问题（来自 Issue #5 的真实开发）

Issue #5 按团队流程走到 `start`，方案记录是 15.7KB 的 JSON，比 8.3KB 的方案原文还长：

1. **两份正文**：JSON 是 Claude 照着 Markdown 原文手工转写的，违反“源文档只保存一份正文”。改方案要改两处，容易不一致。
2. **批准的不是读到的**：评审人读的是 Markdown，批准记录绑定的是 JSON 的分节指纹。转写有出入时，工具核对的不是评审人认可的内容。
3. **没人读**：PR 描述被 JSON 占满，评审人实际只看原文。

T7 已把评审改为 Markdown（工具生成、人填写、工具校验），方案还停在 JSON。本方案把方案也改到同一种方式。

## 2 格式

### 2.1 文件头

沿用知识条目的文件头写法：`---` 之间每行一个 `字段: JSON值`。

```markdown
---
design: "D-local-state"
task: "https://github.com/AdolphKevin/team-workflow/issues/5"
revision: 1
assessment: {"complexity": "medium", "risks": ["public-contract"], "effort": "约 1 代理日", "drivers": ["……"], "uncertainties": [], "required_skills": ["Python"]}
roles: {"design_owner": "Claude", "implementation_owner": "Codex", "acceptance_owner": "AdolphKevin"}
---
```

`revision` 由作者在每次发布新版本时加一，工具核对它比上一版正好大一。

### 2.2 章节

章节是带标记的标题。标记写在标题的下一行：

```markdown
## 2.2 共享仓映射分两层
<!-- tw-section id=mapping type=interface depends=scope-global -->
正文……
```

- `type` 取现有的 `global-scope`、`scope`、`interface`、`data`、`acceptance`、`task`；`depends` 可省略或写多个，逗号分隔。
- 章节正文从标记下一行开始，到下一个同级或更高级的带标记标题为止。中间未带标记的子标题属于该章节正文。
- 第一个带标记的标题之前的内容，如标题、状态行、批准记录表，不属于任何章节，不参与指纹。批准记录表在批准后更新，因此不会让批准失效。
- 必须有且只有一个 `scope-global`。

### 2.3 有结构的章节

**全局范围**写需求级验收和影响范围：

```markdown
- 需求级验收：A1、A7

| 仓库 | 入口 | 操作 | 产生方 | 使用方 | 提交负责方 | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| self | tw brief、tw team start 的共享仓解析 | 读取共享仓映射 | 映射文件 | tw 运行时 | team-workflow | A1、A2 |
```

**验收项**一节一个，正文之后是标签行：

```markdown
### A1 两个 worktree 分别解析共享仓
<!-- tw-section id=A1 type=acceptance -->
同一项目的两个 worktree……
- 角色：在多个 worktree 并行开发的成员
- 初始状态：用户级映射已把 common 指向 X；worktree A 有本机覆盖 Y，B 没有
- 步骤：在 A 运行 tw brief 与 tw team start；在 B 运行 tw brief 与 tw team status
- 预期：A 解析到 Y，B 解析到 X；B 的 status 看不到 A 的任务材料
- 反例：B 误用 A 的覆盖；A 的任务材料出现在 B
- 依据：docs/proposals/2026-10-15-local-state-location.md（v2，AdolphKevin 确认）
- 检查：unit
- 验证：自动；层级 journey；入口 tw brief、tw team start、tw team status；环境 临时 git 仓库与两个 worktree；替身 无；隔离 isolated
```

**任务**一节一个：

```markdown
### T1 两层共享仓映射
<!-- tw-section id=T1 type=task depends=mapping -->
实现用户级映射与查找顺序……
- 验收：A1、A2、A5、A7
- 范围：skills/team-knowledge/scripts/tw_runtime/project.py、tests
- 前置任务：无
```

**已知问题**放在一个带 `<!-- tw-issues -->` 标记的标题下，用现有字段的表格书写；没有已知问题时省略。

标签名、分隔符和取值与现有 JSON 字段一一对应，完整对照表写进 `references/designs.md`。缺标签、取值不合法、引用不存在的章节，都按现在的规则拒绝，并指出行号。

## 3 存放与记录

- **本地任务**：`start --design <Markdown 路径>`，其他接受 `--design` 的命令同样只接受 Markdown。
- **平台任务**：方案文件随变更请求分支提交。`design-draft` 生成的方案记录只含：
  `{"data_version":1,"kind":"design-record","task", "creator", "requirements", "requirements_signature", "history_digest", "previous", "design": {"id", "revision", "path", "commit", "sha256"}}`。
  工具用 `git show <commit>:<path>` 读取原文，核对 sha256 后解析。本地没有该提交时给出缺口，要求先 fetch，不访问平台。
- **PR 描述**写人看的摘要、方案文件链接，加上这一小段记录。
- 批准信封、`--revision`、评审 Markdown、交付核对不变；它们引用的章节编号与指纹来自解析结果。

### 3.1 平台上只给人看 Markdown（v1.1）

- **PR 描述就是方案原文**：`design-draft` 输出的 PR 描述是方案文件在发布提交中的全文。描述只用于展示，可以更新；工具发现描述与最新已发布版本的原文不一致时给出提示，不据此判定。
- **发布记录**：每发布一版，在 PR 上追加一条简短评论，例如“方案第 1 版已发布：`docs/proposals/…md`，提交 `abc1234`”。路径、提交号、摘要等数据放在评论内的 HTML 注释 `<!-- tw-record {...} -->` 中。记录只追加不修改，局部重审依赖的历史不变。
- **批准**：批准评论是一句可读的说明，例如“AdolphKevin 批准方案第 1 版：全部章节。依据：……”，并列出章节标题；批准信封放在 HTML 注释中。
- **代码评审**：评审 Markdown 的绑定区从可见的 JSON 代码块改为 HTML 注释，评审人填写的内容不变。
- Issue 正文中的任务块、Issue 上的方案评论、交接与进度记录同样适用：可读正文加隐藏数据。任务块的可读正文列出目标、非目标和验收项。工具解析时只认 `tw-record` 注释，可见文字不参与判定。

## 4 删除与不变

- 删除：JSON 方案输入、`templates/design.json`，以及 PR 和 Issue 中嵌入整份方案的方案记录。按本仓教训“只接受当前格式”，旧格式直接拒绝并提示改写，不并存。
- 新增：`templates/design.md`；`designs.load()` 解析器；`designs.render()` 把内部结构写成 Markdown，供 `issue-draft` 起草和测试使用。
- 不变：内部结构、指纹算法、局部重审、批准与评审规则、业务验收字段的要求。验收字段是否过重是另一个问题，本方案不动。

## 5 验收

| 编号 | 内容 | 方式 |
| --- | --- | --- |
| M1 | 任意合法的内部结构，`render` 后再 `load`，与原结构相同；指纹不变 | 自动测试 |
| M2 | 只改第一个带标记标题之前的内容（如批准记录表），所有章节指纹不变 | 自动测试 |
| M3 | 改一节正文，只有这一节及依赖它的章节需要重新批准 | 自动测试 |
| M4 | 缺标签、错误类型、重复编号、引用不存在的章节、两个 `scope-global`、JSON 方案输入，分别拒绝并指出位置 | 自动测试 |
| M5 | 平台方案记录引用的提交在本地不存在、摘要不符时拒绝；记录不再包含整份方案 | 自动测试 |
| M6 | 用 `docs/proposals/2026-10-15-local-state-location.md` 本身作为方案，补上标记后，在 PR #6 重新发布记录与批准，`tw team start` 返回 `implementation_ready: true` | 真实入口 |
| M8 | 发布到平台的方案、批准、评审、交接、进度草稿中没有可见的 JSON 代码块；数据在 `tw-record` 注释中，往返解析一致 | 自动测试 |
| M7 | 全量测试、发布检查、`tw check` 通过 | 实际运行 |

## 6 工作量

约 1–1.5 代理日：解析与渲染 0.5，命令与记录改造 0.5，测试夹具从 JSON 改为 Markdown 0.25，文档 0.25。由 Codex 实现，Claude 审核；M6 由 Claude 在真实仓库执行。

## 7 待确认的决定

- **D1** 方案只认 Markdown 原文，删除 JSON 方案输入，不并存。
- **D2** 章节用“标题 + 下一行 HTML 注释标记”标识；第一个标记之前的内容不参与指纹。
- **D3** 验收项、任务、影响范围用标签行和表格书写，字段与现有结构一一对应。
- **D4** 平台方案记录只放路径、提交号和摘要，原文从本地 git 读取。
- **D5** 以 Issue #5 的方案原文作为首个真实用例，完成后恢复 Issue #5 的实施。
