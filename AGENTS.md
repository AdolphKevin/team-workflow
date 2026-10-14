# 工作入口

本仓维护集中分发的团队入口 `team-workflow`、知识入口 `team-knowledge`（唯一的 Python 运行时）、直接复用的 MATT 方法和验证工具。
架构和边界见 [README](README.md) 与[设计说明](docs/design.md)；本次合并重构见[方案](docs/proposals/2026-10-14-unified-redesign.md)。

- 本仓自己的知识在 `.tw/`，开工前用 `tw brief` 读取，完成后在同一改动中更新。这里不包含消费项目的知识、凭证和运行日志。
- MATT 源码复用来源见 `upstream/matt.lock.json`，本地改动见 `upstream/matt.patch`。更新时保留原文、配套资源和许可，核对依赖闭包。
- 源文档只保存一份正文；知识条目引用原文，不复制词汇或设计决策。
- 通用工具仅用 Python 3.10+ 标准库。项目脚本和业务测试留在业务仓库。
- 运行 `python3 -m unittest discover -s tests -v` 与 `python3 scripts/check_release.py`；指令文本受发布检查的篇幅预算约束，新增强制规则必须对应真实失败案例或验收要求。
- 技能变化须在隔离工作区做独立代理试用，检查真实输入与结果；代理试用不能代替两位真实团队成员试点。
- 保留用户已有授权和实现方式，不增加自动提交、外部发布或强制多代理流程。

<!-- team-workflow:guidance:knowledge start -->
## 项目知识

开工前读取 `.tw/` 中与任务相关的现行约束、决策和踩过的坑：
`python3 <team-knowledge 技能目录>/scripts/tw.py brief --task "<任务>" --path <相关路径>`。
完成后按 team-knowledge 技能的规则更新知识（与代码同一个 PR），并运行 `tw.py check`。
<!-- team-workflow:guidance:knowledge end -->
