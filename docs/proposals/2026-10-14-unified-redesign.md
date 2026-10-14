# team-workflow 与 CS 合并重构方案（草案 v4）

> 状态：已批准，实施中 · 日期：2026-10-14 · 方案负责人：Claude（核心调研） · 协作设计：Codex · 评审与批准：AdolphKevin
>
> 本文只是设计，不包含实施。章节编号保持稳定，可以逐节批准。文中的 `.tw/`、`team-knowledge`、`tw` 是 N1 确认的命名。
>
> 修订记录：
> - v2：按 Codex 对抗式评审修订 12 处。
> - v3：按你的三点意见修订，涉及迁移改由代理整理、历史教训按需找回、只保留最新设计。
> - v4：撤回 v3 的 N8（不保存取代与演变）。改为保留“放弃过的做法及原因”，并规定教训不随代码变化删除。
> - v4.1：阶段 2 实施中经你确认的两处范围调整。T1 保留任务编号，本地目录为可读名称加身份哈希；C 节的命令重新分组移到 T7。
>
> 各轮修订的对照见附录 C。

## 批准记录

| 时间 | 批准人 | 范围 | 依据 |
| --- | --- | --- | --- |
| 2026-10-14 | AdolphKevin | v4 全文；G3 中 N1–N8 全部确认 | 会话中逐项确认 N1、N2、N3、N5、N6，随后指示“开始执行这个方案” |
| 2026-10-14 | AdolphKevin | v4.1：T1 保留任务编号与可读目录；C 节的命令重新分组移到 T7 | 阶段 2 独立评审 F6、批次 0 第一轮缺陷 F3 之后，会话中确认“可以” |

实施分支：`feature/unified-redesign`。按 I 节分阶段进行，每个阶段的验收证据记录在 `docs/validation.md`。

## 0 摘要

- **一个仓库、一个运行时**：
  - CS 合入 team-workflow 仓，只保留一份 Python 标准库运行时。
  - 分为两个技能：团队入口 `team-workflow`（沿用原名），以及知识入口 `team-knowledge`（取代 `cs`）。
- **项目内一个根目录 `.tw/`**：
  - 入库知识与 `local/` 本地数据放在同一个目录。`local/` 由嵌套的 `.gitignore` 隔离，并由 `tw check` 校验。
  - 迁移完成后，`.codestable/`、`.team-workflow.json`、`.team-workflow/` 都不再存在。
- **默认展示最新的设计，同时保留放弃过什么**：
  - 知识描述现在仍成立的约束、决策和教训。
  - 决定改变时，正文改写为现行结论，旧做法和放弃原因移入同一文件的“放弃过的做法”一节，不删除。
  - 教训不随代码变化删除。完整的版本历史交给 git。
  - 取消 11 类目录，任务记录不再入库。
  - 条目分三种：`rule`（现行约束）、`decision`（决策）、`lesson`（踩过的坑），另有 `glossary` 和 `overview`。
  - 用 Markdown 直接编辑，与代码在同一个 PR 中评审。
  - 工具只做导航（`brief`）和结构检查（`check`/`audit`）。计划令牌、锁、回执、内容指纹、`future_use`、跨文件取代链等机制全部删除。
- **把“遇到过的错误”作为首要沉淀对象**：
  - 设立 `lesson` 种类。缺陷流程中必须考虑写 lesson，并尽量绑定守护测试。
  - 从 git 历史找回教训不做成默认流程，由用户在需要时指挥代理去做。目前只计划为 agent-py 找回 Agent Native 开发中的教训，包括把 agent 仓的相关教训迁入 agent-py。
- **迁移不写脚本**：
  - 已接入的项目由代理按迁移指南整理旧知识：逐条核实后，用新格式和新的表述写入 `.tw/`，再删除旧目录，用一个 PR 交给用户确认。
  - 新运行时完全不读取旧格式。回退时直接撤销 PR。
- **团队流程**：本次只拆除与知识之间的桥接，并统一任务身份、证据位置和版本号。流程本身的简化放到第二阶段单独评审。
- **验收**：
  - 先在 agent-py、core、common 试点迁移，由独立代理复核，高风险结论经真实入口核对。
  - 最后由两位真实成员双向接续。

## 1 评估

| 项 | 内容 |
| --- | --- |
| 复杂度 | 复杂：两个仓库重写合并；约 15 个已接入项目迁移；团队流程衔接点改动 |
| 风险 | public-contract（技能入口、项目数据格式、CLI）、persistence（知识迁移与删除）、cross-service（多仓知识归属与依赖解析） |
| 工作量 | 工具实现：阶段 1–2 约 2–3 周，单人加代理，逐阶段验收，属于粗估。迁移见 B7 |
| 依据 | 5 份调研报告，以及 Codex 四轮产出，见附录 B |
| 未决事项 | 文中引用的统计数字在使用前抽查复算 |
| 所需能力 | Python 标准库与 git；Claude Code、Codex、Cursor 的技能机制；业务仓验证环境（PostgreSQL 等）；迁移时由用户确认 live-chat 的业务判断 |

本任务属于复杂任务，按团队流程**先批准方案，再实施**。G3 的决定已全部确认，方案正文可以整份批准，也可以逐节批准。

---

## G 全局范围

### G1 目标与非目标

**目标**

1. 一个仓库、一个运行时、一个项目根目录、一个稳定的任务身份、一个项目数据版本号。
2. 写知识的成本接近改一份文档，可以评审，也可以核实。重点沉淀三类内容：
   - 错误教训；
   - 业务规则的来源与例外；
   - 设计理由。
3. 读取精准，篇幅有上限，诊断信息与知识分开。
4. 已接入项目由代理整理迁移，只保留现在仍然成立的设计。未核实的内容单独列出清单，不会被静默丢弃。
5. 指令文本有篇幅预算，规则有删减机制。

**非目标**

- 不降低团队流程现有的批准、业务验收、独立验收和交接要求。流程简化另行评审，见 T7。
- 不做自动观察，也不做后台自动写知识（ECC observer 那种方式）。首版也不做钩子注入，见 R5。
- 不提供迁移脚本，新运行时也不读取任何旧格式。
- 知识库不保存完整的版本历史（交给 git），但“放弃过什么、为什么”必须保留在现行条目中（K1）。
- 不默认从 git 历史挖掘教训。
- 不自动提交、推送、发布，也不自动关闭 Issue。

### G2 设计原则

| 编号 | 原则 | 我方证据 | 借鉴 |
| --- | --- | --- | --- |
| P1 | 知识是可评审的文档，不是数据库记录：直接编辑，并发交给 git，评审放在 PR | 写一条知识要走 template、手写 JSON、预览、计划文件、应用、doctor；一次会话手写了 25 段 JSON；另一位成员 44 个代码提交从未改动知识 | MATT#294 主张“像代码一样评审”；Trellis 直接编辑 spec；ECC team memory 人工审核后入库 |
| P2 | 默认展示最新的设计，只记代码里看不出来的东西：业务来源与例外、理由、边界、坑、跨服务约定，以及放弃过的做法和原因。不记完整版本历史、一次性结果、工具版本、行号、任务流水 | acceptance 卡写着“本次 436 项通过”；9 个 PROJECT.md 写着过期的工具版本；34% 的 memory 卡已被取代却仍在库中 | MATT writing-for-agents（能从环境查到的就不写）；Trellis 的 741 个行号锚点中 17% 已失效 |
| P3 | 结构检查只查客观缺陷，语义交给评审和独立验收 | future_use 的约束等于标题（5 个仓都是 7/7）；evidence.result 照抄结论；已提交的卡片残留 `__REPLACE__` | ECC Memory Vault 的 doctor 只报告不修改；MATT 认为“未评审的词汇表比没有更糟” |
| P4 | 绑定 git 提交，不绑定整文件的内容指纹 | 6 天后 17/17 张卡变成 needs-review；brief 每次都附带 6 条“已变化”提示 | Trellis 把运行态移出仓库 |
| P5 | 一个事实只有一个正文归属，原文优先 | #146、#147 在 3 个仓各写了一份；“单测不等于端到端验收”在 4 个仓重复出现 | ECC living-docs 的单一归属原则 |
| P6 | 读取分层，并设预算 | 一次聚焦 brief 有 82KB，诊断占 55%；约 22 个任务中只有 6 个读过 brief | Trellis #154（31–36KB 被截断后改为约 6KB）；ECC 的 8,000 字符上限 |
| P7 | 规则有预算，也有删减机制 | CS SKILL.md 从 8KB 涨到 38KB；TW references 有 102KB；一个团队任务的阅读链约 129KB | MATT writing-for-agents 定期清理无效指令 |
| P8 | 发布与开发分开，项目数据尽量不升级 | 至少 8 个版本轴；推送 main 即发布；各项目停在 schema 1/3/4/5；adopt 同一天被删又被加回 | Trellis 的模板哈希（只借鉴思路） |

### G3 决定（已全部确认，2026-10-14）

| 编号 | 决定 | 依据 |
| --- | --- | --- |
| N1 | 命名：目录 `.tw/`；技能 `team-workflow`（沿用）和 `team-knowledge`（取代 `cs`）；CLI `tw` | 通用名在代理工具圈已被占用：`workbench`、`wb`、`.workbench/` 被 wbcli 使用，`.keel/` 被 KEEL 使用，`.baton/` 被 blader/baton 使用，cairn 有多个同名项目。沿用 `.team-workflow/` 会与三处冲突：旧的纯本地证据目录、各项目根 `.gitignore` 中的忽略行、现有运行时（`common.py:177`）。新目录与旧布局互不重叠 |
| N2 | 任务记录不入库：结果依次保存在 Issue、PR、提交说明中，本地只留草稿 | 89 条任务记录中有 30 条是维护或合并流水；knowledge_use 极少使用；内容与 Issue 和交付产物重复 |
| N3 | 知识分类按现行 K1 的种类与边界：rule、decision、lesson，加上 glossary 和 overview | 11 类分类产生了 32.5% 的脚手架文件，还出现按配额建卡、同一概念被拆进 3 类的情况 |
| N4 | 从 git 历史找回教训不作为默认流程，也不提供工具，由用户按需指挥代理执行。目前只计划为 agent-py 找回 Agent Native 开发中的教训，并把 agent 仓里适用的教训迁入（B5） | 用户确认 |
| N5 | 团队流程的简化放到第二阶段 | 本次已涉及公开契约和数据迁移，再叠加流程语义变化，出问题时难以定位 |
| N6 | CS 仓归档，新仓不保留 CS 的提交历史 | 运行时整体重写，旧历史仍可在归档仓中查阅 |
| N7 | 迁移由代理按迁移指南整理，不提供迁移脚本；新运行时不读取旧格式（B） | 用户确认 |
| N8 | 保留“放弃过的做法”：决策改变时正文改写为现行结论，旧做法连同放弃原因、可重新考虑的条件和来源，移入同一文件的“放弃过的做法”一节；明确不做的事记为 rejected；教训不随代码变化删除；brief 在相关时主动提示。属于 K1 的内容，随 N3 一并确认 | MATT 用 `superseded by` 和被否决的备选；ECC 用 delete-zone；我方 TW 的规则反复横跳；9 月 5 日重建后，教训虽仍在 git 中，代理却读不到 |

---

## P 问题与证据

按影响排序，箭头后为本方案对应的章节。数字采集于 2026-10-14，来源见附录 B。

1. **写入仪式过重，知识很少被写**。
   - 写入链路有 5 步，还要手写 JSON、循环重试，并出现过误用旧计划。
   - 另一位成员 9 月以来的代码提交从未改动知识；小服务重建后几乎没有知识提交。
   - 用户原话：“teamwork + cs 工作流…感觉不太好用”。
   
   → W、K3
2. **最有价值的教训没有沉淀**。
   - 用户原话：“cs 这个项目最大的价值就是沉淀历史遇到的错误”。
   - 9 月 5 日重建时丢弃了约 547 张旧卡，只有 agent-py 用 history-review 保留了 27 组教训。
   
   → K1 lesson、K3、B5
3. **工具状态互相作废**。
   - 写入同范围的新卡会让开工简报过期；任何 Wiki 改动都会让 learn 计划令牌失效。
   - 在旧版本和按提交绑定的检查中，提交知识会让执行证据过期。41b1a5a 已改为按检查分别选取结果；现行 `validation.py` 默认按内容绑定，并排除了 `.codestable/`。
   - 结果是代理按“让工具通过”的顺序操作：一个 +18/−5 的改动产生了 10 个请求、39 个本地文件。
   
   → T3、T7
4. **门槛逼出形式填充**。future_use、evidence 被机械填写，还残留占位符；CS 卡片的 front-matter 共 53,263 字符，正文只有 3,221 字符。→ K2、W2
5. **固定 11 类**。
   - 1203 个入库文件中，391 个是脚手架。
   - 165 个分类 README 中，73 个是空模板。
   - README 漏列了 18 张当前卡。
   
   → K1、L1
6. **知识失真检测不到**。
   - common 有两张 accepted 卡已被 core 的测试和 proto 否定，但路径检查照样通过。
   - memory 的 51 张当前卡中，27 张引用了已不存在的内容。
   
   → B3、W3
7. **读取篇幅大，相关性弱**。
   - brief 有 82KB，其中知识只占 28%。
   - 相关性只靠路径前缀和中文二元词。
   - always:true 的原文每次都全文返回。
   
   → R
8. **概念重复**。
   - 任务有三套 ID；plan、acceptance 一词多义。
   - 自检命令有 4 种。
   - 8 项 capability 两仓各写一份；lint 脚本两仓字节相同。
   
   → T1、M
9. **版本与发布混乱**。
   - 至少 8 个版本轴；TW 5 天发了 6 个版本。
   - 工具升级迫使每个仓走一轮维护；2.1.0 工具直接拒绝 schema 4。
   
   → M5
10. **指令文本只增不减**。一个团队任务的阅读链约 129KB。→ M6
11. **跨仓知识重复，原文登记几乎没人用**。595 个范围项中只有 17 个跨仓；depends_on 的使用次数为 0；所有项目的 documents 登记加起来只有 1 条。→ K4、K5
12. **本地证据膨胀**。
    - TW 的 `.team-workflow/` 5 天积累了 571 个文件。
    - core 的 `.team-workflow/` 有 2,402 个文件、646MiB，其中 delivery-followup* 一项就有 318 个文件、583MiB。
    - TW 仓忽略了自己的 `.codestable/`，它的知识只存在本机。
    
    → L2
13. **摩擦的量级**。
    - core 的一次交付会话中，可见的失败至少 37 次，补救重试至少 15 次，失效后重做至少 3 轮，过期计划重试至少 10 次。
    - 补救窗口约 41 分钟，约占活跃时间的 12%（估算，含并行工作）。
    
    → W、T3

---

## K 知识模型

### K1 种类与边界

| 种类 | 位置 | 写什么 | 不写什么 |
| --- | --- | --- | --- |
| overview | `overview.md` | 项目做什么、和谁协作、从哪里开始读代码；不超过 1,200 字符 | 工具版本、统计数字 |
| glossary | `glossary.md`（项目没有已登记的词汇原文时才使用） | 项目特有的术语（MATT 格式，`_Avoid_` 列出同义词） | 通用词、实现细节 |
| rule | `rules/<slug>.md` | 现在必须保持的行为、契约、边界和跨服务约定。条件与例外写在一起，并写明业务来源 | 能从代码直接读出、又没有业务来源的描述性事实 |
| decision | `decisions/<日期>-<slug>.md`（项目没有已登记的 ADR 目录时才使用） | 现行的 ADR：背景、决定、真实备选及不采用的理由、后果，以及**放弃过的做法**。只在“难以逆转、没有背景会意外、确有取舍”三条同时成立时写。明确不做某事，且满足同样条件时，记为 rejected | 普通的实现选择、尚未批准的计划、逐次修改的过程记录 |
| lesson | `lessons/<日期>-<slug>.md` | 踩过的坑：现象、根因、修复与防护、发现方法、适用条件。尽量绑定守护测试 | 一次性失败、找不到根因的流水 |

- 原来的 11 类（事务边界、安全边界、兼容性等）改为可选的 `tags`，同时作为评审时的检查清单，不再对应目录。
- **现行在前，放弃过的保留**：
  - 条目存在即有效。decision 只有 `accepted` 和 `rejected` 两种状态；rule 和 lesson 不设状态字段。
  - **决定改变时**：正文改写为现行结论；旧做法移入同一文件的 `## 放弃过的做法` 一节，不删除。该节每项写：做法；放弃原因（失败机制或证据）；什么条件下可以重新考虑；来源（提交、Issue）；关键词（任务描述里可能出现的说法，brief 用它提醒）。三种条目都可以有这一节。
    - 这样不会出现 MATT#822 那种失效文件和现行文件混在一起的情况，也不会出现 #1114 那种只追加修订、原结论却不变的矛盾。
    - 作用与 MATT 的 `superseded by`、“被否决的备选”和 ECC 的 delete-zone 相同：防止被放弃的方案再次被提出。
  - **rule 失效时**：如果失效原因值得记住（例如曾因某种故障被废除），把它写进相关 decision 的“放弃过的做法”或写成 lesson；否则删除。
  - **lesson 不随代码变化删除**：代码重写后同样的错误还会再犯。实现位置变了，就更新 scope。只有整类错误已经不可能发生（例如相关技术栈被整体移除），并经评审确认，才删除。
  - 逐次修改的完整过程交给 git，不在知识库中复述。

### K2 文件格式

- 文件头用 `---` 包围，每行一个 `字段: JSON值`。用标准库就能解析，不实现通用 YAML。
- 种类由所在目录决定，文件路径就是条目的身份。
- 文件名用 ASCII kebab-case，中文标题写在 `title` 和一级标题里。
- 不用顺序编号。MATT 目前取最大号加 1，并行分支会撞号（MATT#799）。

| 字段 | 适用 | 含义 |
| --- | --- | --- |
| `title` | 全部，必填 | 与一级标题一致 |
| `scope` | rule、decision、lesson，必填 | 路径 glob 数组，如 `self:internal/**`、`common:protos/brand/**`，语法见 R2 |
| `source` | 全部，必填 | Issue、PR、提交链接、`仓库:原文路径`，或用户确认记录的链接 |
| `verified` | rule、lesson 必填；其余可选 | 按仓库记录 `{"self":{"commit":完整哈希,"date":日期}}`，表示作者实际核对时的基线，不代表测试通过；工具不会自动填写 |
| `status` | decision 必填 | `accepted` 或 `rejected` |
| `guards` | rule、lesson，可选 | `仓库:测试路径#测试名`，或 `check:检查名` |
| `symbols` | 可选 | 精确的符号名，作为检索线索，不能证明业务事实 |
| `tags`、`related`、`owner` | 可选 | 标签；关联条目（读取时扩展一层）；跨仓契约的负责人 |

**删除的字段**：`future_use`、`confidence`、结构化证据四元组、`knowledge_use`、`fingerprint`、`revision`、`supersedes`、`superseded_by`、`applies_to`、`depends_on`、`pinned`、`topics`，以及与 `scope` 重复的 `paths` 和 `scopes`。

**示例 1：决策**（由 core 的会话语言卡改写，`decisions/2026-10-13-conversation-language.md`）

```markdown
---
title: "建会话前确定语言，并使用独立字段保存"
scope: ["self:internal/biz/conversation_language_biz.go", "self:internal/data/conversation_repository.go"]
source: ["https://github.com/channelwill/cw2-live-chat/issues/146"]
verified: {"self":{"commit":"108e82b5a2dd56ef8ef2f370259810de9c653bf6","date":"2026-10-14"}}
status: "accepted"
---
# 建会话前确定语言，并使用独立字段保存

创建会话时，路由先于消息交给代理；如果等代理逐轮回写，首次路由就拿不到语言。
因此在创建事务前判定语言，随会话一起写入。

语言使用独立字段，之后只接受代理依据更新的买家消息回写。

## 备选
- metadata：整体覆盖更新，会增加并发覆盖的风险。
- 只靠代理后续判定：首次路由拿不到结果。

## 后果
符合付费条件的组织会多一次有截止时间的同步调用，失败时必须回退。阈值与套餐条件由相关 rule 和测试维护。
```

**示例 2：已被代码否定的旧卡**

common 里有两张旧卡：“满 30 天由 Owner 永久删除”和“异步清理任务”。迁移时写成一份现行决策，旧做法放进“放弃过的做法”：

```markdown
---
title: "归档超期后保留品牌及历史，不提供永久删除"
scope: ["self:protos/brand/**"]
source: ["self:docs/refactor-baseline/exceptions.md", "<迁移 PR 中的用户确认记录>"]
verified: {"self":{"commit":"b7a00482c7648a6ce982bf2fbdb8507bed0fdc67","date":"2026-10-14"}}
status: "accepted"
---
# 归档超期后保留品牌及历史，不提供永久删除

归档后只能在恢复截止时间之前恢复；超期后作为不可恢复的归档永久保留。
不提供人工删除、自动删除或清理任务。协议中保留原清理状态的编号和名称，防止被再次复用。

## 放弃过的做法
- 满 30 天由 Owner 显式永久删除，再由不可恢复的异步任务清理（2026-08 设计，曾为现行决定）。
  放弃原因：（迁移时从 EXC-018 原文摘录，不能只写引用）。
  重新考虑的条件：（同上，例如出现合规删除要求时）。
  来源：common 旧卡 k-20260821-192858-03、k-20260824-115521-07；protos/brand/brand.proto 中的保留项（dedeca5）。
  关键词：永久删除、清理任务、彻底删除品牌
```

括号中的内容在迁移时据原文填写，这里只示意格式。

**示例 3：教训**（来自 agent-py 的 history-review H06，`lessons/2026-09-05-operation-reaffirmation.md`）

```markdown
---
title: "重复表达操作不能制造新案件或丢失原案件"
scope: ["self:packages/order_graph/**"]
source: ["https://github.com/channelwill/cw2-live-chat-agent-py/commit/f0dd458241"]
verified: {"self":{"commit":"b4d0aa0647e2483d2816cbc817b8c8ab1e72f328","date":"2026-10-14"}}
guards: ["self:tests/order_graph/test_evidence_boundary.py#test_new_task_frame_does_not_project_host_route_as_active_operation"]
---
# 重复表达操作不能制造新案件或丢失原案件

现象：路由参数被当成已有案件的事实；用户再次表达同一操作时，原案件可能被替换。
根因：混淆了入口选择与业务状态。
修复与防护：入口参数只用于选择处理入口。版本匹配、且仍在收集信息的案件收到纯重申时，
只重新提示缺失的信息，保持案件引用、版本和加密内容不变，不查询订单，也不创建动作。
适用条件：没有有效的新字段，也没有新订单或操作切换。
发现方法：检查新任务是否被错误地赋予了活动操作。守护测试只覆盖这一半，续接行为仍缺测试。
```

示例中的提交哈希和测试名来自 Codex 的只读核对，正式写入前还要再核实一次。

### K3 写入时机与门槛

| 时机 | 写什么 | 谁确认 |
| --- | --- | --- |
| 修复缺陷，且根因不明显 | lesson，尽量附上守护测试；团队流程的缺陷保护记录中增加“教训”一项（T5） | PR 评审人 |
| 方案批准中出现 ADR 级的选择 | decision（已有登记的 ADR 原文时写在原文处） | 方案评审人 |
| 业务验收确立或改变了行为契约 | 新增或改写 rule | 验收负责人 |
| 逻辑任务收尾，或到了评审节点 | glossary 或已登记的词汇原文；不在术语刚出现时就写（MATT#130） | PR 评审人 |
| 用户要求找回历史教训 | 按 B5 写 lesson | 用户 |

- 工具不判断“值不值得写”，也不判断“是否与任务相关”，只检查客观缺陷（W2）。
- 门槛靠格式说明中的正反例和评审来把关，不靠必填字段的数量。
- 团队任务仍然遵循“先业务验收，再写知识”的顺序。知识与代码在同一分支提交，不另外生成任务记录。
- 交付物中包含一份**成员操作说明**，附带正反例，覆盖以下情形：
  - 日常改写已有 rule；
  - 不需要沉淀的任务；
  - 无法核实时的处理：不写成条目，在 Issue 中留待确认。

### K4 跨仓知识归属

- 事实写在契约提供方的仓库中。消费方用 `related: ["common:rules/brand-recovery.md"]` 引用，不复制正文。
- 团队通用的流程规则，例如“单测不等于数据库或端到端验收”，写进技能的业务验收标准，不在各业务仓重复。
- 共享仓需要在 `config.json` 的 `shared` 中显式声明。brief 只读这一层，不递归。
  - 读取时会展示实际的检出目录、HEAD 和未提交状态。
  - 同一远端的不同 worktree，靠检出目录和 HEAD 区分。
  - 缺少映射时只给提示，不猜测，也不自动克隆。
- 跨仓契约可以用 `owner` 指定负责人，由负责人接受契约变更。

### K5 原文登记与原文优先

- 在 `config.json` 的 `documents` 中登记原文：`[{id,title,source,scope,section?}]`。
  - `source` 可以是仓内 glob（如 `self:docs/adr/*.md`）、跨仓路径或外部链接。
  - 这取代了逐个文件手写的 `documents/*.json`。
- **原文优先**：项目已有 GLOSSARY.md、ADR 目录、RFC、SOP 等原文并已登记的，直接修改原文，知识条目只做链接。只有在没有已登记原文时，才写入 `.tw/glossary.md` 或 `.tw/decisions/`。MATT 的适配也按这个规则执行（M4）。
- 外部链接（如 Notion PRD）只返回标题和链接；使用 `tw read --online` 时才访问远端。
- 取消 `always:true` 原文的全文注入，只保留 overview 常驻。

---

## L 项目内布局

### L1 目录树

```text
.tw/
├── .gitignore            # 工具维护，内容为 local/
├── config.json           # 入库
├── overview.md           # 入库
├── glossary.md           # 入库，可选
├── rules/                # 入库，按需创建
├── decisions/            # 入库，按需创建
├── lessons/              # 入库，按需创建
└── local/                # 忽略，按检出目录隔离
    ├── repositories.json # 本机映射：仓库别名 → 路径，外部文件输入 → 路径
    ├── cache/            # 可以随时重建的索引
    └── tasks/<任务身份>/  # 方案草稿、运行原件、验收与交付证据
```

新项目只生成 `.gitignore`、`config.json`、`overview.md` 三个入库文件。作为对比，目前 2.1.0 的小服务约有 23 个脚手架文件。

`config.json` 的字段：

- `format`：固定为 `"channelwill/team-workflow"`，用于区分同名工具。遇到其他工具的 `.tw/` 时拒绝接管。
- `data_version`：首版为 1。
- `project{id,name}`：id 取规范化后的 git remote。
- `context`：项目操作手册等开工时需要阅读的文档。
- `shared`、`documents`。
- `checks`、`required_checks`、`risk_checks`、`inputs`、`external_inputs`、`environment_versions`、`accounts`：沿用原 `.team-workflow.json` 的含义，第二阶段再简化。

### L2 隔离与防误提交

- 嵌套的 `.tw/.gitignore` 由工具维护。以下情况 `tw check` 会报错：
  - `local/` 没有被忽略；
  - `local/` 下有已跟踪的文件；
  - 根 `.gitignore` 忽略了整个 `.tw/`。
- 工具只写 `local/`，显式调用的 `init`、`new` 除外。
- 工具从不执行 `git add`，也不自动提交。Trellis 出过两次事故：一次 `git add -f` 提交了 548 个文件；另一次自动提交把已删除的系统带回了主线。
- `local/` 按检出目录隔离，每个 worktree 各有一份；缓存与 HEAD 绑定，避免 ECC 那种跨 worktree 的泄漏。
- 本地证据设上限（core 现在有 646MiB）：
  - 单个原件超过上限（默认 20MiB）时，只保存摘要和外部位置；
  - `tw clean --older-than` 只清理已交付任务的原件；
  - `tw audit` 报告 `local/` 的体积。

---

## R 读取路径

### R1 入口

- 项目 `AGENTS.md` 的托管块不超过 400 字符，只放指针：开工前运行 `tw brief`，完成后按知识规则更新。
- `CLAUDE.md` 只保留 `@AGENTS.md`，Cursor 规则也只放同一个指针。托管块只替换自己的那一段，其他内容保持不变。
- 调用方式：代理在已安装的 `team-knowledge` 技能目录中运行 `python3 <技能目录>/scripts/tw.py`，与现在调用 CS 的方式相同，不需要加入 PATH。

### R2 brief 选择算法

1. **规范化**：规范化仓库身份、相对路径和符号，拒绝越界路径。glob 由自研匹配器处理：`*` 不跨目录，`**` 跨目录，`?` 匹配单个字符。不用 `fnmatch`，因为它的 `*` 会跨目录。
2. **固定内容**：总是输出 overview。术语只返回任务中直接出现的词，以及它们的 `_Avoid_` 别名。
3. **候选优先级**：显式条目（`--entry`）或精确符号 → scope 路径匹配 → 标题、标签、术语匹配。
4. **中文匹配**：
   - 词表由三部分组成：词汇表术语及别名、所有 `tags`、条目标题按标点和空白切出的词组。
   - 任务文本先规范化（ASCII 转小写、全角转半角），再从左到右做贪心最长匹配，每个词只计一次。
   - 不切二元字串，未知的短词不加分。
5. **排序**：按元组排序，结果完全确定：
   1. 优先级层；
   2. 路径具体程度，即匹配的 glob 中字面段的数量；
   3. 独立信号数；
   4. 文件路径。
6. **扩展与放弃提醒**：
   - 按 `related` 对选中条目扩展一层。
   - 命中 rejected 决策时，只展示理由部分。
   - 选中的 decision 有“放弃过的做法”时，展示每项的做法、放弃原因和重新考虑的条件。
   - 任务文本命中某项放弃过的做法时（按第 4 步的词组匹配，例如“永久删除”），即使 scope 没有命中，也单列一条“曾放弃”提醒。
7. **共享仓**：只读取配置的那一层，核验实际检出的身份，并展示检出目录、HEAD 和未提交状态。
8. **正文检索**：首版默认不检索正文。阶段 1 用真实查询集对比有、无正文检索时的召回，再决定默认值。

**预算**

- 默认 6,000 个 Unicode 字符：overview 不超过 600，术语不超过 400，导航不超过 600，其余留给条目。
- 条目按空行分段，只能整条放入。放不下时改为索引行，**禁止截断否定条件**。
- 索引也放不下时，显示剩余数量和再次查询的方法。

**缓存**：输入为 HEAD，以及各知识文件的路径、大小和修改时间；工作区中有改动的文件另计内容哈希，使未提交的知识改动能立即被检索到。读取缓存时不写入；缓存缺失时在内存中计算。

### R3 漂移提示

- 每个仓库批量读取一次提交图，计算 `verified.commit..HEAD` 中命中 scope 的提交数。未提交的改动单独列出。
- 基线不存在，或历史不足（如浅克隆）时，显示“未知”，不显示 0。
- 这个数字只是背景信号，表示“相关代码动过”，不代表结论已经失真，也不会自动改变任何状态。
- 性能目标：500 条知识、5 个共享仓时，冷查询约 1 秒，热查询约 200 毫秒，需要实测确认。

### R4 输出示例

```markdown
# 任务：修改新会话语言路由

项目：核心服务管理业务状态，与 common 共用协议。

## 建会话前确定语言
创建事务前判定，随会话写入独立字段……
来源：Issue #146 · 核实基线之后有 N 个相关提交，另有未提交修改
→ decisions/2026-10-13-conversation-language.md

## 继续阅读
- 语言回写规则 → rules/conversation-language-update.md
- 代理侧弱输入边界 → agent-py:rules/language-evidence.md（检出：../cw2-live-chat-agent-py @ 4f2c… 无未提交修改）

## 相关提交
（按本次路径筛选的提交标题与 Issue 链接）
```

不再输出回执、复核队列、11 类覆盖表和空字段。这些诊断信息移到 `tw audit`。

### R5 钩子注入（不进首版）

按路径触发的注入（Trellis 0.7 的做法：Claude Code 在工具调用之后注入，Codex 在 apply_patch 之前注入）放到阶段 5 之后再评估。前提是真实任务回放的数据表明 brief 的召回不够。

---

## W 写入与校验

### W1 直接编辑

- 代理像改代码一样编辑 Markdown，与代码在同一个 PR 中评审。
- `tw new rule|decision|lesson --slug --title --scope --source [--verified-at-head]` 用于生成骨架：
  - `scope` 和 `source` 必填；
  - 只有作者明确声明已在当前 HEAD 核对过（`--verified-at-head`），才写入 `verified`；
  - 同名文件已存在时拒绝。
- 普通的知识编辑不需要事务、锁或计划令牌。

### W2 `tw check`

`tw check` 不写入任何文件，也不执行测试。它可以检查工作区、暂存区，或者与 `--base` 指定的分支对比。CI 也可以运行。

**错误**

- 文件头无法解析、有重复或未知的字段、必填项为空、残留占位符（如 `__REPLACE__`）。
- rule 或 lesson 缺少 `verified`。
- 文件名、日期、状态、提交的格式不合法；路径越界，或经过不允许的符号链接。
- rule 或 lesson 的 scope 在本仓匹配不到任何文件；已配置的跨仓引用明确不存在。
- 守护测试的引用无法解析，或检查名未配置。
- “放弃过的做法”中有一项缺少放弃原因、来源或关键词。
- 内部链接缺失。
- 同一份原文被登记了两个正文归属。
- 出现 L2 列出的忽略规则问题。
- 存在旧的 `.codestable/`、`.team-workflow.json` 或 `.team-workflow/`。这条用来提示尚未迁移，或防止旧系统复活，见 T6。
- 超过篇幅上限。

**警告**

- 外部仓库读不到；核实提交不可用；浅克隆导致历史不足。
- 已接受但尚未实现的 decision，其 scope 匹配不到文件。
- scope 范围过宽；scope 内的代码已有变化。
- 疑似重复；来源失效；没有守护测试。
- 一次性的测试计数、工具版本、行号锚点、空泛的填充句。

**不做的判断**：测试是否覆盖了全部结论、结论是否成立、知识是否与任务相关。这类语义问题只提示“需人工核实”，交给评审和独立验收。

### W3 `tw audit`

- 汇总以下内容：来源可用性、变化热点、疑似重复、失效链接、共享归属、超出预算的条目、忽略规则、`local/` 体积。
- 加 `--links` 时才在线检查外部链接；在线访问失败和内容不存在分开报告。
- 报告明确区分三种状态：结构有效、证据可用、业务结论尚未判定。
- 每周质量复盘时引用 audit 的结果。原 cs-analysis 中有效的方法并入这里。

### W4 删除的写入机制

以下机制全部删除：

- `learn`；`template`（由 `new` 取代）；
- 计划文件与令牌、写锁、事务日志、revision 乐观锁；
- `consolidate`、`receipt-check`、`task-files`；
- 主题治理（`topics list/suggest/update`）；
- 跨文件的取代链；被取代的内容改为写进现行决策的“放弃过的做法”（K1）；
- `learning.schema.json`，以及复制到每个项目的 schema。

---

## T 团队流程衔接

### T1 稳定的任务身份

- 任务身份就是任务记录中的 `id`，创建后不改名：
  - 平台任务的身份是 Issue 地址，任务块保存在 Issue 中；
  - 其他任务由创建者给定稳定的编号。
  - 改动任务内容、重复运行 `prepare`，都不改变身份。
- 本地材料放在 `local/tasks/<可读名称>-<身份哈希前 8 位>/`：
  - 可读名称取自身份，Issue 为 `owner-repo-编号`；
  - 哈希取自完整身份，名称相近的仓库、只有大小写不同的编号，不会落进同一目录。
- 多个 Issue 共用一次实现时，每个 Issue 仍是自己的任务：用 `run --with-task` 共用一次检查和一份方案，分别验收；知识改动只写一次（T4）。
- 跨仓任务由主仓持有联合身份，即联合清单的 `task_id` 与 `joint`。参与仓的任务用 `parent` 引用它，联合核查只认这一个身份。
- 续接按身份进行：平台任务用 Issue 地址，其他任务用同一份任务文件或 `prepare` 生成的上下文；`status --format text` 给出下一条命令。共享材料（Issue 评论、交接、收尾说明）都带上身份。
- 任务结果写在 Issue 的收尾说明或 PR 中。纯离线、未提交的任务只能在本机恢复，不能宣称支持团队交接或完整的周复盘。
- **放弃过的做法**：v4 规定由 `team prepare` 生成 `<仓库别名>/<YYYYMMDD>-<slug>` 形式的身份，Issue 与 PR 只作关联项。
  - 放弃原因：现有任务编号已经稳定，可以续接；平台任务直接以 Issue 地址为身份即可。另起一套生成的身份，还要同时维护它与 Issue 的映射。阶段 2 评审后由你确认保留现有做法（v4.1）。
  - 可重新考虑的条件：出现大量没有 Issue、又需要多人交接的离线任务。

### T2 配置合并

`.team-workflow.json` 并入 `config.json`（L1）。项目数据只有一个 `data_version`，本地证据的格式跟随它变化，不再单独设证据的 schema 版本。

### T3 执行绑定的目录契约

现行实现中，`common.py` 的 `reserved()` 把 `.team-workflow` 和 `.codestable` 整个排除在快照之外，并拒绝已跟踪的 `.team-workflow/` 文件；`validation.py` 默认按内容绑定。新布局的契约如下：

| 路径 | 是否参与执行绑定 |
| --- | --- |
| 仓库中的其他文件（已跟踪的，以及未被忽略的未跟踪文件） | 参与 |
| `.tw/config.json` | 按检查分别绑定各自的配置项，沿用现在对 `.team-workflow.json` 的做法 |
| `.tw/local/**` | 不参与 |
| 知识正文（`overview.md`、`glossary.md`、`rules/`、`decisions/`、`lessons/`） | 不参与；在 `inputs` 中显式声明为构建输入的除外 |

- 按提交绑定的检查（`revision_sensitive`）照常绑定 HEAD，所以提交知识仍会让这类检查过期。这是设计意图，不是缺陷。目标是：只提交知识时，按内容绑定的检查不失效。
- 实现时要同时修改文件快照、变更范围计算和执行绑定三处，不能只改目录常量。

### T4 交付时的知识处置

最终的 `verify` 要求交付报告满足以下两者之一：

- 列出本分支改动的知识文件（工具从 git 差异中列出），并且 `tw check` 通过；
- 写明不需要改知识的理由。

知识是否相关、是否充分，由评审人判断。删除 `knowledge`、`knowledge-template`、收尾简报和 CS 记录核对。

### T5 流程节点与知识

- 缺陷保护模板增加“教训”一项：写明 lesson 的路径和守护测试，或者说明为什么没有可复用的教训。
- 方案评审中出现 ADR 级的选择，批准后写成 decision。如果已经有对应的原文，就改原文（K5）。
- 业务验收改变了行为契约时，改写 rule。

### T6 删除的桥接，防止旧系统复活

**删除**：

- `knowledge.py`、capability 协商、`contract_version`、`workflow_acceptances`、回执；
- `check_cs_knowledge.py`、`check_cs_delivery.py`，以及 `check_parallel.py` 中与 CS 相关的部分；
- CI 中克隆 CS 默认分支的步骤。

**防止旧系统复活**：Trellis 在 live-chat agent 仓出过这样的事——系统被删除后，另一个分支运行了 init，自动提交又把它带回了主线。对策：

- 发布说明要求卸载 `cs`、`cs-analysis`；
- 整体替换托管的指引块；
- `tw check` 发现旧目录时报错；
- 新运行时不提供任何会创建旧目录的路径。

### T7 第二阶段：流程简化方向（本次只列方向）

| 方向 | 证据 |
| --- | --- |
| 小改动分级：低风险、只需单项检查的改动走轻量路径 | 一个 +18/−5 的改动产生了 10 个请求、39 个文件 |
| 减少形式绑定带来的重跑：环境身份、用例登记名、评论作者 | 两轮全量重跑由规则触发；40ffdae 已取消“评论作者必须是评审人” |
| `tw team status` 显示当前步骤和下一条命令 | 用户反馈“没有步骤感”；现在的 `status --format text` 在缺少任务输入时直接报错退出 |
| 写明 Issue 的关闭规则 | 用户反馈“不清楚 Issue 该不该关” |
| 两位真实成员试点 | 从 0.3.0 起从未执行；6 个 rc 版本都没有达到推广条件 |
| 按 C 节重新组织命令，全局参数归入子命令（v4.1 由阶段 2 移入） | 阶段 2 评审 F6：`tw team` 仍整体转发原有的约 50 个全局参数 |

---

## C 命令面

> v4.1：本节的命令重新分组与全局参数收敛移到 T7，与流程简化一并评审。阶段 2 只把团队命令统一为 `tw team <原命令名>`，原命令名和参数保持不变；知识命令（init、brief、read、new、check、audit、cache、version）已按本节实现。

全局参数只保留 `--root` 和可重复的 `--repository 别名=路径`，其余参数都归到各自的子命令下。现在 TW 有 54 个全局参数。

| 命令 | 作用 |
| --- | --- |
| `tw init [--guidance] [--apply]` | 预览或建立最小布局与指引块 |
| `tw brief --task [--path] [--symbol] [--entry] [--tag] [--budget] [--index]` | 读取知识 |
| `tw read <路径或文档ID> [--section] [--online]`、`tw read --list` | 读取原文或条目全文 |
| `tw new rule\|decision\|lesson --slug --title --scope --source [--verified-at-head]` | 生成骨架 |
| `tw check [--cached\|--base]`、`tw audit [--links] [--since]` | 结构检查、健康报告 |
| `tw cache --rebuild\|--clear` | 只处理可以重建的缓存 |
| `tw version [--check-install]` | 版本；检查两个技能是否来自同一个发行、文件是否被改动、是否有同名技能 |
| `tw team …` | 团队功能，见下表 |
| `tw clean`、`tw schema` | 维护 |

**TW 现有 29 个子命令的去向**

| 现有命令 | 去向 |
| --- | --- |
| project | 并入 `check`、`audit`、`version --check-install` |
| snapshot | `team run --capture-only`（只捕获，不执行） |
| run | `team run` |
| brief | 并入 `brief` |
| knowledge、knowledge-template | 删除 |
| review-template、delivery-template | `team review --template`、`team report --template` |
| verify、aggregate、evidence | `team verify`、`team aggregate`、`team evidence` |
| prepare、resume | 合并为 `team prepare`（新建，或按身份续接） |
| handoff、task-export | `team handoff`、`team handoff --task-only` |
| progress、status | `team progress`、`team status` |
| import-result | `team import` |
| agents | `team agents`，仍为可选 |
| design-draft、design-diff、approval-draft | `team plan --draft\|--diff`、`team approve --draft` |
| issue-draft | `team draft --kind issue` |
| cleanup、guidance、metrics | `clean`、`init --guidance`、`team metrics` |
| adopt | 删除：旧证据不用于新的验收 |
| version、schema | 保留 |

**CS 现有命令的去向**

- `brief`、`documents list/read` 合并为 `brief` 和 `read`。
- `doctor`、`drift`、`audit`、`status` 并入 `check` 和 `audit`。
- `template` 由 `new` 取代；`reindex` 改为 `cache --rebuild`。
- `bootstrap` 中的初始化改为 `init`；重建功能删除。
- 删除 `learn`、`receipt-check`、`consolidate`、`task-files`、`topics *`。
- cs-analysis 不再保留独立入口。

本阶段只改变命令的组织方式，不降低现有的批准和业务验收要求。

---

## B 迁移（代理整理，不写脚本）

### B1 原则

- 项目默认展示最新的设计，放弃过的做法按 K1 保留。旧的 `.codestable/`、`.team-workflow.json`、`.team-workflow/` 只是迁移素材，新运行时不读取。
- 迁移由代理按迁移指南完成，用户负责指挥和确认。
- 不提供盘点或转换脚本，不读取旧格式，也不默认查 git 历史（查历史见 B5）。
- 回退方式：撤销迁移 PR。已跟踪的旧内容都能从 git 历史取回。

### B2 迁移指南

迁移指南写在 `team-knowledge/references/migration.md`，不超过 3,000 字符。

1. **准备**：
   - 在新分支、干净的工作区上操作。
   - 在途的团队任务先完成，或明确放弃。
   - 本仓所在的产品组已经换装新技能（B4）。
2. **初始化**：
   - 运行 `tw init`，建立最小布局。
   - 代理把 `.team-workflow.json` 的检查配置整理进 `config.json`，并把原文登记整理进 `documents`。
   - 用 `tw check` 校验。
3. **整理知识**：
   - 代理直接阅读旧知识：当前卡片、PROJECT.md、分类摘要、documents 登记。旧格式都是 Markdown 或 JSON，可以直接读。
   - 只保留现在仍然成立、对未来有用的内容。逐条按 B3 核实后，用新格式和新的表述写成 rule、decision、lesson、glossary、overview。
   - 历史决策按现行设计重新组织语言。
   - 旧库中被取代的卡片及其取代理由，以及与现行代码矛盾、但曾经被接受过的结论（例如 brand purge），整理进对应决策的“放弃过的做法”，不丢弃。
   - 跨仓重复的内容，归到契约提供方的仓库。
4. **清理旧内容**：
   - 已跟踪的 `.codestable/` 和 `.team-workflow.json` 直接删除。
   - 未跟踪的旧 `.team-workflow/` 证据，以及 `.codestable/cache`、`local.json`：先列出体积，征得用户同意后再删除；用户也可以自行另存。
   - 本机的跨仓映射写入 `.tw/local/repositories.json`。
5. **收尾**：
   - 运行 `tw init --guidance --apply` 更新指引块。
   - 删除根 `.gitignore` 中的旧条目。
   - 确认 `tw check` 没有错误。
6. **提交 PR**：正文附“迁移说明”，包括：
   - 保留、改写、删除的数量，以及按类别归纳的理由；
   - 待用户确认的问题；
   - 未能核实、因而没有迁入的内容清单，附旧路径。
   
   用户确认后合并。

### B3 核实要求

| 层次 | 范围 | 做法 | 未通过时 |
| --- | --- | --- | --- |
| 代码核对 | 全部迁入的条目 | 代理阅读真实入口和关键路径，核对路径、符号、常量、错误码、协议字段、表结构等。路径存在不算支持 | 不迁入 |
| 真实入口核对 | 涉及 authorization、persistence、concurrency、messaging、public-contract、cross-service 的行为结论 | 按业务验收标准运行守护测试或真实接口，以独立确定的预期核对结果 | 不迁入，列入迁移说明 |
| 用户确认 | 业务规则与决策；无法执行验证的结论 | 在迁移 PR 中逐条确认，确认记录写入 `source` | 不迁入，列入迁移说明 |
| 独立复核 | 试点仓的全部条目；后续批次中的全部高风险条目，以及其余条目至少 20% 的抽样 | 由未参与迁移的代理对照代码复核 | 退回修改 |

**代理核实要点**（可以直接作为提示词）：

> 1. 逐条阅读，不继承 current、accepted、PASS 这类标签。
> 2. 分别判断“应当怎样”和“当前怎样”；实现上的差异不能自动推翻已经确认的要求。
> 3. 每条结论都要记录支持证据、反证和未核实的部分。
> 4. 不编造测试通过、批准人或事故日期。
> 5. 不恢复旧的控制层、旧字段或已被拒绝的方案。

### B4 多仓顺序与换装

- 多仓产品（如 live-chat）以组为单位换装：全员卸载 `cs`、`cs-analysis`，安装同一个新版本 tag。
- 组内按“契约提供方 → 核心实现 → 消费者”的顺序逐仓迁移，每个仓一个 PR。
- 尚未迁移的仓，在 brief 里显示为“未迁移”，`tw check` 也会提示旧目录的存在。

### B5 按需找回历史教训（由用户指挥）

- 不是默认步骤，也不提供工具。用户提出需要时，代理按 `team-knowledge/references/lessons-from-history.md` 的要点执行（不超过 1,500 字符）。
- 来源：
  - 旧知识的 git 历史（`git log --diff-filter=D -- .codestable`、`git show <提交>^:<路径>`）；
  - Issue 和 PR；
  - 已有的复盘文件。
- 只保留现在仍可能再犯的失败机制，写成 lesson，尽量绑定守护测试。由用户确认后提交。

**目前唯一计划的找回：agent-py 的 Agent Native 开发教训**

- 目标：写入 agent-py 的 `.tw/lessons/`。
- 来源：
  - agent-py 自己的 `.codestable/wiki/history-review/`：从 337 条记录中归纳出 27 组；
  - agent-py 9 月 5 日重建前的知识（`334cc9d^`）；
  - agent 仓 9 月 5 日重建前的知识（`cc2278f8^`）；
  - agent 仓已删除的 Trellis spec（在 `ef6f3e3a` 中删除，其中 graph-patterns.md 有 19 个场景小节）。
- 迁移规则：agent 仓的教训如果适用于 agent-py 的实现，就迁入 agent-py，并在正文中写明适用条件。不适用的内容不迁入。
- 作为阶段 3 中 agent-py 迁移之后的一项独立任务，由你指挥执行。

### B6 每仓验收

1. `tw check` 没有错误，旧目录已全部移除。
2. 用最近的真实任务回放 brief（例如 core 的 #126–#152）。预期条目由独立代理事先确定，回放时这些条目要出现。
3. 已知冲突已经处置，例如 common 的 brand purge。
4. 迁移说明完整：未迁入的内容都已列出，用户确认的问题都有记录。
5. 高风险结论已经通过真实入口核对；无法运行的场景明确保留为未完成。

### B7 工作量（以“代理时长”和“人工时长”为单位）

| 项 | 估算 | 依据 |
| --- | --- | --- |
| 小服务迁移 | 每仓 0.5–1 代理小时 | 9 月 5 日重建时每仓约 25–30 分钟，但当时字段是机械填写的；新流程需要更多阅读 |
| agent-py、core、common | 每仓 0.5–1 代理日 | agent-py 的历史复核约 1.5 小时，覆盖 337 条记录；core 当前有 52 张卡 |
| 独立复核 | 约为迁移时长的 30–50% | 按 B3 的范围 |
| 真实入口核对 | 按高风险结论的数量计算，需要数据库等环境 | 迁移时再估 |
| 用户确认 | 约 58 条决策和需求，每条 2–5 分钟，合计 2–5 人工小时 | 项目审计统计 |
| agent-py 历史教训找回 | 由你决定范围 | B5 |

---

## M 仓库合并与发布

### M1 合并后的目录树

```text
skills/
  team-workflow/            # 团队入口：SKILL.md、references、templates
  team-knowledge/
    SKILL.md
    MANIFEST.json           # 发行编号与文件哈希
    scripts/tw.py
    scripts/tw_runtime/     # 唯一的运行时模块：知识、检索、检查、团队
    references/             # 写作规范与正反例、迁移指南、找回历史教训
  matt-*/                   # 15 个复用的技能
tests/                      # 单元、CLI、安装、完整任务场景、真实查询回放
scripts/                    # 测试、发行检查、打包、上游校验
docs/                       # README、设计、安装、成员操作说明、验收、验证记录
upstream/matt.lock.json、matt.patch
plugin.json、.claude-plugin/、LICENSE、licenses/
.tw/                        # 本仓自己的知识，入库，用于自用验证
```

- 运行时只有 `team-knowledge/scripts/` 这一份。知识技能可以单独使用。
- 团队技能依赖知识技能。只装了团队技能时，在执行任何写入之前就报告缺少依赖。
- `tw version --check-install` 检查两个技能的 MANIFEST 是否属于同一个发行编号、文件是否被改动（保留现有的 `tool-modified` 检测），以及是否存在同名技能。

### M2 删除清单

**CS 中不迁入的部分**：

- `scripts/build_runtime.py`、`skills/cs/runtime_src/`，以及生成的 `skills/cs/scripts/cs_knowledge.py`（这三者构成了双份源码）；
- `bootstrap.py` 的重建功能；
- `skills/cs-analysis/`；
- 项目脚手架资产（`assets/project/.codestable` 下 11 类的 README/INDEX、`learning.schema.json` 等）；
- `docs/rebuild.md`、`storage.md`、`parallel-development.md`、`drift.md`、`governance-acceptance.md`。其中仍需要的内容写进新文档。

**TW 中删除的部分**：

- `skills/team-workflow/scripts/knowledge.py`；
- `scripts/check_cs_knowledge.py`、`check_cs_delivery.py`；
- `adopt.py`、`versioning.py`；
- 两仓重复的 `lint_undefined_names.py`，只保留一份；
- `.gitignore` 中的 `.codestable/` 和 `.team-workflow/` 两行。本仓的知识改为入库 `.tw/`。

**需要改写的**：README、AGENTS.md、`docs/design.md`、`docs/install.md`，以及全部技能中的接入链接。

**测试**：先把旧测试覆盖的行为风险迁入新用例，再删除旧测试；不按旧文件名批量删除。

### M3 测试与 CI

- 统一使用 unittest。
- 保留检索评测和失真反例，例如 brand purge 这类“路径存在、结论却已被否定”的情况。
- 新增用例：
  - `init` 与托管指引块；
  - `check` 识别旧目录残留和忽略规则问题；
  - 单技能安装；
  - 跨仓与 worktree 的依赖核验；
  - 离线运行；
  - 篇幅预算。
- **真实查询回放集**：从 core 的 #126–#152 等任务中挑选查询，由独立代理确定预期条目，作为召回回归。目前唯一的检索指标只来自 5 条合成查询。
- **迁移指南试用**：由未参与编写的代理，在 gateway 和 agent-py 的副本上按指南完成迁移，检查指南能否独立执行。
- CI 不再克隆 CS 默认分支，直接测试同一份发行源码。在 macOS 和 Linux 上，用 Python 3.10 和当前支持的最新版本验证。
- 阶段 1 在 Claude Code、Codex、Cursor 上实测：技能发现、显式调用、自动调用，以及缺少依赖时的提示。

### M4 MATT 复用的修正

- **lock 与核对**：lock 如实记录来源，实际是 `main@b0618bc`，不能写成 1.3.1。`check_release.py` 目前只核对文件哈希，需要补上版本号与提交的对应关系。
- **patch 遗漏**：
  - `matt-code-review/SKILL.md:34`：悬空的 tracker doc 引用。
  - `matt-codebase-design/DESIGN-IT-TWICE.md:30`：直接引用了 GLOSSARY.md。
  - `matt-domain-modeling/SKILL.md:15、29、45、67` 和 `ADR-FORMAT.md:3、5、27`：写死了根目录路径，并按最大号加 1 编号。改为通过 `team-knowledge`、按原文优先规则（K5）读写：已有登记原文的改原文；没有的写入 `.tw/glossary.md` 或 `decisions/<日期>-<slug>.md`。
- **调用设置**：统一 Claude Code 与 Codex 的隐式调用设置（`disable-model-invocation` 与 `allow_implicit_invocation`）。团队技能只允许显式调用，知识技能允许自动调用，并按 M3 实测。
- **上游原文**：保留上游原文和许可，补丁保持可逆。

### M5 安装、发布与版本

- **发行与安装**：
  - 发行使用不可变的 tag 和固定的发行包；main 只做开发和验证，不再“推送 main 即发布”。
  - 本机 skills CLI 1.7.2 的源码已确认支持 `owner/repo#v1.0.0` 这类引用，安装说明改为固定 tag。
  - 这个 CLI 不会根据 Markdown 链接自动补装依赖，所以仍用 `--skill '*'` 一次装齐，再由 `tw version --check-install` 核对。
- **升级**：显式选择版本，不自动提交。
- **版本轴只保留两个**：软件发行版本，以及项目的 `data_version`。
  - 没有破坏性变化时，`data_version` 不变。
  - 有破坏性变化时，`data_version` 加一，并按 B 的方式由代理迁移。
  - 旧运行时遇到未来的格式时拒绝写入；新运行时不会静默修改项目。
- **正式版**：必须完成两位真实成员的试点。

### M6 指令篇幅预算与删减机制

| 对象 | 上限（Unicode 字符） |
| --- | --- |
| `team-workflow/SKILL.md` | 3,000 |
| `team-knowledge/SKILL.md` | 2,500 |
| 托管指针 | 400 |
| 每个技能的 MATT 接入补丁 | 200 |
| 单份必要参考（含迁移指南） | 3,000 |
| 首次必读链总量 | 8,000（现在约 129KB） |
| overview | 1,200 |
| 普通条目 | 3,000 |

- 发行检查按 Unicode 字符统计，并检查声明的必读关系，超限即失败。MATT 原文按所选方法读取，不计入统一的开工必读链。
- 每条新增的强制规则都必须对应真实的失败案例或验收要求。
- 发布评审时同时检查三类规则：重复的、已由代码保证的、已失效的。
- 超出预算时，通过合并、删除或按需路由解决，不靠追加例外来扩大上限。
- 篇幅预算本身不能证明负担下降，阶段 4 要用真实任务实测阅读量、命令数和耗时。

---

## V 验收与回归

### V1 指标（基线 → 目标）

| 指标 | 基线 | 目标 |
| --- | --- | --- |
| 小服务入库的脚手架文件 | 约 23 个 | 3 个 |
| 全部项目入库文件中脚手架的占比 | 32.5% | 低于 10% |
| brief 默认篇幅 | 14–82KB | 不超过 6,000 字符 |
| 写一条知识需要的工具步骤 | 5 步，外加手写 JSON | 编辑 Markdown，再运行 `tw check` |
| 首次必读的指令 | 约 129KB | 不超过 8,000 字符 |
| 任务身份 / 版本轴 / 运行时源码 | 3 套 / 至少 8 个 / 2 份 | 1 套 / 2 个 / 1 份 |
| 只提交知识就导致按内容绑定的检查失效 | 在旧版本中发生过 | 0 |
| 一次团队任务的补救重试与手写 JSON | 补救重试至少 15 次，手写 JSON 25 段 | 实测下降，阶段 4 记录 |
| 非方案作者的成员写的知识 | 0 | 试点中每人至少 1 条 |
| 真实查询回放的召回 | 没有基线 | 阶段 1 建立基线，此后不得下降 |

### V2 真实入口验收

- 每个阶段都用真实仓库、真实任务走一遍，并保留证据（见 I）。
- 新的业务行为先在真实入口验证一次，再沉淀为仓内的回归用例；无法自动化的部分明确列为“仍需手动”。

### V3 独立验收

- 涉及持久化、公开契约的阶段，由未参与实现的代理在隔离工作区中试用。
- 迁移结果按 B3 复核。
- 两位真实成员的双向接续不能由代理替代。
- 缺少真实入口证据、缺少独立验收，或者回归没有实际运行，一律报告为未完成。

---

## I 实施任务

| 阶段 | 交付 | 真实入口验收 | 独立验收 | 依赖 |
| --- | --- | --- | --- | --- |
| 0 冻结设计 | N1–N8 已确认；批准方案正文；字段表、命令参数、读写边界、删除清单定稿 | — | 方案评审人 | — |
| 1 知识运行时 | `init/brief/read/new/check/audit/cache/version`；格式与预算；写作规范与正反例；成员操作说明；迁移指南与找回教训要点；真实查询回放集与召回基线；三个客户端的调用实测 | 在 gateway 和 core 的副本上读写，能发现占位符和失效引用；查询不写入任何文件 | 未参与实现的代理在隔离工作区试用 | 0 |
| 2 合并与团队衔接 | 合仓；把 TW 脚本迁入运行时；删除桥接；合并配置；建立 `local/` 布局；落实 T3 的执行绑定契约；稳定的任务身份（v4.1：任务编号加可读目录）；适配 live-chat 的 worktree 依赖工具（`script/worktree/skills/livechat-worktree-dependency/scripts/worktree.py`，目前只处理两份旧映射路径） | 在本仓用新流程完成一个真实任务；只提交知识时，按内容绑定的检查不失效；新布局下 worktree 依赖解析正确 | 独立验收者核对原始结果 | 1 |
| 3 迁移试点 | 按 B 由代理迁移 agent-py、core、common；agent-py 迁移之后，由你指挥找回历史教训（B5） | brand purge 冲突被识别并改写；brief 回放能取到预期条目；迁移说明完整 | 按 B3 独立复核；用户确认语义 | 1、2、候选发行包 |
| 4 成员试点与发行 | tag 发行；安装、升级、回退 | 两位成员在同一任务中双向接续、检索和交付；实测阅读量、命令数和耗时 | 两位真实成员 | 3 |
| 5 推广与流程简化 | 其余仓按组由代理迁移；T7 另行评审，包括 C 节的命令重新分组 | 每组按 B6 验收 | 用户与团队的业务验收 | 4 |

---

## X 风险与对策

| 风险 | 对策 |
| --- | --- |
| 代理迁移时遗漏或误删有效知识 | 迁移说明列出所有未迁入的内容；独立复核；用户确认；撤销 PR 即可回退，旧内容可从 git 取回 |
| 未跟踪的旧证据被误删 | 删除前列出体积，并征得用户同意 |
| 新格式又被形式填充 | 必填项少；`verified` 不自动填写；正反例；评审；audit 识别空泛的填充句 |
| 漏召回 | 真实查询回放集纳入回归；glob 精确匹配；索引行兜底；用数据决定是否开启正文检索 |
| 读到错误的依赖代码 | 共享仓展示检出目录、HEAD 和未提交状态；缺少映射时只提示，不猜测；适配 worktree 工具 |
| 本地内容误提交 | 嵌套 `.gitignore`、`check`、发行排除；工具不执行 git add |
| 旧系统复活 | 卸载旧技能；替换指引块；`check` 对旧目录报错；按组换装 |
| 名称冲突 | 使用 `.tw/` 并加 `config.format` 标识，遇到其他工具的同名目录时拒绝接管；`--check-install` 检查同名技能 |
| 重复踩坑、重复提出已被放弃的方案 | 决策保留“放弃过的做法”，写明原因和重新考虑的条件；明确拒绝的记为 rejected；lesson 不随代码变化删除；brief 在任务涉及相关范围或命中相关词组时主动提醒 |
| 指令再次膨胀、规则只增不删 | 发行检查强制预算；新规则必须对应真实案例 |
| 独立验收流于形式 | 由未参与实现的人执行，并保留原始证据；真实成员试点不能替代 |

---

## 附录 A 参考项目借鉴对照

| 借鉴 | 来源 | 本方案落点 |
| --- | --- | --- |
| 单根目录、嵌套 .gitignore、只写白名单路径、不自动提交 | Trellis（有 548 个文件误提交、删除后复活两起事故）；ECC Memory Vault | L1、L2、T6 |
| 会话入口只放索引，正文按需读取，设硬预算 | Trellis #154 与 0.7；ECC 8,000 字符上限 | R1、R2 |
| frontmatter 中用 `paths` glob 按路径匹配 | Trellis 0.7 | K2 `scope`、R2 |
| 代理写入需经人审；单一正文归属 | ECC Memory Vault、living-docs | P1、P5 |
| GLOSSARY 格式、ADR 三条件、记录被拒的需求 | MATT | K1、K5 |
| 用规范化的 git remote 作为项目身份 | ECC | L1 `project.id` |
| **改进而非照搬** | | |
| ADR 顺序编号改为日期加 slug | MATT 现行做法是取最大号加 1，#799 中并行分支撞号 | K2 |
| 被取代的决策不单独成文件，而是移入现行决策的“放弃过的做法”，保留原因和重新考虑的条件 | MATT 用 `superseded by` 和被否决的备选防止方案被重复提出，但 #822 中失效与现行的 ADR 混在一起，#1114 只追加修订导致原文结论过时；ECC 用 delete-zone 防止删除的内容复活 | K1、R2 第 6 步、W2 |
| 教训持续保留，用 break-loop 式的缺陷复盘写入 | Trellis `break-loop` 在调试后把教训写回 spec，但缺少状态与整理，矛盾不断累积（讨论 #371） | K1、K3、T5 |
| **不借鉴** | | |
| 按主题的大文件只增不减、行号锚点、整文件注入 | Trellis（单个文件 3,993 行，一次注入 455KB） | K1 原子条目、P2 |
| 按开发者分的 journal、入库的共享索引 | Trellis #284、#415 | 任务记录不入库，索引放 local |
| 钩子自动观察、后台模型自动写入、数值置信度与衰减 | ECC | 非目标 |
| 在个人目录中保存项目知识；按 TTL 删除已评审的知识 | ECC | 知识入库，失效时改写或删除 |
| MATT 分散在根目录的文件布局 | MATT | 单一根目录、原文优先，路径交给知识技能 |

## 附录 B 调研来源

- **子代理报告**：
  - Trellis：本地 0.6.5，上游 0.7.0-beta.4；
  - ECC/MATT：上游 HEAD；
  - 两仓开发问题：git 历史，以及已删除的会话审计文档；
  - 已接入项目审计：15 个项目、1,203 个入库文件、12 个会话。
- **Codex**：
  - 独立方案；
  - 详细设计：D1–D9 评审、格式、算法、命令映射、发布；
  - 两批补查：会话摩擦、MATT 遗留问题、skills CLI 能力、历史数据；
  - 对 v1 的对抗式评审。
- **外部链接**：[mindfold-ai/Trellis](https://github.com/mindfold-ai/Trellis)、[affaan-m/ECC](https://github.com/affaan-m/ECC)、[mattpocock/skills](https://github.com/mattpocock/skills)、[vercel-labs/skills](https://github.com/vercel-labs/skills)、[wbcli 文档](https://www.wbcli.com/docs/getting-started)、[KEEL](https://skillselion.com/skills/vzwjustin/KEEL/plugins/keel-companion-plugin)、[blader/baton](https://cdn.jsdelivr.net/gh/blader/baton@main/SKILL.md)。

## 附录 C 修订对照

**v1 → v2（Codex 对抗式评审）**

| 评审意见 | 修订 |
| --- | --- |
| 阻断：沿用目录名与现有运行时冲突 | N1 改为新目录 `.tw/`；T3 写明执行绑定的目录契约；L1 补充 `context` |
| 阻断：仓库身份证明不了依赖正确 | K4、R2 第 7 条展示检出目录、HEAD 和未提交状态；阶段 2 适配 worktree 工具 |
| 阻断：核实标准与独立验收不一致 | B3 统一核实层次，并写明全量与抽样的边界；未核实的内容不迁入 |
| 阻断：阶段依赖与切换窗口 | I 中迁移试点依赖阶段 2 和候选发行包；B4 规定按组换装 |
| 阻断：恢复与回退 | v3 改由代理迁移后，回退方式为撤销 PR；未跟踪的证据须经用户同意才能删除 |
| 安装入口 | R1 写明调用方式；M1 增加 MANIFEST 与 `--check-install`；M3 把客户端实测提前到阶段 1 |
| 形式门槛 | W1 中 `new` 必须填写 scope 和 source，`verified` 不自动填写；W2 中未实现的决策只警告；T4 的相关性交给评审判断 |
| 检索算法 | R2 定义了 glob 语法、词表与最长匹配、排序元组和缓存输入；是否检索正文由数据决定 |
| 任务身份漂移 | T1 改为生成后不变、带仓库范围的身份 |
| 证据与估算 | P3 改正了“HEAD 导致失效”的表述；B7 统一了单位 |
| 字段与命令矛盾 | 保留 `symbols`，删除 `paths` 和 `scopes`；新增 `--entry`；区分 `run` 与 `--capture-only`；`adopt` 改为删除 |
| 原文归属与成员说明 | K5 规定原文优先；M4 按原文优先改造 MATT；K3 增加成员操作说明 |

**v2 → v3（你的意见）**

| 意见 | 修订 |
| --- | --- |
| 只有 agent-py 值得找回 Agent Native 教训，agent 仓的教训可以迁入 agent-py | B5 只计划 agent-py 一项，并列出具体来源与迁入规则；I 阶段 3 中由你指挥执行 |
| 从 git 找回教训不应强制，由用户按需指挥 | N4 确认；删除 `--history` 和“已清空过的仓默认读历史”；B5 改为按需的要点说明 |
| 项目只管最新设计；迁移由代理整理，不提供脚本 | N7 确认；删除 `tw rebuild` 整套命令、旧格式读取、暂存与回退日志；B 改为迁移指南；N8 推导出不保存取代链和演变（v4 已撤回） |

**v3 → v4（你的追问：不记录的话会不会重复踩坑；三个参考项目是否有记录）**

| 意见 | 修订 |
| --- | --- |
| 不保存取代与演变会导致重复踩坑 | 撤回原 N8。K1 改为在决策中保留“放弃过的做法”，写明原因、重新考虑的条件和来源；lesson 不随代码变化删除。R2 第 6 步在相关时主动提醒。W2 检查每项都写明原因和来源。B2 迁移时整理被取代的卡片。依据：MATT、ECC 都记录被放弃的方案；Trellis 记录教训但没有整理机制；我方 TW 的规则曾反复横跳，9 月 5 日重建后教训虽留在 git 中，代理却读不到 |

**v4 → v4.1（阶段 2 评审后你的确认）**

| 意见 | 修订 |
| --- | --- |
| 任务身份保留任务编号加可读目录（独立评审 F6，批次 0 第一轮缺陷 F3） | T1 改写，原设计移入“放弃过的做法”；本地目录加身份哈希，避免碰撞；I 阶段 2 同步 |
| 命令重新分组推迟 | C 节加注，T7 增加一项；阶段 2 保留原命令名 |
