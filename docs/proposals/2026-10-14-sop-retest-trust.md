> 历史文档：保留当时的方案或验证记录；现行能力与使用方式见 [README](../../README.md)。

# SOP 场景的 Agent 验证与人工复测（草案 v1）

> 状态：已被取代 · 日期：2026-10-14 · 方案负责人：Claude · 评审人：AdolphKevin
>
> 由[场景化黑盒验收与指令文本的肯定式改写](2026-10-16-scenario-acceptance-and-positive-text.md)取代：场景格式、用例导入、配对与统计并入该方案第 2 节；复测看板由项目代理按指南搭建（该方案 D6）。
>
> 前置：[team-workflow 与 CS 合并重构方案](2026-10-14-unified-redesign.md)阶段 2 合入（S0 批次 0 除外，可以现在开始）。本提案使用其中的 `.tw/` 布局、稳定任务身份（T1）和 `tw team` 命令面（C），不扩大已批准的重构范围。

## 0 摘要

- **要解决的问题**：开发侧由 Agent 按 SOP 完成验证，测试同事却看不到 Agent 验过什么、结论是什么，只能全部重测；双方的场景互不对照，漏掉的边界场景要到测出问题时才暴露；Agent 的验收结论有多可信，也没有任何数据。
- **做法**：
  1. 由 tw 定义 SOP 场景格式并做校验，强制每个阶段同时包含正向和反向场景。
  2. Agent 验证后推送结果。测试同事在网页上复测 Agent 判为通过的场景，判为不通过时必须填写 Jira 链接。
  3. 按需求批次统计“Agent 判通过、人工复测仍通过”的比例。只有多个需求连续保持 100%，才逐步建立信任。
- **形态**：
  - 格式与校验进入 tw 运行时：`tw team sop …`；
  - 复测看板作为子命令 `tw board serve`，仍然只用标准库加 SQLite，先在本地运行，可以直接用 Python 启动，也可以用 Docker 启动；
  - 测试同事只用浏览器，不需要安装 tw。

## 1 与现有标准的对应

本提案只落地[业务验收与质量改进标准](https://github.com/AdolphKevin/team-workflow/blob/8be02e4/skills/team-workflow/references/business-acceptance.md)中已有的要求，不新增流程义务：

| 本提案 | 标准中的依据 |
| --- | --- |
| SOP 场景格式：正向和反向各自成条，带依据和副作用 | §4 第一步，`sources` 契约 |
| Agent 验证并推送结果 | §4 第二步：独立验收者经真实入口验证并留证 |
| 测试同事复测并标记 | §1 独立验收者；§3.4 实现者不得自行验收 |
| 不通过时填写 Jira 链接 | §7 缺陷关联 |
| 复测通过率、误判明细 | §8 每周复盘中的“验收后新增缺陷” |

## 2 范围

**目标**

1. SOP 场景有统一的格式，所有项目一致，并由工具校验正反向场景是否齐全。
2. 与测试同事的用例做对比，发现双方各自遗漏的边界场景和预期冲突。
3. Agent 结果和人工复测是两条独立的轨道，人工标记永远不会被 Agent 改写。
4. 按批次和跨批次统计复测通过率，以及误判明细。

**非目标**

- 不对接 Jira、GitHub 的接口（Jira 只保存链接），不做登录鉴权，不在工具内调用大模型。
- 信任门槛暂定为复测通过率 100%，看板只显示是否达到，不做“达到门槛后自动减少复测”的规则。门槛和放手方式以后再与测试同事商定（D3）。
- 不改变测试同事现有的用例生成流程。
- 不修改方案（design）验收节，验收节不引用 SOP 场景编号（D2）。

## 3 数据格式

### 3.1 SOP 场景文件（入库，属于业务原文）

- 存放在业务仓库，推荐路径为 `docs/sop/<批次>.yaml`，按 K5 登记为原文。
- 字段沿用 tw 现有的验收术语（`actor`、`initial_state`、`steps`、`expected`、`sources`），不另起名称。

```yaml
metadata:
  requirement: "<需求名称>"
  batch: "<批次编号，全局唯一>"
  version: 3
  task: "<任务身份，见重构方案 T1>"
  sources:
    - {ref: "<PRD 或 SOP 原文位置>", version: "<版本>", confirmed_by: "<确认人>"}

sops:
  - id: SOP-02
    title: 建团队与承接
    actor: "Owner / Admin"
    entry: "/setting/teams"
    must: ["切换分配策略只影响之后入队的会话"]
    # negative_exempt: "<没有有意义的反向场景的理由>"
    scenarios:
      - id: SOP-02-P01
        polarity: positive
        title: 新建手动认领团队
        actor: Owner
        priority: P0
        refs: ["ASSIGN-01"]
        verify: api+ui            # api | ui | cli | 用 + 组合，如 api+ui
        layer: local              # 执行环境名称，由项目自定
        initial_state: ["有 Agent A1、A2 和 Supervisor S"]
        steps: ["新建 Support 团队并保存"]
        expected: ["保存成功", "页面上没有品牌范围字段"]
        forbidden_effects: []
        evidence_hints: ["teams、team_members 行"]
        tags: ["section:团队 · 新建"]
      - id: SOP-02-N01
        polarity: negative
        negative_type: permission
        title: Admin 读取看不到的团队
        actor: "Admin（只有品牌 A）"
        priority: P1
        refs: ["#138"]
        verify: api
        layer: local
        initial_state: ["团队 T2 只被品牌 B 引用"]
        steps: ["调用 GET /api/v2/teams/{T2}"]
        expected: ["返回 NotFound"]
        forbidden_effects: ["响应中不出现 T2 的名称或成员"]
```

**`tw team sop check <文件>` 的校验项**：

- 必填字段齐全，场景编号在批次内唯一。
- `metadata.sources` 不能为空。
- 反向场景必须填写 `negative_type`，取值来自标准 §4 第一步的负向类型：`empty-input`、`over-length`、`not-found`、`permission`、`cross-tenant`、`duplicate`、`concurrency`、`disconnect`、`timeout`、`archived`、`other`。
- 每个阶段至少要有 1 个正向和 1 个反向场景，否则报错，并列出缺少的阶段。
- 确实没有反向场景的阶段，写明 `negative_exempt` 的理由后放行；看板上会持续显示这条豁免。

工具只核对结构是否齐全，不判断场景在业务上是否充分，这部分由评审负责（重构方案 P3）。

### 3.2 测试同事的用例（导入，不入 tw 管理的仓库）

原样导入测试同事现有的 YAML（`metadata` 加 `test_cases[]`）：

- 导入时把 `preconditions` 映射为 `initial_state`，把 `expected_results` 映射为 `expected`；
- 从 tags 中提取需求编号（形如 `ABC-01`）和 `section:`，用于分组。

另外兼容他们离线 HTML 导出的执行 JSON：`{prefix, title, _updatedAt, cases: {<编号>: {status, actual, testedAt, images[]}}}`。

### 3.3 Agent 结果

由 `tw team sop push <批次> <结果文件>` 推送，格式为 JSON Lines：

```json
{"scenario": "SOP-02-N01", "status": "pass", "executor": "codex:task-abc", "task": "<任务身份>", "commit": "1a2b3c4", "env": "local", "executed_at": "2026-10-13T08:00:00Z", "evidence": ["<证据位置或摘要>"], "note": ""}
```

- `status` 取值为 `pass`、`fail`、`blocked`、`skip`、`partial`，其中 `partial` 表示接口已通过、界面部分等待人工检查。
- 证据原件仍保存在本机的 `.tw/local/tasks/<身份>/`，看板只保存位置和摘要，与重构方案 L2 的体积上限一致。

### 3.4 配对文件（由 Agent 离线生成）

```json
{"batch": "<批次>",
 "pairs": [{"sop": "SOP-02-N01", "case": "TC_TEAM_014", "relation": "equivalent", "note": ""}],
 "sop_only": [{"sop": "SOP-02-N03", "note": "测试用例未覆盖跨品牌团队的编辑"}],
 "case_only": [{"case": "TC_TEAM_031", "note": "SOP 未覆盖成员上限为 50 的边界"}]}
```

- `relation` 取值：`equivalent`（等价）、`partial`（部分覆盖）、`conflict`（预期冲突）。
- 技能附带一份配对提示词：先按需求编号和 `section` 缩小范围，再做语义配对。编号只作为线索，因为两边的编号可能对不齐。
- 导入时校验：引用的编号必须存在；没有出现在任何一类中的场景或用例，列为“未处理”。

## 4 执行集合、判定与统计

**执行集合**是 SOP 场景。Agent 验证 SOP 场景，测试同事也复测 SOP 场景，两边测的是同一个对象。测试同事的用例只用于对比：只有测试侧才有的场景，经开发确认后补进 SOP 文件，作为新版本重新导入。

**人工标记**：
- `status` 取值为 `pass`、`fail`、`blocked`、`skip`。
- 判 `fail` 时必须填写 Jira 链接，链接要以服务配置的 `JIRA_BASE_URL` 开头。
- 每条标记记录标记人、时间、环境、实际结果和截图（可选）。

**队列**：
- 复测队列：Agent 最新结果为 `pass`，且还没有人工标记的场景。
- 人工补测队列：Agent 最新结果为 `partial` 的场景，单独列出。

**统计**：

| 指标 | 定义 |
| --- | --- |
| 复测通过率 | Agent 最新结果为 `pass` 的场景中，人工最新标记为 `pass` 的数量 ÷ 人工已标记为 `pass` 或 `fail` 的数量 |
| 复测覆盖率 | 已复测数 ÷ Agent 判 `pass` 的场景数 |
| 误判明细 | Agent 判 `pass`、人工判 `fail` 的场景，附 Jira 链接，以及双方的执行人、时间和任务身份 |
| 漏测统计 | 只有 SOP 有、只有测试有、预期冲突、未处理，四类各自的数量 |

- `partial`、`blocked`、`skip` 不计入复测通过率。
- 跨批次按时间展示上述指标。标准 §2 要求数量和比率只描述执行情况，所以看板上要同时显示样本量，不能只显示百分比。
- **门槛显示**：门槛暂定为 100%（D3）。
  - 每个批次显示是否达到门槛。复测覆盖率不到 100% 时，显示为“复测未完成”，不判定是否达到。
  - 跨批次显示截至最近一个批次，连续达到门槛的批次数。出现任何一次误判，计数就归零。
  - 门槛只用于展示，不改变复测队列，也不自动减少复测。

**场景变更**：SOP 文件重新导入后，内容（`initial_state`、`steps`、`expected`、`forbidden_effects`）发生变化的场景，之前的 Agent 结果和人工标记标为“场景已变更”，不再计入统计，直到有了新结果。

## 5 命令与部署

| 命令 | 作用 |
| --- | --- |
| `tw team sop check <文件>` | 本地校验，不需要看板服务 |
| `tw team sop import <文件>` | 把 SOP 场景导入看板 |
| `tw team sop push <批次> <结果文件>` | 推送 Agent 结果 |
| `tw board serve --data <目录> --port <端口>` | 启动看板服务 |
| `tw board import-cases \| import-pairs \| import-execution <批次> <文件>` | 导入测试用例、配对文件和执行 JSON |
| `tw board stats <批次>` | 以 JSON 输出统计 |

- 看板地址写在项目的 `.tw/config.json`，字段为 `board.url`。写入令牌通过环境变量 `TW_BOARD_TOKEN` 传递，不写进任何文件。
- 页面：
  - 批次列表；
  - 批次详情，分“对比”“执行”“统计”三个标签；
  - 跨批次趋势。
  - 标记人在页面上声明一次，保存在浏览器本地。
- **部署（D1）**：先在本地运行，不做服务器部署。
  - Python 方式：`python3 <tw 运行时> board serve --data ./board-data --port 8787`。
  - Docker 方式：仓库附带一个最小的 Dockerfile（只基于官方 Python 镜像，不安装第三方包），数据目录挂载为卷：`docker run -p 8787:8787 -v "$PWD/board-data:/data" -e TW_BOARD_TOKEN -e JIRA_BASE_URL <镜像>`。
  - 默认只监听 `127.0.0.1`。需要让同事通过局域网访问时，显式传 `--host 0.0.0.0`。
  - 数据目录由运行它的人自行备份。工具本身不自动发布，也不对外推送。

**篇幅预算（重构方案 M6）**：
- `team-workflow/SKILL.md` 只增加一行按需路由；
- 细节放在新的参考文档 `references/sop-retest.md`，篇幅不超过 3,000 字符，不进入首次必读链；
- 配对提示词作为技能附带的资源文件，不计入指令篇幅。

## 6 已知限制

- 标记人身份由使用者自行声明，只能防止误操作，防不了冒充。推广到更大范围之前，需要接入登录。
- 配对质量取决于 Agent。工具只校验结构和完整性，配对是否正确由人在页面上确认。
- 测试同事的真实用例包含业务内容，不能放进本仓库。测试夹具使用合成样本，覆盖他们格式中的全部写法：多行列表、带引号的流式 tags、注释、中文标点。真实样本只在本机验证时，从仓库外的路径读取。
- 标准库没有 YAML 解析器，所以要实现一个受限的子集解析器；遇到不支持的写法时，报出行号并拒绝导入。

## 7 验收

由未参与实现的代理和用户通过真实入口执行，保留原始输出。

- **A1** `tw team sop check`：
  - 合法文件通过；
  - 删掉某阶段唯一的反向场景后，报错并指出该阶段；
  - 给该阶段加上 `negative_exempt` 后通过；
  - 缺少 `sources` 或 `negative_type` 时报错。
- **A2** 导入合成的测试用例样本，所有字段与原文一致。用本机的真实样本（686 条）验证时，条数和抽查的 3 条完全一致。
- **A3** 导入配对文件后，“对比”标签按四类显示，数量与文件一致。引用不存在的编号时，拒绝导入；遗漏的场景或用例显示在“未处理”里。
- **A4** 推送 Agent 结果：P01 判 `pass`，N01 判 `partial`。在浏览器中，P01 出现在复测队列，N01 出现在人工补测队列。
- **A5** 在浏览器中把 P01 标为 `fail`：
  - 不填 Jira 链接，或填写非 `JIRA_BASE_URL` 开头的链接，都无法保存；
  - 填写合法链接后保存成功；
  - 统计显示复测通过率为 0/1，误判 1 条，并附上该链接。
- **A6** 修改 P01 的 `expected` 并重新导入后，P01 显示“场景已变更”，统计中不再计入它。
- **A7** 导入执行 JSON：键为 SOP 场景编号的条目成为人工标记；键为测试用例编号的条目只作为参考信息显示。
- **A8** 重启服务后数据仍在。第二个批次产生数据后，跨批次趋势能列出两个批次。门槛显示：
  - 批次 1 有 1 条误判，显示“未达到”；
  - 批次 2 中，Agent 判 `pass` 的场景还没有全部复测时，显示“复测未完成”；
  - 批次 2 全部复测且都为 `pass` 后，显示“达到”，连续达到门槛的批次数为 1。
- **A9** 单元测试覆盖第 3、4 节的全部分支。另有一个端到端测试：在临时目录启动真实服务，通过 CLI 和 HTTP 跑通 A1 到 A7。`python3 -m unittest discover -s tests -v` 和 `python3 scripts/check_release.py` 都通过，篇幅预算检查也通过。
- **A10** 试点：选一个真实需求，由开发侧按新格式产出 SOP 文件，Agent 推送结果，至少一位测试同事在看板上完成复测。这一条不能由代理替代。
- **A11** 用 Docker 启动：按第 5 节的命令构建并运行，浏览器能打开看板，数据写入挂载的目录；容器删除后重新运行，数据仍在。

## 8 实施

| 阶段 | 交付 | 依赖 |
| --- | --- | --- |
| S0 | 批次 0：按本格式写出重构阶段 2 的 SOP 场景，手工跑通验证与复测（见第 10 节） | 无，现在开始 |
| S1 | SOP 格式参考文档、YAML 子集解析器、`tw team sop check` | 重构阶段 2 合入 |
| S2 | 看板存储、导入、统计和 API；`sop import`、`sop push`；`board` 系列命令 | S1 |
| S3 | 网页（对比、执行、统计、趋势）和端到端测试；导入批次 0 的数据 | S2 |
| S4 | Dockerfile 与本地启动说明；在真实需求上试点（A10） | S3 |

每个阶段的验收证据记录在 `docs/validation.md`。

## 9 决定（2026-10-14 确认）

| 编号 | 决定 |
| --- | --- |
| D1 | 看板先在本地运行，用 Python 或 Docker 启动均可，暂不做服务器部署 |
| D2 | 方案验收节不引用 SOP 场景编号；任务与批次之间的关联，只靠 Agent 结果中携带的任务身份 |
| D3 | 信任门槛暂定为复测通过率 100%，只用于展示；正式门槛以及达到门槛后如何减少复测，以后再定 |
| D4 | 用本机制验证 tw 重构自身，作为批次 0 |

## 10 批次 0：用本机制验证重构阶段 2

- **场景文件**：[`docs/sop/archive/tw-unified-redesign-phase2.yaml`](https://github.com/AdolphKevin/team-workflow/blob/8be02e4/docs/sop/tw-unified-redesign-phase2.yaml)，共 7 个阶段、29 个场景，每个阶段都有正向和反向场景。
  - 预期结果只依据重构方案 v4，不依据当前实现。
  - 这份文件需要你确认后，才能作为业务原文使用。
- **Agent 验证**：由未参与阶段 2 实现的 Agent 逐条执行，结果按第 3.3 节写成 JSON Lines，保存在 `.tw/local/` 下。原始证据也留在本机。
- **人工复测**：由你复测 Agent 判为 `pass` 的场景。结论先记在一份按第 3.5 节格式写的执行 JSON 中，Jira 链接暂时可以用 GitHub Issue 链接代替。
- **导入**：看板完成后（S3），把批次 0 的场景、Agent 结果和人工标记导入，作为趋势中的第一个批次。
- **格式反馈**：编写批次 0 时发现，命令行工具没有合适的 `verify` 取值，因此增加了 `cli`。后续在批次 0 中发现的格式问题，也都回写到第 3 节。
- **边界**：批次 0 的复测人是方案批准人，不是测试同事，所以它不能替代 A10 的试点。
