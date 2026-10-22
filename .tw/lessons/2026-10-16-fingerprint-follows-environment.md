---
title: "知识文件清单不应随全局忽略配置改变"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/gitutil.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/check.py"]
source: ["self:docs/proposals/2026-10-16-issue5-leftovers.md", "self:docs/archive/validation-0.x.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
tags: ["文件清单", "工作区", "全局忽略", "XDG_CONFIG_HOME", "本机文件"]
---
# 知识文件清单不应随全局忽略配置改变

现象：历史复核为隔离用户级映射设置临时 `XDG_CONFIG_HOME`，同一检出目录被误判为源码变化。

根因：文件清单采用 Git 全局忽略规则，配置文件位置随运行环境变化，相同工作区得到不同清单。

修复与防护：共用 Git 命令入口显式设置 `-c core.excludesFile=`。知识读取与引用检查使用已跟踪文件，以及仓库 `.gitignore` 和检出目录 `.git/info/exclude` 以外的未跟踪文件。本机文件的忽略规则由仓库维护。

发现方法：同一检出目录分别使用含全局忽略规则和空配置的环境，核对 brief 所选条目与 check 的路径结果一致。

适用条件：调整文件枚举、路径范围或隔离配置环境时。
