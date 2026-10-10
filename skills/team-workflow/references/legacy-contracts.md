# 项目配置与交付材料

所有 JSON 使用 `schema_version: 1`；未知字段与格式版本会被拒绝。路径使用项目内相对路径，文件必须可读、非空，且不能通过符号链接越出项目。检查工具只读取文件和 Git 状态，不执行项目命令。

项目配置 `.team-workflow.json`：

```json
{
  "schema_version": 1,
  "project": "sample-service",
  "context": ["AGENTS.md"],
  "knowledge": {"provider": "cs", "entry": ".codestable/wiki/INDEX.md"},
  "checks": {
    "unit": {"argv": ["python3", "-m", "unittest", "discover"], "purpose": "验证公开行为"},
    "database": {"argv": ["make", "test-db"], "purpose": "验证真实数据库响应和持久化结果"}
  },
  "required_checks": ["unit"],
  "risk_checks": {"persistence": ["database"]}
}
```

支持的风险标记为 `authorization`、`persistence`、`concurrency`、`messaging`、`public-contract`、`cross-service`。普通任务可以使用空风险列表；以上风险出现时，项目配置必须提供非空的相应检查集合。检查是否足以覆盖该风险需要结合任务评审，不能由集合非空推断。

报告通过 `--report` 指定；默认不会向仓库写入报告。示例：

```json
{
  "schema_version": 1,
  "project": "sample-service",
  "revision": "实际提交的完整编号",
  "task": {"reference": "任务链接或当前会话标识", "goal": "可观察的目标", "non_goals": []},
  "risks": ["persistence"],
  "acceptance": [{"id": "A1", "expectation": "重试请求不重复创建记录", "checks": ["unit", "database"]}],
  "checks": [
    {"id": "unit", "status": "passed", "revision": "实际提交的完整编号", "artifact": ".team-workflow/unit.log"},
    {"id": "database", "status": "passed", "revision": "实际提交的完整编号", "artifact": ".team-workflow/database.log"}
  ],
  "review": {"status": "passed", "revision": "实际提交的完整编号", "artifact": ".team-workflow/review.md"},
  "knowledge": {"provider": "cs", "task_note": ".codestable/wiki/task-notes/本次任务.md", "disposition": "none", "reason": "本次复用既有规则，没有新的稳定结论"}
}
```

示例文字需要替换成实际任务与结果，不表示已有测试通过。`checks` 中的每项必须是项目已登记的检查；状态允许 `passed`、`failed`、`skipped`、`not-run`。完成条件及项目配置要求的检查必须实际列出，每项已列检查与评审均需通过。无需执行的检查不列入本次报告，仍需保证风险与完成条件被覆盖。

`revision` 使用当前 Git 提交完整编号，并在命令的 `--revision` 参数中提供可信的预期编号。程序核对项目根目录、当前提交、源文件未提交变化，以及报告、检查和评审的编号一致。忽略目录里的日志可以继续生成；未跟踪且未忽略的文件也视为未完成的工作区变化。程序不证明报告内容可信或测试真的运行过。

`knowledge.disposition` 为 `none`、`reused`、`updated`、`added` 之一，始终填写具体原因与实际 CS 任务记录位置。程序只核对记录文件存在；记录语义、状态和卡片关系由 CS 自己检查。跨仓任务分别生成报告，并保存联合验证结果，单仓结果不能替代整体完成条件。

输出为 JSON，`scope` 固定为 `delivery-material-only` 或 `project-configuration-only`，`business_validation` 固定为 `not-performed`。退出码 `0` 表示所声明范围的材料检查通过，`1` 表示材料存在缺口，`2` 表示输入或环境不可读取。代码、需求和真实测试的审核仍独立进行。
