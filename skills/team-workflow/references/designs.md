# 分节方案与逐节批准

方案使用稳定章节编号、依赖内容指纹和完整历史。业务场景、问题处置及输入格式以
[工具约定](contracts.md)为准。工具不从自由文本推断批准。

## 内容与依赖

方案包含全局范围、局部范围、接口、数据、验收和实施任务。任务关联具体验收与修改范围；
父需求的完整业务验收另列在全局范围。实施依赖只描述前置任务，不等于方案批准。

父方案和子任务分别评估复杂度、风险、工作量、依据、未决事项与所需能力。没有评估不默认
为简单任务。简单任务先有短方案、可实施后合并评审；中等和复杂任务先批准方案再实施。
风险决定必要检查，不自动改变这两条路径。

`own` 指纹覆盖本节内容和排序后的逻辑依赖；`effective` 另覆盖上游依据及影响本节的实施
决定。业务场景、验证要求与影响调查属于方案内容，改变时需核对受影响的批准。仅阻塞验收
的问题处置独立核对，不使无关实施批准失效。角色分配与章节排列不改变业务内容指纹。

## 批准与变化

批准记录批准人、方案版本及明确章节，有确认依据时一并记录。需求答复、部分字段确认和实施
顺序确认只覆盖实际确认的内容。整份批准展开为当时全部章节，不覆盖后来新增的章节。
最新的修改要求或暂缓不能被更早的批准覆盖。

PR 描述展示已提交的方案原文，发布记录和批准追加为评论，由项目平台脚本一并读取；
展示内容不作为记录，历史摘要、分节批准与局部重审规则相同。`approval-draft --revision <完整提交号>` 将可选 `revision`
记入批准，格式为 40 或 64 位十六进制。合并批准用本地 git 读取该提交的源码，按
`code_digest` 的内容口径比对；不一致拒绝，本地缺提交时报告缺口，不访问平台。
方案批准只校验格式并存档；没有该字段时沿用原行为。

代码评审人可把填好的第 2 版评审 Markdown（含完整绑定区）作为变更请求评审提交，
用 `review --task <身份> --from-platform` 导入；未有已提交评审时 `deliver` 自动导入。
逐项复核、问题历史与本地提交相同，身份及来源核查见[工具约定](contracts.md)。

按旧、新依赖图的并集计算影响，删除依赖也保留原受影响范围。增删章节、业务约束或评估
改变时重审对应部分，未受影响的批准继续使用。完整历史从第一版连续提供，删除与已知
问题均保留处置历史；不能通过再改一版隐藏未确认删除或丢掉问题。

简单任务的合并评审批注同时绑定当前源码与实际运行引用；改了代码或运行材料后重新核对。
父方案复杂不使已经独立评估的简单子任务自动升级为事前评审。待定业务决定只阻塞相关工作。

## 状态与接口

| 输出 | 含义 |
| --- | --- |
| `implementation_ready` | 选中工作已有有效方案、评估和指派；中等及复杂任务另需适用批准；相关实施问题和前置任务已解决 |
| `fully_approved` | 选中章节和相关删除已有有效批准 |
| `local_review_valid` | 批准与实际修改归属可核对；简单任务还有当前合并评审 |
| `acceptance_ready` | 评审与相关问题处置齐备；实际业务结果仍由 `accept` 核对 |

`designs.py` 继续提供 `validate_design`、`fingerprints`、`scope_coverage`、`impact`、
`approval_draft` 和 `approval_status`。局部核对使用 `section_ids`，自动纳入上游依据。
`history` 保留完整旧版本，`changed_paths=None` 表示未知，空列表表示已经核实没有变更。

## Markdown 原文格式

方案正文只维护仓库中的 Markdown，起点见[方案模板](../templates/design.md)。所有显式
`--design`、方案 `--record` 和 `--design-history` 都读这种格式，JSON 方案直接拒绝。
`.tw/local/` 中由工具保存的 JSON 快照只供内部引用，不能用这些参数重新输入。

文件第一行是 `---`，结束的 `---` 之间每行一个 `字段: JSON值`，字段齐全且不重复：

| 文件头 | 内部字段 | 取值 |
| --- | --- | --- |
| `design` | `id` | 稳定方案编号，字符串 |
| `task` | `task_id` | 所属任务编号或规范地址，字符串 |
| `revision` | `revision` | 正整数，每次发布加一 |
| `assessment` | `assessment` | 对象：`complexity`、`risks`、`effort`、`drivers`、`uncertainties`、`required_skills` |
| `roles` | `roles` | 对象：`design_owner`、`implementation_owner`、`acceptance_owner` |
| 自动补齐 | `data_version`、`kind` | 固定为 `1`、`design`，无需书写 |

评估和业务字段的既有要求见[工具约定](contracts.md#业务场景与证据)，不因换格式减免。

```markdown
## 接口约定
<!-- tw-section id=api type=interface depends=scope-global -->
实际接口行为与限制。
```

| 章节写法 | 内部字段 |
| --- | --- |
| 标题文字（`#` 至 `######`） | `title` |
| 标题下一行的 `tw-section` 注释 | `id`、`type`、`depends_on`；`depends` 可省略，多项用逗号 |
| 标记下一行至下一个同级或更高级的带标记标题 | `body`；其中未标记子标题、代码示例仍属正文 |
| 第一个标记标题之前的文字 | 不属于章节，不参与指纹；可写标题、状态、批准记录 |

`type` 为 `global-scope`、`scope`、`interface`、`data`、`acceptance`、`task`。
必须有且只有一个 `id=scope-global type=global-scope`。标记不在代码围栏中生效。

### 结构化章节字段对照

标签行位于正文之后，使用 `- 标签：值`，以下路径均相对本节 `data`。
角色、初始状态、预期这类单值标签取到行尾；分号、顿号、字面引号直接保留，不包 JSON 引号。
多值标签用 `、` 分隔，空数组写 `无`；步骤、反例和操作用 `；` 分隔。只有某一项含实际
分隔符时才用 JSON 引号包住该项，引号内的分隔符不切分；依据的子字段只保护 `；` 和 ` / `，验证行的环境值和列表只保护实际使用的内外层分隔符。
换行及特殊边界用 HTML 字符实体保存：`&` 转义，列表项首尾空白、字面值 `无`、起始 `[`
或不完整的起始引号同样转义，读取时还原；普通行内空白、括号和引号不因此加引号。
数组仍可直接写 JSON 数组。表格的单值列继续按下方的缺省标记与实体规则书写。

| 类型 | 标签或表列 | 内部字段 |
| --- | --- | --- |
| 全局范围 | 需求级验收 | `requirement_acceptance` |
| 全局范围 | 影响范围表：仓库、入口、操作、产生方、使用方、提交负责方、验收 | `impact[].repository/entrypoint/operations/producer/consumer/commit_owner/acceptance` |
| 验收 | 角色、初始状态、步骤、预期、反例 | `scenario.actor/initial_state/steps/expected/negative_cases` |
| 验收 | 依据 | `scenario.sources[]`：`位置 <ref>；版本 <version>；确认人 <confirmed_by>`；多项用 ` / ` |
| 验收 | 检查 | `checks` |
| 验收 | 验证 | `verification`，子字段见下表 |
| 任务 | 验收、范围、前置任务 | `acceptance/scope/blocked_by` |
| 任务 | 评估（可选，JSON 对象） | `assessment`，字段与文件头一致 |
| 各类型的其他数据 | `数据 "<字段名>"`，值为 JSON | 保留既有扩展字段，不丢弃、不推测 |

依据也可写成 `<ref>（<version>，<confirmed_by> 确认）`。早期方案可以省略依据标签，
保持既有缺失状态；验收仍要求有已确认的来源。扩展字段名按 JSON 转义，特殊字符可用 Unicode 转义。

验证标签写在一行，例如：

```markdown
- 验证：自动；层级 journey；入口 tw team start；环境 临时仓库；替身 无；隔离 isolated；隔离依据 无；用例 无
```

| 验证中的文字 | `verification` 内部字段 |
| --- | --- |
| 自动 / 人工 | `method`: `automatic` / `manual` |
| 层级 | `coverage.level` |
| 入口 | `coverage.entrypoints` 数组 |
| 环境 | `coverage.environment` |
| 替身 | `coverage.substitutes` 数组 |
| 隔离 | `coverage.isolation` |
| 隔离依据 | `coverage.isolation_evidence` 数组，省略等于空数组 |
| 用例 | `cases` 数组，省略等于空数组 |

影响范围表使用上表的七列和 Markdown 分隔行；每行对应一项调查。
已知问题用独立标题及下一行 `<!-- tw-issues -->`，表头如下；没有问题可省略整个标题和表格。

| 已知问题表列 | 内部字段 |
| --- | --- |
| 编号、问题、负责人、影响章节、阻塞阶段、状态 | `issues[].id/summary/owner/affects/blocks/state` |
| 原因、证据、确认人、确认依据、后续任务、范围调整 | `issues[].resolution.reason/evidence/confirmed_by/confirmation/follow_up/scope_change` |

所有列都保留；未出现的处置字段写 `—`，空字符串写 `""`，空数组写 `无`，不互相转换。
表格及标题中的 `|`、换行和 `&` 用 HTML 字符实体转义，解析时还原。所有标签、字段和数组顺序保留。

正文统一为 LF，去掉首尾空行和每行行尾空白；保留行内空格、段落间空行、代码围栏和缩进。
`render` 在每个带标记标题前、正文与首个标签之间、标签与表格之间各输出一个空行。
`load` 不把这些排版空行算进正文；只改变这些空白不影响章节指纹和已有批准。
`load(render(design))` 的正文为上述规范化结果，其他字段保持原值；内部结构和指纹算法不变。
正文中的保留标签或标记行可加 Markdown 反斜杠转义，解析时还原；渲染器也会转义未闭合的代码围栏，避免吞掉后续章节。
缺文件头字段、缺标签、非法值、重复编号、未知类型或引用缺失都会报原文行号。

## 发布与隐藏记录

先提交方案文件，保持该文件没有工作区改动，再运行 `design-draft --issue <地址> --record <方案.md>`。
结果的 `pr_description` 是发布提交中的 Markdown 全文，`markdown` 是单独追加的发布评论。
记录的 `design` 仅含 `id`、`revision`、`repository`、`path`、`commit`、`sha256`，其余
任务、发布者、要求签名、历史摘要与前序引用继续保留，不再嵌入整份方案。
工具按本机仓库映射，用本地 `git show <commit>:<path>` 读原文，核对摘要和身份后解析；
缺提交先 fetch，缺映射先补映射，工具不为此访问平台。`status` 和 `start` 提示 PR 描述与
最新原文的差异，提示不改变批准判定。

发布到平台的任务、方案记录、批准、交接（含收尾）、进度都采用可读 Markdown 加
`<!-- tw-record {...} -->` 隐藏注释。任务展示目标、非目标、验收；批准展示批准人、版本、
章节标题及确认依据；交接与进度展示负责人、状态和剩余事项。评审绑定区也采用同一种注释，
受保护区比对、逐项复核、平台评审导入仍按[工具约定](contracts.md)。
工具只从 `tw-record` 解析数据，可见文字不参与判定；旧 `team-workflow-<类型>` 代码块
直接拒绝，须重新生成草稿。注释内的 JSON 字符串将 `-`、`<`、`>` 编为 Unicode 转义，
换行使用 JSON 转义，确保内部没有 `--`、`<!--`、`-->`，读取后逐字还原。
