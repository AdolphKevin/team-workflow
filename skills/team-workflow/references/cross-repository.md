# 多仓库共同验收

一个业务目标使用同一个任务 ID，各仓任务分别使用自己的基准提交、风险及验收项。按权威定义索引发现相关仓库；CS 分仓读取、分仓写回，保留各自任务 ID，不复制业务卡片。

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
