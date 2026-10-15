---
title: "改变仓库身份格式后，已迁移项目的配置失效而检查没有报"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/commands.py", "self:skills/team-knowledge/scripts/tw_runtime/team/common.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:docs/validation.md"]
verified: {"self": {"commit": "ac3be9083919f45fb2a2dcb979a99efdbc5cc3fb", "date": "2026-10-15"}}
guards: ["self:tests/test_unified_team.py#test_project_checks_external_repository_identities_against_local_checkouts"]
tags: ["仓库身份", "external_inputs", "迁移", "配置", "回归", "project"]
---
# 改变仓库身份格式后，已迁移项目的配置失效而检查没有报

现象：平台脚本改造把仓库身份从 `所有者/仓库` 改为 git 远端规范化的 `主机/路径`。core 迁移后的配置仍写 `channelwill/cw2-live-chat-common`，`tw team project` 与 `tw check` 都报正常，直到 `start` 解析依赖仓时才失败。由 Issue #5 的 A7 独立验收发现。

根因：身份格式只在使用依赖仓的命令里核对，配置检查不解析本机检出；改变格式时也没有核对已迁移项目的配置。

修复与防护：`tw team project` 逐个解析 external_inputs 中的依赖仓，身份与本机检出不一致时报错，并给出应改成的值；缺少本机映射只提示。不做新旧格式自动兼容。

发现方法：在真实的已迁移项目上运行 `tw team project`，以及会解析依赖仓的 `start`。

适用条件：改变仓库身份、任务身份或任何配置字段的格式时，先在已迁移项目上运行检查。
