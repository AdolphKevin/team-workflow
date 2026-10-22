---
title: "改变仓库身份格式后，已迁移项目的配置失效而检查没有报"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/check.py", "self:skills/team-knowledge/scripts/tw_runtime/gitutil.py"]
source: ["self:docs/archive/validation-0.x.md", "self:docs/proposals/2026-10-22-knowledge-only.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-01-P02", "self:docs/sop/tw-knowledge-only.yaml#SOP-02-P01"]
tags: ["仓库身份", "迁移", "配置", "共享仓"]
---
# 改变仓库身份格式后，已迁移项目的配置失效而检查没有报

现象：旧平台改造把仓库身份从 `所有者/仓库` 改为 `主机/路径`，已迁移项目仍保存旧值，直到解析依赖仓才失败。由历史独立验收发现，详见验证记录归档。

根因：身份格式只在使用依赖仓的命令中核对，配置检查未解析本机检出，也未覆盖已迁移项目。

修复与防护：知识层的共享仓以规范化远端身份声明；`project.resolve` 核对实际检出身份，`tw check` 报告不匹配及期望、实际值；缺少映射时提示配置。知识格式与身份格式分开处理，升级不重写项目配置。

发现方法：用真实临时共享仓经 brief、read、check 核对来源；分别配置正确身份、错误身份与缺少映射，确认读取与提示范围。

适用条件：调整共享仓身份或本机映射规则时。
