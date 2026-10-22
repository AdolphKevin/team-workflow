---
title: "目录与文件路径语义不同会导致简报漏读知识"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/repo_paths.py", "self:skills/team-knowledge/scripts/tw_runtime/globs.py", "self:skills/team-knowledge/scripts/tw_runtime/brief.py", "self:scripts/replay_brief.py"]
source: ["self:docs/archive/validation-0.x.md", "self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-01-P01"]
tags: ["scope", "路径", "目录", "仓库根", "简报", "漏读"]
---
# 目录与文件路径语义不同会导致简报漏读知识

现象：旧任务的范围写 `.` 时开工失败；写目录时命令成功，但简报漏读目录通配符范围下的知识，`./app.py` 与 `app.py` 也曾被误判为不同路径。

根因：目录前缀与具体文件匹配采用两套语义，通配符匹配只检查一个方向，部分使用处比较未规范化字符串。

修复与防护：知识查询经 repo_paths 规范化，保留目录含义；brief 按模式与查询目录是否重叠选择。具体算法依据仍见[知识选择方案 R2](../../docs/proposals/2026-10-14-unified-redesign.md#r2-brief-选择算法)。

发现方法：经 brief 和回放入口核对 `.`、目录、等价路径、范围外路径的实际可见条目，不能只看命令退出码。

适用条件：修改路径规范化、知识范围或简报选择时。
