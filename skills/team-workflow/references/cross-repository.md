# 多仓库共同验收

按权威定义索引发现相关仓库；CS 分仓读取、分仓写回，不复制业务卡片。第三版使用一个总任务关联不同仓的任务编号，并按[协作约定](collaboration.md)明确职责、原文接口、依赖与联合负责人。

## 第三版可移植验收

联合清单包含 `schema_version: 3`、总任务 URL `task_id`、负责联合验证的仓库 `joint`、`participants` 和 `dependencies`。participants 每项为 `{repository, commit, profile, task, report}`，后三项为仓内相对路径；dependencies 每项仅为 `{repository, commit}`，用于没有独立改动的公共依赖。每个参与任务的 parent 指向同一个总任务；各仓 report 必须是第三版。

```bash
python3 <技能目录>/scripts/workflow.py aggregate --root <项目> --joint .team-workflow/joint.json --cs-skill <CS目录> --repository example/core=<本机Core目录> --repository example/gateway=<本机Gateway目录> --repository example/common=<本机Common目录>
```

联合检查配置通过 external_inputs 声明所有其他参与仓及公共依赖，在执行时采集可移植结果，按[外部结果](external-results.md)导入。所有参与方分别完成审查与 CS 回写；聚合器复核各仓要求及交付，再比对联合执行包含的完整仓库版本集合。共享清单不保存本机绝对目录；目录映射由调用者提供。

## 第二版本地验收

原有第二版清单仍支持同机核查，一个业务目标使用同一个任务 ID，各仓分别使用自己的基准提交、风险及验收项。这类运行不能自动变成第三版跨机器证据。

在负责联合测试的仓库放置 `.team-workflow/joint.json`：

```json
{
  "schema_version": 2,
  "task_id": "共同任务标识",
  "joint": "core",
  "participants": [
    {"root": "/实际/core", "profile": ".team-workflow.json", "task": ".team-workflow/task.json", "report": ".team-workflow/delivery.json"},
    {"root": "/实际/gateway", "profile": ".team-workflow.json", "task": ".team-workflow/task.json", "report": ".team-workflow/delivery.json"}
  ]
}
```

先稳定所有参与仓的实现及任务；`joint` 是运行真实联合测试的项目名称，其任务必须声明 `cross-service` 风险，项目配置将该风险映射到联合测试命令。以主入口 `run --joint .team-workflow/joint.json` 执行，运行前后记录全部参与仓的代码和配置状态。其他仓各自完成验证、评审和知识回写，再执行 `aggregate --joint ...`。

单仓命令都通过也不能代替联合调用。聚合器只认可绑定所有参与仓的联合运行；漏仓、重复项目名、不同任务、某仓未完成或任何参与仓变化均不能通过。全部输入是显式本地路径，不通过自然语言猜远端版本。

联合环境不可用时保留阻断，列明缺少的服务或夹具。不要把两个独立单元测试拼成端到端证明，也不要为试点修改真实业务规则。
