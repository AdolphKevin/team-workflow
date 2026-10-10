# 工作入口

本仓维护集中分发的 team-workflow 技能、直接复用的 MATT 方法及实际验证工具。
架构和边界见 [README](README.md) 与 [设计说明](docs/design.md)。

- 项目知识统一通过独立 CS 读取登记原文和经验。这里不包含消费项目的知识、凭证和运行日志。
- MATT 源码复用来源见 `upstream/matt.lock.json`，本地改动见 `upstream/matt.patch`。更新时保留原文、配套资源和许可，核对依赖闭包。
- 源文档只保存一份正文；CS 的任务记录与引用不复制词汇或设计决策。
- 通用工具仅用 Python 3.10+ 标准库。项目脚本和业务测试留在业务仓库。
- 运行 `python3 -m unittest discover -s tests -v`、`python3 scripts/check_release.py`，以及针对锁定 CS 的真实接口测试。
- 技能变化须在隔离工作区做独立代理试用，检查真实输入与结果；代理试用不能代替两位真实团队成员试点。
- 保留用户已有授权和实现方式，不增加自动提交、外部发布或强制多代理流程。
