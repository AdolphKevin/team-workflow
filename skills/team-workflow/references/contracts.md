# 工具约定

这里描述当前项目配置与本地执行接口。任务接续与第三版交接见[协作约定](collaboration.md)，GitHub Actions 结果与第三版交付见[外部结果](external-results.md)。旧项目配置明确拒绝；不自动转换或重建知识。进度记录不参与本地任务内容指纹。

运行环境：Python 3.10+、Git；工具只用标准库，业务检查使用项目自己的环境。统一命令为 `python3 <技能目录>/scripts/workflow.py`，下面用 `$WF` 指代该文件。通过当前技能目录发现 CS 后，将其目录传给 `--cs-skill` 或环境变量 `TEAM_WORKFLOW_CS_SKILL`，不得硬编码作者机器路径。

## 项目配置

根目录 `.team-workflow.json` 使用 `schema_version: 3`，普通执行只读。完整例子见发行包 `examples/python.project.json` 与各 LiveChat 示例。

- `project`：唯一项目名称；`context`：必须读取的本仓文件。
- `knowledge`：`{"provider":"cs","entry":".codestable/wiki/INDEX.md"}`。
- `checks`：检查 ID 映射。每项包含 `argv` 参数数组、`cwd` 本仓工作目录、`timeout` 秒、`purpose`、`format`、`required_cases`、`required_env`。命令不经 shell；需要管道时使用项目明确维护的脚本。
- `format`：`command` 仅记录命令完成；`go-json` 解析 `go test -json`；`junit` 解析 pytest 等生成的 XML，此时提供 `report: "{output}/results.xml"` 并在命令参数中使用相同路径。
- `required_cases`：精确用例 ID。Go 是 `包路径::测试名`；JUnit 是 `classname::name`。空数组表示全部发现的用例都必须通过；显式指定时允许其他用例跳过，但任何用例失败仍失败，必要用例缺失不通过。
- `required_env`：必需环境变量名，只记录缺少的名称，不保存值。凭证通过环境传递，不放命令参数。日志仍须遵循项目脱敏约定；内置脱敏只覆盖已知敏感环境值、Bearer 和 URL 密码，不是通用数据识别器。
- `required_checks`：`{"code":[检查ID],"docs":[]}`；`risk_checks`：风险到非空检查集合。支持 `authorization`、`persistence`、`concurrency`、`messaging`、`public-contract`、`cross-service`。
- `inputs`：参与验证但被 Git 忽略的文件或目录，需显式列入。运行环境中的可变服务和外部数据不能由文件指纹证明稳定，应使用确定性夹具并由评审核对。
- `external_inputs`：逻辑依赖名称到描述的映射。文件为 `{"kind":"file"}`，仓库为 `{"kind":"repository","repository":"owner/repo"}`。本机位置由 `--input 名称=路径`、`--repository owner/repo=路径` 提供，或放入被忽略的 `.team-workflow/local.json` 的 `inputs`、`repositories` 映射；命令参数优先。仓库身份必须与实际 Git 远端一致。共享配置不保存本机绝对路径；本地配置只能提供位置，不能覆盖检查或验收。
- `environment_versions`：名称到版本查询命令数组，例如 `{"go":["go","version"]}`。只在显式运行验证时执行。

配置缺少某个风险映射时不假设普通单元测试已覆盖。`project` 只读检查配置与 CS；可在 CS 不可用时继续 `run`，最终 `verify` 仍不能完成。

## 任务与运行

任务平台是任务原文。用 `task-export --issue <URL>` 导出本次快照，后续使用返回的 `artifact.path`；本地任务输入同样由调用方提供独立文件：

```json
{
  "schema_version": 2,
  "id": "Issue URL 或稳定的本地任务标识",
  "base": "本次改动的完整基准提交编号",
  "goal": "用户原始目标及必要澄清",
  "non_goals": [],
  "kind": "code",
  "risks": [],
  "acceptance": [{"id":"A1","expectation":"可观察结果","checks":["unit"]}]
}
```

`kind` 为 `code` 或 `docs`；内容核查的验收项可用空 `checks`，但最终评审必须提供具体证据。验收项与项目默认、风险要求的检查取并集，不允许报告自行缩小要求。基准提交必须真实存在，不能填写移动的分支名。

```bash
python3 "$WF" project --root "$PROJECT" --cs-skill "$CS_SKILL"
python3 "$WF" brief --root "$PROJECT" --task "$TASK" \
  --cs-skill "$CS_SKILL" --path src
python3 "$WF" run --root "$PROJECT" --task "$TASK"
```

上例的 `$TASK`、`$BRIEF`、`$KNOWLEDGE`、`$REVIEW`、`$DELIVERY` 均为对应命令返回的 `artifact.path`，不是固定公共文件名。

`brief` 的产物含实际简报正文；必须读取，保存回执不代表已经使用知识。产物默认写入 `.team-workflow/tasks/<任务摘要>/requests/<请求编号>/`。`run` 返回完整执行记录的路径。可重复 `--check` 做聚焦运行；最终核查仍要求全部必要结果。不重复列入同一检查的旧运行，使用最终对应版本。

`.team-workflow/` 只放运行产物，不跟踪进 Git。源码指纹覆盖 HEAD、暂存区内容、工作文件、删除及未忽略新文件；`.codestable/` 由 CS 独立核对；源码在测试前后变化使运行失效。子模块需作为参与仓独立核查。工具不提交代码，不替用户恢复原有修改。

## 知识与评审

按 CS 自己的流程完成 `learn` 预览、应用与检查，任务记录请求或结果中包含工作流任务 ID。再捕获完成状态：

```bash
python3 "$WF" knowledge --root "$PROJECT" --task "$TASK" \
  --cs-skill "$CS_SKILL" --cs-task-id '实际CS任务ID' \
  --brief "$BRIEF" --disposition none \
  --reason '本次没有新的稳定结论，仅更新任务记录'
python3 "$WF" review-template --root "$PROJECT" --task "$TASK" \
  --brief "$BRIEF" --knowledge "$KNOWLEDGE"
python3 "$WF" evidence --root "$PROJECT" --path src/example.py
```

`knowledge` 不替代 `learn`，只调用 CS 的只读检查。`none/reused/updated/added` 表示实际知识处置，不要求每次新增卡片。CS 完成记录通过 `task-files` 核对同一任务的状态、版本和文件，通过只读 `receipt-check` 核对相关原文、知识与查询范围。无关任务、缓存或 CS 源码变化不单独使材料失效。接口缺失时报告缺少的能力。CS 当前公开命令不提供历史写入时刻的密码学证明；完整本地闭环仍依赖实际执行 CS 写回与代理评审。

评审模板默认未通过。实际阅读代码、需求及输出后填写：`reviewer`、`standards`、`spec`、每个 `acceptance` 的 `status: passed`、具体 `summary` 与非空 `evidence`。证据使用 `evidence` 命令生成的 `{path,sha256}`；不能只填写测试文件来证明测试通过，应引用运行记录。`knowledge_conflicts_resolved` 在复核实际知识冲突后填写；阻断 finding 必须解决。模板的绑定和知识引用不要手工刷新以掩盖过期。

第三版平台任务生成 `review-template` 时还须传 `--issue <同一Issue-URL>`。模板自动记录完整需求正文的指纹；改了规格正文后，即使交接已更新，旧审查也不能通过。负责人和进度评论的变化不改变该指纹。第二版本地审查保持原有行为。

后续业务代码、测试、任务或配置变化：重跑必要检查并重新评审。只有知识变化：完成相应 CS 处置、重新捕获并评审知识，不自动重复业务测试。

## 最终核查

生成交付模板，所有引用使用前序命令返回的路径：

```bash
python3 "$WF" delivery-template --root "$PROJECT" --task "$TASK" \
  --run "$RUN" --review "$REVIEW" --knowledge "$KNOWLEDGE"
```

```bash
python3 "$WF" verify --root "$PROJECT" --task "$TASK" \
  --report "$DELIVERY" --cs-skill "$CS_SKILL"
```

输出分开记录材料、执行、评审和知识四层。本版成功范围为 `local-workflow`；本地记录可追溯但未签名，不能抵御具有文件写权限者的伪造，也不是全部业务的证明。`run` 成功仅为 `execution-only`。第二版退出码 0 表示指定范围通过，1 表示未完成或输入不可用，2 为 CLI 参数错误。工具文件变化后需用实际安装版本重新运行，不把旧运行冒充新版本结果。

## Python 场景审查

业务场景保留仓库原有运行命令和完整证据要求。检查项可额外声明：

```json
{
  "artifacts": ["{output}/manifest.json", "{output}/suite-transcript.json"],
  "review": {
    "format": "codex-scenario",
    "path": "{output}/codex-review.json",
    "required_artifacts": ["manifest.json", "suite-transcript.json"]
  }
}
```

这段合并到检查项，实际 artifact 列表按项目合同补全。运行工具采集执行时文件；Codex 在运行后审查并写入原项目要求的报告，最终核查检查 `PASS`、`COMPLETED`、相同 run_id、无未解决 finding 及证据哈希。缺少报告、旧报告或旧证据均不能完成。生产运行器不调用本工具，也不生成语义审查结论。

## 并行生成与重试

生成命令可传 `--request-id <唯一编号>`。同一编号且输入相同的完成请求只读返回原结果；
相同编号、不同输入明确拒绝。仍在执行时返回 `running`，进程中断后返回 `interrupted`。
需要重跑检查或处理中断时使用新编号，保留原材料。结果按不可覆盖的原子操作发布，
完整写完才出现最终文件；既有 `--out` 路径被占用时拒绝覆盖。

不同任务及默认调用分别使用独立目录，同一目录中的并发进程也不会抢写公共文件。
源码并行修改仍使用用户已有独立检出目录或 Git worktree。工具不创建工作区管理系统，
不生成公共“当前任务”。手工输入、审查填写和联合清单同样使用各自任务目录。

CS 只按公开命令及返回字段校验能力，不锁定版本、提交或源码哈希。验证时实际使用
的提交写入验证记录，不能成为运行限制。MATT 来源锁定及补丁核验继续保留。
