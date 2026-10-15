# 跨机器结果与联合验收

实际执行结果、业务评审和知识收尾分别记录。此处只处理执行来源和多仓联合核对；任务
关闭、日志链接可访问或远端显示成功，都不能代替原始执行报告。

## 在执行时保存原始结果

执行 `run --portable` 时，每项检查在运行前后分别读取源码、仓库版本和环境；
输出目录中的 `result.json` 与原始标准输出、错误输出、测试报告一起保存。
需要把结果用于其他机器时，通过现有 CI 发布该检查目录的内容，保持
`result.json` 位于产物压缩包的根目录。工具不会替用户发布产物。

这份文件使用 `data_version: 1`、`kind: portable-execution`，记录：

- 检查编号、定义、命令、执行目录、实际运行仓库及原始用例结果。
- 实际源码内容、执行器版本和环境的指纹，以及运行前后是否一致。
- 所有参与仓库和构建输入的原始提交、内容指纹及是否存在未共享改动。
- 实际开始与结束时间；通过 `TW_RUN_CONTEXT` 记录仓库、运行编号、重试次数和任务名称，字段见[平台脚本契约](platform.md)。

原始文件路径以检查输出目录为起点保存，`argv` 按配置模板记录并保留 `{output}`。
业务命令和仓库身份保持原样。前端检查必须声明其运行仓库，不能用后端检查的
结果代替；配置中的构建输入也会随执行一并记录。

调用方只应在真实命令执行期间使用
`capture(directory, profile, row, before_source, after_source, started, finished)`。
它不可覆盖已有 `result.json`，不能在收尾时补算源码版本来装饰旧日志。

## 导入与复用

`import-result --result <来源文件>` 将文件中的 JSON 定位信息原样交给项目的
`ci-result` 操作，格式由项目脚本决定。来源证明和下载目录按[平台脚本契约](platform.md)。
工具只读平台。它核对运行、任务、重试次数、时间范围、平台公布的产物
摘要和实际下载内容，再从原始报告重新计算用例结果。来源不明、零用例、必要用例
跳过、失败、环境缺失、执行期间源码变化或未共享改动，均不能通过。

导入生成 `kind: imported-execution` 记录。后续每次验证都会重新检查
平台来源、压缩包、解包内容和当前检查要求；本地成功摘要无法替换原始报告。
产物引用使用项目内相对路径，整个项目换目录后可以继续核对。

没有指定目标环境时，默认要求结果中的完整环境与当前实际环境一致。需要在本机
核对不同系统上的 CI 结果时，事先在检查的 `environment.target` 中明确登记目标
环境的完整公开记录：`runtime` 内记录 `python`、`platform`、`machine`；另有
环境类别 `kind`，以及 `versions` 中配置的每个工具版本。需要夹具时，独立的
`fixture` 项保存其标识。工具版本和夹具项均保留完整的 `command` 数组与
`identity` 文本，避免工具名称与运行环境字段互相覆盖。
目标必须完整且与报告逐项相同，不按操作系统名称猜测兼容性，也不从待导入产物
自动生成目标。普通本地执行也遵守该目标；本地环境不符合时不能通过这项 CI 要求。

复用仍要求源码内容、检查定义、执行器一致。导入和业务验收时核对所要求的环境；业务验收后的知识和最终交付
沿用验收时记录的环境，不执行环境命令，也不比较当前环境，夹具清理后仍可核查原始记录。仅提交知识记录或产生
相同源码的新提交，可以继续使用结果；记录始终保留当时实际测试的提交，并另列
本次核对的版本。声明 `revision_sensitive: true` 的检查还要求提交一致。源码变化
后不能把旧提交改成新提交来使结果通过。

公开接口 `import_result(root, profile, locator, directory=None)` 返回生成文件及记录；
`validate_import(root, profile, record, *, live=True)` 返回经核对的结果和原始执行记录；
`live=False` 用于验收后的离线核查，仍检查源码、定义、执行器、平台来源及原始报告。
前者只保存材料，后者不改写材料；二者都不声称完成业务交付。

## 多仓联合交付

联合清单使用仓库身份与项目内相对路径，本机目录通过现有仓库映射提供：

```json
{
  "data_version": 1,
  "task_id": "共同的总任务编号或 Issue URL",
  "joint": "code.example/group/core",
  "requirement": {"repository":"code.example/group/core","task":".tw/local/requirement.json","report":".tw/local/requirement-report.json"},
  "participants": [
    {"repository":"code.example/group/core","commit":"完整提交编号","profile":".tw/config.json","task":".tw/local/task.json","report":".tw/local/report.json"},
    {"repository":"code.example/group/gateway","commit":"完整提交编号","profile":".tw/config.json","task":".tw/local/task.json","report":".tw/local/report.json"}
  ],
  "dependencies": [
    {"repository":"code.example/group/common","commit":"完整提交编号"}
  ]
}
```

`joint` 指向负责联合验证的参与仓库，该任务须声明跨服务风险及相应真实检查。
各参与方分别运行完整的业务、评审、知识与交接核对；任务可以使用不同编号，但
必须关联同一个总任务。本地任务通过 `task.parent` 关联，平台任务读取 Issue 中
的总任务关系。

纯构建依赖只提供固定版本，不因此要求额外成员或独立交付记录。配置中声明需要
修改或联合验证的仓库，必须列为参与方并完成自身交付。联合运行须在执行时覆盖
清单中的所有参与方和构建依赖；本机外部文件不能充当共享仓库版本。

`aggregate(root, manifest, repositories)` 逐仓调用交付核对，再核对
联合检查的实际来源、全部输入、运行时间和原始结果。输入、任务、交付材料或平台
进度在核对期间变化时不能通过。结果分别返回清单当前固定的 `versions` 和实际
运行所用的 `tested_versions`；相同内容的新提交不会抹去原始执行版本。

通过联合核对表示所列材料支持本次交付，`closable` 仍为 `false`。关闭任务继续
使用已有授权，工具不自动关闭、提交或发布任何内容。


## 主需求验收

联合清单必须包含 `requirement: {repository, task, report}`，指向联合负责仓库中的
主需求任务和业务验收输入。该任务编号必须等于清单的 `task_id`，`acceptance_scope` 为
`requirement`，且没有更上层 `parent`。聚合会实际核对主需求场景，不能仅由各参与子任务
通过推导主需求通过；实现任务的知识与最终交付仍逐仓核对。
