---
title: "Team Workflow 项目总览"
source: ["self:README.md", "self:docs/design.md", "self:docs/proposals/2026-10-22-knowledge-only.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
---
# Team Workflow 项目总览

本仓只发行项目知识技能 team-knowledge，开工前读取约束、决策和教训，完成后与代码一起维护；与成员使用的开发流程无关。

从 `skills/team-knowledge/SKILL.md` 和写作规范开始。唯一 Python 标准库运行时在 `skills/team-knowledge/scripts/tw_runtime/`：cli 分发命令，project 读取配置及跨仓映射，brief/read 读取知识，entries/check 校验结构与引用，audit 汇总健康情况；init/new/cache 是显式写入入口，install 核对文件清单。

发行检查与打包在 `scripts/`，当前验收场景在 `docs/sop/tw-knowledge-only.yaml`。独立代理经临时项目的真实命令入口验收，结果写入 `docs/validation.md`；历史场景与记录分别在 `docs/sop/archive/`、`docs/archive/`。

项目知识、共享原文与本机材料分开保存。引用只表示可追溯，测试运行由产品仓库 CI 证明。SOP 验收与回归沉淀由 sop-board 发行。两位真实成员各自一周试点须单独记录。
