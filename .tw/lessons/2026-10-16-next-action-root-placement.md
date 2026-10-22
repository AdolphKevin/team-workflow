---
title: "知识命令应接受文档中给出的项目参数位置"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/cli.py"]
source: ["self:docs/archive/validation-0.x.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-01-P01"]
tags: ["初始化", "root", "命令参数"]
---
# 知识命令应接受文档中给出的项目参数位置

现象：旧团队状态给出的初始化命令把 `--root` 放在子命令后，知识入口只接受它位于子命令前，照抄指引实际执行时失败。

根因：公共参数在不同入口单独注册，文字检查没有执行给出的命令。

修复与防护：所有知识子命令共用项目参数定义，支持子命令前后两处写法；两处同时出现时子命令值优先。

发现方法：在临时目录实际执行 `tw --root <项目> init` 与 `tw init --root <项目>`，再用同样两种形式执行知识检查，核对结果。

适用条件：修改公共命令参数或文档示例时。
