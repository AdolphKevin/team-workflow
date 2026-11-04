---
title: "已接入项目由代理按指南迁移，不提供迁移脚本，历史教训按需找回"
scope: ["self:skills/team-knowledge/references/migration.md", "self:skills/team-knowledge/references/lessons-from-history.md"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md", "self:docs/proposals/2026-11-04-field-feedback.md"]
verified: {"self": {"commit": "7cd1894ce0ffdde383d31cc7225a52710f72db8b", "date": "2026-11-04"}}
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

- brief 读取旧卡标题与路径并列出匹配项
  放弃原因：用户确认运行时继续只读 .tw/；旧知识作为未核实线索，由代理按任务词与路径直接检索阅读，再按迁移指南整理。
  重新考虑的条件：出现经用户确认、需要运行时解析旧格式的使用要求
  来源：实际使用反馈方案第 2.2、6 节（2026-11-04）
  关键词：旧卡标题、旧知识、brief 读取旧卡、未初始化
