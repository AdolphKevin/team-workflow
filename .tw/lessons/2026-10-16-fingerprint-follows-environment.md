---
title: "工作区指纹随运行环境变化"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/gitutil.py", "self:skills/team-knowledge/scripts/tw_runtime/team/common.py", "self:skills/team-knowledge/scripts/tw_runtime/team/validation.py", "self:skills/team-knowledge/scripts/tw_runtime/team/portable.py", "self:skills/team-knowledge/scripts/tw_runtime/team/knowledge.py"]
source: ["https://github.com/AdolphKevin/team-workflow/issues/5", "self:docs/proposals/2026-10-16-issue5-leftovers.md"]
verified: {"self": {"commit": "ab02c838dd106c02a262ab19790b49dc5f02eb5b", "date": "2026-10-16"}}
guards: ["self:tests/test_issue5_workspace.py#test_inventory_and_changed_paths_follow_checkout_rules_across_xdg_environments", "self:tests/test_task_progress.py#test_scope_problem_names_globally_ignored_file_and_both_resolutions"]
tags: ["源码指纹", "工作区", "改动范围", "全局忽略", "XDG_CONFIG_HOME", "本机文件"]
---
# 工作区指纹随运行环境变化

现象：Issue #5 第一轮复核误报 Q3。复核代理为隔离用户级映射而设置临时 `XDG_CONFIG_HOME`，同一检出目录随后被判为“源码已变”。

根因：源码指纹与改动范围在多处读取 Git 的全局忽略规则，其位置随运行环境变化，同样的文件由此得到不同清单。

修复与防护：共用的 Git 参数入口显式设置 `-c core.excludesFile=`，文件清单由已跟踪文件与仓库规则以外的未跟踪文件组成。仓库规则取各目录 `.gitignore` 与本检出目录 `.git/info/exclude`。改动范围提示列出文件名，本机文件加入项目 `.gitignore`，项目文件纳入任务范围；此前仅用全局规则忽略本机文件的进行中任务，按新清单重跑一次检查。守护测试在两个用户配置环境中比较源码指纹、改动范围及其他文件清单，并核对仓库忽略规则和处理提示。

发现方法：同一检出目录分别使用含全局忽略文件和空配置的 `XDG_CONFIG_HOME`，经开工、运行检查与查看状态核对“运行检查”仍为已完成。

适用条件：调整工作区文件枚举、源码指纹、改动范围、忽略判断，或在隔离环境中复核已有任务时。
