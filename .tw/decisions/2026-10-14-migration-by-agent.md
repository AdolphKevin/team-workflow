---
title: "已接入项目由代理按指南迁移，不提供迁移脚本，历史教训按需找回"
scope: ["self:skills/team-knowledge/references/migration.md", "self:skills/team-knowledge/references/lessons-from-history.md"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
status: "accepted"
tags: ["迁移", "重建", "历史教训"]
---
# 已接入项目由代理按指南迁移，不提供迁移脚本，历史教训按需找回

旧的 `.codestable/`、`.team-workflow*` 只是迁移素材，新运行时不读取旧格式。代理按迁移指南逐条核实后用新格式重写，未核实的内容列入 PR 的迁移说明，用户确认后合并，撤销 PR 即可回退。从 git 历史找回教训只在用户要求时进行。

## 放弃过的做法
- `tw rebuild` 工具链：盘点、暂存、应用、恢复，以及对已清空过的仓默认读取 git 历史
  放弃原因：用户确认项目只管最新设计，迁移交给代理整理；默认挖历史成本高，只有 example-assistant 值得找回
  重新考虑的条件：需要一次迁移数十个仓库且语义核实可以批量完成
  来源：方案修订记录 v3
  关键词：rebuild、迁移脚本、inventory、重建工具
