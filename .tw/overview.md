---
title: "team-workflow 维护仓总览"
source: ["self:README.md", "self:docs/design.md", "self:docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md"]
verified: {"self": {"commit": "f51c1b9ff5911b0b7fee4991e63feb622ce58b90", "date": "2026-10-16"}}
---
# team-workflow 维护仓总览

本仓维护三样东西：团队入口 `team-workflow`、知识入口 `team-knowledge`（唯一的 Python 运行时 `tw`），以及 15 个直接复用的 MATT 方法。

读代码从 `skills/team-knowledge/scripts/tw_runtime/` 开始：知识命令在顶层模块（brief、check、entries），团队流程在 `team/`（入口 workflow.py，交付核查在 delivery.py，执行绑定在 common.py 与 validation.py）。场景文件的格式与内容指纹在 `team/scenario_files.py`，YAML 子集读取在 `team/scenario_yaml.py`，任务场景读取、用例导入与覆盖核对在 `team/scenarios.py`，逐行结果契约在 `team/scenario_results.py`，当前状态、轮次登记与统计在 `team/scenario_rounds.py`。验收材料路径与产品指纹由 `team/validation.py` 统一计算；检查运行继续绑定完整源码。场景验收、评审绑定与回归状态的交付规则在 `team/scenario_acceptance.py`，交付继续复用场景状态与运行选用。流程下一步的统一读取入口是 `team/commands.py` 的 `current_status`；受阻问题身份由 `team/scenario_acceptance.py` 的 `findings` 生成，对应回归见 `tests/test_scenario_rework.py`。场景验收的设计依据见[已批准方案第 2 节](../docs/proposals/2026-10-16-scenario-acceptance-and-positive-text.md#2-验收流程的正确逻辑)。行为测试在 `tests/`，发行检查与打包在 `scripts/`，MATT 来源与补丁在 `upstream/`。

通用工具只用 Python 3.10+ 标准库；业务检查和环境脚本留在业务仓库。自动化测试和代理试用不能代替两位真实成员试点。
