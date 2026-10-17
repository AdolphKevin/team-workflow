# 任务协作与交接

共享任务保存分节方案、具名批准与可追溯交接；工具职责见[工具做什么](contracts.md#工具做什么)，方案结构见[分节方案](designs.md)。每条平台记录保存实际发布评论账号 `recorded_by`，用于追溯记录人。

## 平台任务与方案

Issue 正文展示目标、非目标和验收项，隐藏的 `tw-record` HTML 注释保存任务数据。外层为 `data_version: 1`、`parent`、`task`；无总任务时 `parent` 为 `null`。内层采用[任务格式](contracts.md#配置与任务)，含：

- `design_id`：稳定方案编号。
- `section_ids`：负责的章节编号，至少含一个实施任务节。
- `acceptance_scope`：主需求 `requirement`、子任务 `task`；子任务内外层 `parent` 指向同一主需求。
- 可选 `paths`、`symbols`、`scopes`：知识读取范围。

任务的验收编号须与所选实施任务引用的验收节一致，结果和检查由方案展开。任务数据中的要求变化时更新方案和交接；记录有效性见[记录绑定](contracts.md#记录绑定)。

方案评论记录已提交原文的仓库、路径、提交号、摘要、发布者、要求指纹、前序引用和历史指纹。负责人确认后发布，每次修订编号加一并保留原评论。子任务引用主需求上的方案和批准；方案记录及批准发到方案所属任务，交接和进度发到各自任务。

批准人可由他人代为记录；`load` 的 `approval_records` 同时列批准人及 `recorded_by`。有会议或聊天依据时填写可选 `confirmation`。批准路径与章节选择见[内容与依赖](designs.md#内容与依赖)和[批准与变化](designs.md#批准与变化)。

## 两类交接

`handoff --kind design` 由方案负责人交给实施者；默认 `--kind implementation` 由实施负责人交代完成情况。输入示例：

```json
{
  "creator": "alice",
  "owner": "bob",
  "done": ["方案与验收条件已确认"],
  "verified": [],
  "remaining": ["按方案实现加法"],
  "questions": [],
  "next": "实现 T1，运行 A1 对应检查。",
  "included_progress": []
}
```

`creator` 承担对应方案或实施责任；`owner` 为下一位接手者，是当前 Issue 被指派人并在方案中具有责任。方案、实施、验收三项责任分别保留。`questions` 使用[问题记录](contracts.md#问题处置与交接)，自动带入方案及历次交接的已知问题；有负责人和下一步的剩余工作可交接。

工具补充方案版本、已批准章节、源码指纹及所有仓库的提交与内容版本。源码需可从共享仓取得；未共享工作区、本机独有外部文件、遗漏依赖、不可访问引用列为缺口。`verified` 引用执行或验收文件 `{path, sha256}`，核对时重读原始报告；源码与说明链接放 `references`，类别见[业务验收术语](business-acceptance.md#1-术语)。

外部仓库职责为 `build`（构建输入）、`modified`（本次修改）、`joint`（联合验证），均记录版本。修改和联合仓库需对应任务、被指派人和交付依据；联合工作另留接口原文、确认位置及联合验收负责人。显式依赖清单覆盖配置中的全部仓库。

`start` 返回当前要求、完整方案和历史、评审、各项责任、知识简报、交接和待确认进度；按实际改动与源码核对批准和范围。同次命令复用平台快照，再运行时获取最新进度和指派；缺少交接时列出接手材料缺口。

平台任务开工后，用 `--task <完整 Issue 地址>` 调用后续命令，按 `current.json` 补材料并重读平台；方案或批准更新时重新 `start`。`handoff`、`progress` 分别提供实际交接或进度输入。

## 进度、冲突与收尾

普通进度有唯一请求编号、记录作者与实际发布账号。相同编号和内容计一次，同编号内容不同形成冲突。`pending_progress` 列待确认项，负责人读过后把 `{id,digest}` 写入 `included_progress`，后续交接保留这些引用。

方案、批准和交接引用前序记录及完整历史。并行发布、前序被编辑、同版本竞争内容均报告缺口；脚本提供创建与编辑时间，已编辑结构化评论含最后一条均留缺口。读完冲突各方后保留全部评论，在新草稿输入增加：

```json
{
  "resolution": {
    "history_digest": "读取结果返回的当前历史指纹",
    "reason": "说明如何合并各方内容、采用哪些决定、保留哪些问题"
  }
}
```

历史与 `history_digest` 一致时建立明确起点；继续编辑此前评论时重新核对。方案、批准和交接分别整理各自冲突。

## 接入已有 Issue

缺少 `tw-record` 任务注释的 Issue 返回 `error_code: issue-not-adopted`。准备任务及已提交的共享方案后运行，格式见[方案格式](designs.md#markdown-原文格式)：

```bash
tw team issue-draft --root "$PROJECT" --task "$TASK" [--design "$DESIGN"] \
  [--with-task "$SIBLING_TASK"] [--reviewer <评审人>]
```

结果按 Issue 给新正文（保留原说明，替换或追加任务说明和注释）、方案任务的发布评论及变更请求原文、具名评审请求和发布顺序。共用父方案的子任务写 `parent` 与 `acceptance_scope: task`。按 `next_steps` 顺序发布；评审人确认后用 `approval-draft` 生成批准记录。

## 单人任务的收尾说明

交接有方案交接（`design`）、实施交接（`implementation`）和收尾说明（`close`）。仅一位平台负责人、无须另行负责的共享仓库且无跨服务风险时，可用收尾说明；实施可由本人或其指挥的代理完成。其他情况发布实施交接，缺负责人时先指派。

最终 `verify` 在 `close_note` 给摘要与记录：业务验收文件指纹、知识处置及已有关闭授权。`creator` 是实施负责人，`owner` 是唯一平台负责人，可读说明列出两者；`remaining` 为空，`verified` 引用业务验收。收尾前[确认全部进度](#进度冲突与收尾)，并按[问题记录](contracts.md#问题处置与交接)完成相关处置。发布后 `start` 返回 `closed: true`，再次 `verify` 使用已发布记录。

方案、批准、交接和进度的读取结果与草稿含 `delivery: not-evaluated`，接手结果为 `closable: false`；最终交付核对执行、代码评审、知识处置、接续条件，并在结束前重读平台。
