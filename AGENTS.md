# 工作入口

本仓只维护项目知识技能 `team-knowledge` 及其 Python 运行时 `tw`，与成员使用的开发流程无关。职责见 [README](README.md)、[设计边界](docs/design.md)与[已批准方案](docs/proposals/2026-10-22-knowledge-only.md)。

- 本仓知识在 `.tw/`；源码、知识与原文在同一改动中维护，原文只保存一份正文。
- 通用工具只用 Python 3.10+ 标准库；产品的业务脚本和测试留在产品仓库。
- 本仓不新增单元、接口或集成测试。验收由未参与实现的独立代理，按 `docs/sop/tw-knowledge-only.yaml` 经真实命令入口执行，结果写入 `docs/validation.md`。`docs/sop/archive/` 仅供历史追溯。
- 技能变化须在隔离工作区做独立代理试用，核对实际输入与结果；两位真实成员各自试用一周的结论单独记录，代理试用不能替代。
- 发行前运行 `python3 scripts/check_release.py` 与打包命令。指令篇幅预算见 `.tw/rules/instruction-budgets.md`；新增强制规则须有真实失败案例或验收要求。
- 保留用户已有授权、实现方式及未提交改动；提交与发布按用户指示执行。

<!-- team-workflow:guidance:knowledge start -->
## 项目知识

开工前读取 `.tw/` 中与任务相关的现行约束、决策和踩过的坑：
`python3 <team-knowledge 技能目录>/scripts/tw.py brief --task "<任务>" --path <相关路径>`。
完成后按 team-knowledge 技能的规则更新知识（与代码同一个 PR），并运行 `tw.py check`。
<!-- team-workflow:guidance:knowledge end -->
