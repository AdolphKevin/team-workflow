---
title: "知识格式只把读者需要的字段设为必填，占位内容按错误处理"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/entries.py"]
source: ["self:docs/proposals/2026-10-14-unified-redesign.md"]
verified: {"self": {"commit": "ca9d1f43664dc227f0fea0bf55c9c6ccbbb5e418", "date": "2026-11-08"}}
tags: ["占位符", "形式填充", "必填字段"]
---
# 知识格式只把读者需要的字段设为必填，占位内容按错误处理

现象：已提交的决策卡里留着模板的替换标记（两个下划线包住 REPLACE）；future_use 的约束直接照抄标题，evidence.result 照抄结论，在 5 个服务仓中全部如此。卡片文件头共 53,263 字符，正文只有 3,221 字符。

根因：每张卡强制填写至少两个未来场景和四元组证据，写作者为了通过校验而填写，而不是为了读者。

修复与防护：三种条目共有的必填字段为 title、scope、source；rule、lesson 另需 verified，decision 另需 status；`tw check` 把占位内容当作错误；一次性结果、行号锚点、工具版本给出警告。

发现方法：`tw check` 报“残留占位内容”；评审时看结构化字段是否只是重复正文。

适用条件：给知识格式增加必填字段时。
