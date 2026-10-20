---
title: "按格式版本分流，让新任务用旧格式绕过了方案批准"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/common.py"]
source: ["https://github.com/AdolphKevin/team-workflow/commit/73afafd", "https://github.com/AdolphKevin/team-workflow/commit/d55d892"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
tags: ["方案批准", "格式版本", "旧格式", "兼容分支"]
---
# 按格式版本分流，让新任务用旧格式绕过了方案批准

现象：新建的 Issue 按旧格式写任务块，走了旧版本的处理分支，在没有方案批准的情况下进入实施。

根因：工具同时支持多个格式版本，并按版本号选择校验逻辑；旧分支没有新的批准要求，等于给新任务留了一条绕行的路。

修复与防护：只接受当前格式；项目数据只认 `data_version`，旧配置字段（schema_version、knowledge、workflow_version）直接拒绝，并给出迁移提示。

发现方法：用旧格式字段构造新任务或配置，命令必须拒绝，而不是降级处理。

适用条件：引入新的数据版本或兼容读取时。
