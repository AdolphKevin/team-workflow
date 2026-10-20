# 场景文件、验收入口与复测

交付条件见[业务验收标准](business-acceptance.md#5-交付报告)，工具职责与记录绑定见[工具约定](contracts.md#工具做什么)。下文 `tw` 指 `python3 <team-knowledge 技能目录>/scripts/tw.py`。未接入团队流程的项目见[接入指南](onboarding.md)的独立验证方式。

## 1. 场景文件

场景放在业务仓库，推荐 `docs/sop/<批次>.yaml`，按原文登记，只写业务流程，粒度与数量见[场景粒度](business-acceptance.md#场景粒度)。采用 JSON 或 YAML 子集（对象、数组、字符串、数字、布尔值、空值），空格缩进，字符串按需加引号，示例见[场景模板](../templates/scenarios.yaml)。

`sources.confirmed_by` 填原文的实际确认人。代理推断的预期先写方案问题清单，阻塞 `acceptance`；确认后并入场景并补确认人。

- 顶层为 `metadata` 与 `sops`。`metadata` 必填 `requirement`、`batch`、`version`、`owner`、非空 `sources`；每项来源含 `ref`、`version`、`confirmed_by`，可选 `tags`。
- 节点必填 `id`、`title`、`actor`、`entry`、`scenarios`，可选 `must`、`negative_exempt`。每个节点至少一条正向 `positive` 和一条反向 `negative` 场景；反向豁免理由写入 `negative_exempt`。
- 场景必填 `id`、`polarity`、`title`、`actor`、`priority`、`verify`、`initial_state`、`steps`、`expected`、`forbidden_effects`。后四项为字符串数组：前三项非空，副作用数组可空。可选 `refs`、`evidence_hints`、`tags`、`regression`。节点编号在文件内唯一，场景编号在任务内唯一。
- 反向场景另填 `negative_type`：`empty-input`、`over-length`、`not-found`、`permission`、`cross-tenant`、`duplicate`、`concurrency`、`disconnect`、`timeout`、`archived`、`invalid-input`、`incomplete-input`、`interrupted`、`stale-input`、`tampered-input`、`other`。

方案验收节用 `- 场景：docs/sop/<批次>.yaml#SOP-02、SOP-03` 引用节点。`tw team scenarios check <文件>` 核对结构、来源、正反向规则及入口，问题附行号。

回归即按第 6 节重跑受影响的场景。无法经验收入口执行的场景写 `regression: {manual: 原因, owner: 负责人, trigger: 触发时机}`，其余省略。

## 2. 验收入口

在 `.tw/config.json` 的 `acceptance_entries` 中按入口名登记，场景的 `verify` 引用该名称。入口回答四个问题：

| 问题 | 字段与填写方式 |
| --- | --- |
| 最终用户在哪里验收，用什么工具以用户身份操作？ | `surface`、`operate` 为非空字符串；可选 `address_env` 填地址的环境变量名，`accounts` 引用已声明的账号编号 |
| 结果在哪里看到，如何核对不应发生的副作用？ | `observe` 为非空字符串数组，列页面、文件、数据或接收端等观察点 |
| 证据怎么冻结？ | `evidence` 为非空字符串数组，列截图、输出、轨迹及摘要等保存方式 |
| 环境怎么隔离和清理？ | `isolation` 为非空字符串，写明资源边界与清理方法 |

例如 `"cli": {"surface":"cli", "operate":"运行已安装的命令", "observe":["输出、退出码和文件变化"], "evidence":["完整命令与输出"], "isolation":"每轮临时用户目录与工作目录，留证后清理"}`。账号声明及授权见[登录标准](business-acceptance.md#6-真实验证操作手册的最低内容)。

## 3. 三种交付形态

- **Web 应用**：用浏览器工具按场景点击、输入，核对页面、请求、数据与实际接收端。真实账号由用户在真实浏览器登录，随后恢复自动化。
- **命令行应用**：按安装文档装好交付物，执行用户会运行的命令。使用临时 `HOME` 与工作目录，记录命令、标准输出、错误输出、退出码、文件清单与摘要。负向场景覆盖错误参数、缺文件、权限不足、重复执行、中断续接和并发。
- **智能体应用**：沿用[第 5.5 节三层验收](test-capability.md#55-模型与智能体输出)。扮演用户的执行者与语义复核者分开；固定源码、配置和场景快照重复运行，分别统计机械失败率与语义偏差率，修复后从首次重新计数。

其他入口按第 2 节四个问题推导。一个需求可跨多种形态，场景用 `verify` 标明入口。

## 4. 用例导入与覆盖

复杂需求导入主流程用例集，历次导入的并集都要覆盖，同一编号取最后一次导入的内容。

```bash
tw team scenarios import-cases --task <身份> <用例文件>
tw team scenarios coverage --task <身份> --pairs <配对.json>
```

用例文件采用 JSON 或 YAML 子集，顶层 `test_cases` 或 `cases` 数组每项必填 `id`、`title`，其余字段原样保存。代理按业务语义判断覆盖：流程用例由场景覆盖，补齐遗漏场景；细节用例并入覆盖它的流程场景，写进该场景的 `expected`。预期有分歧时以测试同事的理解为准。

配对文件含三个数组，每条导入用例恰好归一类：

- `covered`：`{case, scenarios, note}`，`scenarios` 引用本任务场景编号。
- `conflict`：`{case, scenarios, note}`，预期有分歧。
- `disposed`：`{case, state, reason, confirmed_by}`，`state` 取 `blocked`、`deferred`、`out-of-scope`，由测试同事确认。

存在分歧、缺归类或重复归类时返回 `scenario-coverage-incomplete`。预期仍待确认的部分在首轮后交测试同事确认。

## 5. 执行与提交

独立执行者经声明的入口执行待执行清单，每条场景写一行 JSON：

```json
{"scenario":"SOP-02-P01","status":"pass","actual":"退出码为零，输出符合约定","evidence":["evidence/output.txt"],"executed_at":"2026-10-16T08:00:00+08:00","executor":"验收者姓名","session":"会话标识"}
```

必填字段为 `scenario`、`status`、`actual`、`evidence`、`executed_at`、`executor`。`status` 取 `pass`、`fail`、`blocked`、`skip`；可选 `session`、`finding`、`note`。字符串填实际内容，`note` 可空。`executed_at` 为带时区且截至当前的时间；同一文件每个场景一条结果。证据路径相对结果文件目录并限于其内，`pass`、`fail` 至少一份证据；`blocked`、`skip` 填 `finding` 问题编号。`skip` 计入受阻，验收时受阻问题须有含确认人的接受或延期处置，未验证范围保留在交付记录中。

结果文件与证据放在仓库外或 `.tw/local/`。仓库中的未跟踪文件属于[产品指纹](contracts.md#记录绑定)，在其中写证据会使已通过场景因源码变化而失效。执行到提交期间固定产品和场景快照，保留执行版本与环境；提交前复核快照。

```bash
tw team scenarios pending --task <身份> --format json
tw team scenarios submit --task <身份> --results <结果.jsonl>
```

提交覆盖清单的全部场景，执行者与实施负责人独立。`submit` 核对证据、复制到本轮目录并保存摘要，绑定当前场景与产品指纹；登记成功后可清理原证据。

轮次统计与 `metrics` 口径见[工具约定](contracts.md#轮次验收与回归)，比较时保留分子、分母及轮次。

## 6. 增量验收

`pending` 列出新增、内容变化、上次失败，以及待判定（`undetermined`）的场景。场景内容指纹覆盖 `initial_state`、`steps`、`expected`、`forbidden_effects`。同产品指纹上已通过的场景继续有效；产品变化后，已通过场景进入待判定，由独立执行者按改动范围逐条判定：受影响的重跑后 `submit`；不受影响的写明理由沿用：

```bash
tw team scenarios carry --task <身份> --results <沿用.jsonl>
```

每行 `{"scenario","reason","scope","executor","executed_at"}`，`reason` 写不受影响的理由，`scope` 写依据的改动范围。沿用与重跑分开计数，字段见[工具约定](contracts.md#轮次验收与回归)。受阻项通过问题处置跟进。

## 7. 复测看板契约与搭建

项目代理按本节搭建看板，或为测试同事现有工具增加转换脚本：

1. 读取场景文件与 `tw team scenarios pending --task <身份> --format json`，按 `pending` 展示待执行项，保留场景编号、内容指纹、入口、预期与副作用；其余场景供选择复测。
2. 让人填写状态、实际结果、执行者、时间、证据与缺陷链接。问题编号写 `finding`，链接写 `note` 或证据文件；输出字段遵循第 5 节。
3. 导出结果契约文件与证据目录到仓库外或 `.tw/local/`，逐项核对路径与必填项，再用 `scenarios submit` 登记。看板刷新当前清单与统计，展示缺项和拒绝原因，产品或场景变化时重新取清单。
4. 在[项目验收方案](../templates/project-verification.md)写明看板或脚本的位置、启动方式、维护人、隔离与清理方法，将该方案登记到 `context`。
