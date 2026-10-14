---
title: "team-workflow 维护仓总览"
source: ["self:README.md", "self:docs/design.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
---
# team-workflow 维护仓总览

本仓维护三样东西：团队入口 `team-workflow`、知识入口 `team-knowledge`（唯一的 Python 运行时 `tw`），以及 15 个直接复用的 MATT 方法。

读代码从 `skills/team-knowledge/scripts/tw_runtime/` 开始：知识命令在顶层模块（brief、check、entries），团队流程在 `team/`（入口 workflow.py，交付核查在 delivery.py，执行绑定在 common.py 与 validation.py）。行为测试在 `tests/`，发行检查与打包在 `scripts/`，MATT 来源与补丁在 `upstream/`。

通用工具只用 Python 3.10+ 标准库；业务检查和环境脚本留在业务仓库。自动化测试和代理试用不能代替两位真实成员试点。
