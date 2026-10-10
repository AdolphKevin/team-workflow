# 外部验证结果

现有第二版本地运行、审查与知识回执继续可用。第三版交付可同时引用本地 run.json 和已导入结果；验收要求、审查和 CS 完成记录仍必须齐备。旧结果只在原有检查范围内解释，原工具版本的记录可用对应固定版本复核，升级不自动生成新的验收证明。

## 执行时采集

GitHub Actions 运行项目原有检查时，可以使用集中安装的执行工具采集可移植结果：

```bash
python3 <技能目录>/scripts/workflow.py run --root . --task .team-workflow/task.json --portable
```

每个检查目录生成 `result.json`、标准输出、错误输出和声明的原始报告。把该检查目录整体作为一个 Actions artifact 上传，使 result.json 位于压缩包根目录。工具在执行前后采集所有源码、公共仓库依赖及环境版本；后来不能给旧报告补填执行时版本信息。项目检查和业务测试仍留在项目内，采集和解析工具只随插件安装。

当前适配器要求执行中的实际提交与 Actions run 的 head_sha 一致；用于导入的工作流 job 保持默认显示名（job ID 或带矩阵后缀的 job ID）。PR 合并提交与 run head 不一致、定制 job 显示名及其他持续集成平台暂不具备该来源核查能力，明确保留为参考材料。其他工具可以执行现有检查并使用此采集入口，无需采用固定开发方法。

待交付仓必须匹配采集内容，且所有源码可由提交获取。外部文件可用于单仓核查；跨机器联合验收须把公共文件纳入对应版本化仓库。不要为获得通过状态提交不属于本任务的改动。

## 导入与核查

本地 locator JSON 只负责定位：

```json
{"kind":"github-actions","repository":"example/project","run_id":100,"attempt":1,"job_id":200,"artifact_id":300}
```

```bash
python3 <技能目录>/scripts/workflow.py import-result --root <项目> --result .team-workflow/locator.json
```

导入通过 gh 当前账号只读读取 run、job、artifact，下载原始 ZIP；核对批次、job、执行时间、源码、检查定义、环境采集及平台提供的压缩包摘要，重新解析 Go JSON 或 JUnit。普通命令仍只证明命令完成，行为由逐项审查判断。缺少运行时来源或原始结果的普通文件只作参考，不可改标为 Actions 结果。

第三版 report 保留 `task_id/runs/review/knowledge`，增加 `issue` 并使用 `schema_version: 3`。`runs` 引用导入返回的 import.json 或当前本地 run.json。verify 会重新读取当前平台要求、远端运行批次和原始 ZIP，发现旧批次、来源变化、缺失/过期材料及被修改的本地摘要时报告未完成。任务平台不可访问时不能宣称已核对当前要求。

校验 SHA-256 用于检查内容对应关系，不是签名或对作者行为的证明。审查仍需确认验收项、实际用例、未覆盖分支和必要环境；绿色的 Actions 运行不是最终交付结论。
