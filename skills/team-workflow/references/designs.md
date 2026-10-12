# 分节方案与逐节评审

创建或修改团队方案、记录方案批准、判断旧批准能否复用时读取本页。
格式示例位于 [方案模板](../templates/design.json)。运行工具生成评审草稿后，对照实际确认
保留具体评审人和依据；草稿本身不证明任何人已经批准，也不会发布到任务平台。

## 方案格式

方案使用 `schema_version: 4`、`kind: "design"`，保存稳定的 `id`、所属 `task_id`
和从 1 开始连续递增的 `revision`。每次修改保存完整的新版本，旧版本继续可读取。
分工更新同样保存新快照，但分工信息不影响章节批准。

`assessment` 分别记录 `complexity`（`simple`、`medium`、`complex`）、`risks`、
`effort`、判断依据 `drivers`、未确定事项 `uncertainties` 和所需能力 `required_skills`。
除复杂度和工作量外均为文本数组。`roles` 记录 `design_owner`、`implementation_owner`
和 `acceptance_owner`，允许兼任；未指派时用空字符串，状态核查会报告缺项。

每个 `sections` 元素包含 `id`、`type`、`title`、`body`、`data` 对象和 `depends_on` 数组。
编号可含英文字母、数字、点、下划线与连字符，保持稳定，不随章节顺序改变。

| 类型 | 必要内容与关系 |
| --- | --- |
| `global-scope` | 恰好一节，编号固定为 `scope-global`，记录全局目标、非目标及约束；不能依赖其他节 |
| `scope` | 局部功能的范围，由有关章节显式依赖 |
| `interface` | 输入、输出、失败行为及兼容要求 |
| `data` | 结构、约束、迁移及事务要求 |
| `acceptance` | `data.checks` 是检查编号数组；纯内容核对可为空，最终验证仍执行任务和风险要求的检查，`depends_on` 指明验收依据 |
| `task` | `data.acceptance` 是非空验收节编号数组；`data.scope` 是仓内路径数组；`data.blocked_by` 是实施前置任务编号数组 |

所有章节隐式依赖 `scope-global`。任务还隐式依赖 `data.acceptance` 所列的验收章节，
无须再手填同一条 `depends_on`。`blocked_by` 只表示执行顺序：前置任务所依赖的接口变化
不会因此使后置任务的方案批准失效。两种关系均检查缺失引用和循环。

范围是具体的仓内相对路径，目录向下匹配；`.` 表示整个仓库。拒绝上层目录、绝对路径、
反斜线与通配符。多仓任务由调用方分别提供对应仓库的变更路径。缺少范围、未枚举变更、
或存在未归属的变更时，不能报告局部评审仍然有效。选择整仓重审时，先把任务范围明确
改为 `.`，再审核其对全部内容的影响。

需要跟踪具体业务选择时，可增加 `decisions`：每项包含稳定 `id`、`question`、
`status`（`pending` 或 `confirmed`）、受影响章节 `affects`，确认后必须有 `answer`。
空的 `affects` 表示影响整个方案。待定选择沿依赖关系阻塞有关任务；普通不确定事项仍由
`uncertainties` 展示。确认或改变答案会使受影响章节需要重审。

## 内容指纹与批准

当前指纹算法编号为 `fingerprint_version: 1`。所有文本统一换行为 LF，使用键排序的
UTF-8 JSON 计算 SHA-256；不推测两段自然语言是否意思相同。

- `own` 绑定章节编号、类型、标题、正文、结构化内容及排序后的逻辑依赖。
- `effective` 绑定本节的 `own`、全部上游章节的 `own` 以及影响本节的业务选择。
- 章节排列、对象键排列、依赖列表排列和分工信息不改变章节指纹。评估信息另有
  `assessment_hash`；复杂度、风险或判断依据变化需要重新评审。

批准使用 `schema_version: 4`、`kind: "approval"`，包含 `design_id`、`task_id`、
`design_revision`、指纹算法编号、评估指纹、`reviewer`、`confirmation`、`decision`、
`mode`、明确的 `sections` 编号到 `{own, effective}` 映射，以及 `deletions`。
结论为 `approved`、`changes-requested` 或 `deferred`。读取历史时按从早到晚的顺序传入，
同一章节以最后一份相关记录为准；后来的拒绝或暂缓不能被更早的批准覆盖。

整份批准展开为当时全部章节的清单，不覆盖后来新增的章节。部分批准只包含指定章节。
上游仍待评审、要求修改或暂缓时，中等和复杂任务不能只凭任务节自身的批准进入实施。
删除记录保存旧 `own`、旧 `effective`、删除前版本和删除版本；后续版本继续保留核查，
不能通过再改一版让未确认的删除消失。

简单任务允许先实施，包括涉及接口、权限或数据库的简单任务；必要检查仍由风险决定。
其交付需要 `mode: "combined"`，同时绑定 `code_digest` 和明确的 `run_refs`（仅在没有必要执行项时可为空）：
每项运行引用为 `{ "path": "运行记录位置", "sha256": "内容指纹" }`。代码、运行记录
或有关删除与当前输入不一致时，合并评审不能作为完成依据。方案模式 `design` 不带代码
或运行字段。此处只校验绑定关系，真实执行成功与报告内容仍由验证工具检查。

## 影响计算与局部核查

比较相邻完整版本，识别新增、修改、删除的章节及改变的业务选择。对旧、新逻辑依赖图的
并集计算下游范围；删除依赖也不能保护原来受它约束的下游批准。评估变化影响全部章节。
原始测试是否重跑由实际源码、检查与环境决定；这里的“需要重审”不会替代执行结果判定。

完整历史从第 1 版连续提供。缺版本、同版内容冲突、旧格式或旧指纹算法不自动转换。
保留原材料，补齐历史或通过明确的升级流程再生成新记录。

`approval_status` 可传 `section_ids: ["T1"]`，工具自动纳入全部上游依据，返回
`required_sections` 和 `required_tasks`。未影响这些章节的其他任务可以继续修改。
删除只阻塞其自身旧、新依赖关系所影响的选中任务；整份方案核查始终要求全部删除已确认。

| 状态 | 含义 |
| --- | --- |
| `implementation_ready` | 选中任务已指派、没有相关待定选择或未完成前置任务；中等和复杂任务还需有效批准 |
| `fully_approved` | 选中章节及相关删除已经批准，记录格式与完整历史可核对 |
| `local_review_valid` | 选中批准与变更归属均可核对；简单任务还需当前合并评审 |
| `acceptance_ready` | 评审条件齐备、职责明确且没有相关待定选择；仍需实际业务验证和交付核查 |

## 供工具调用的接口

`scripts/designs.py` 仅使用标准库和共享校验函数；不访问文件、Git、网络或 CS，不修改输入。
调用方负责读取历史、枚举真实变更、核对运行材料及保留批准依据。

- `validate_design(design)`：严格校验并返回输入；错误抛出 `common.Invalid`。
- `fingerprints(design)`：返回算法编号及各章节的 `own`、`effective`。
- `scope_coverage(design, changed_paths)`：返回变更到任务的映射、未归属变更和缺失范围。
- `impact(previous, current, changed_paths=None, *, history=None)`：返回本次受影响章节及历史删除。
- `approval_draft(design, reviewer, confirmation, decision='approved', section_ids=None, previous=None,
  code_digest=None, run_refs=None, mode=None, *, history=None, deletion_ids=None)`：生成明确的评审记录。
  `section_ids=None` 表示整份方案及全部历史删除；显式指定章节时只批准这些章节，删除必须
  另传 `deletion_ids`。仅评审删除时使用 `section_ids=[]`。
- `approval_status(design, approvals, previous=None, changed_paths=None, code_digest=None,
  run_refs=None, completed_tasks=(), *, history=None, section_ids=None)`：读取审批状态和下一步缺项。
  `history` 是旧版完整快照数组；`previous` 可补传紧邻旧版。`changed_paths=None` 表示未知，
  空数组表示调用方已经核实没有变更。所有状态输出均保留全部章节，完成判断以选中范围为准。

### 子任务评估

任务节可在 `data.assessment` 中分别评估复杂度、风险、工作量依据和所需能力；字段与方案的 `assessment` 相同。未填写时沿用方案评估。选中的简单子任务可以合并评审，即使父方案复杂或风险较高；对应风险检查仍不可省略。任务的风险集合须与选中任务节的评估一致。
