---
title: "删除旧记录时，它承担的核对被一起删掉"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/check.py", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/install.py", "self:scripts/check_release.py"]
source: ["self:docs/archive/validation-0.x.md", "self:docs/proposals/2026-10-22-knowledge-only.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-01-N01", "self:docs/sop/tw-knowledge-only.yaml#SOP-02-P01", "self:docs/sop/tw-knowledge-only.yaml#SOP-03-P01"]
tags: ["最终交付", "业务验收", "知识处置", "删除桥接", "删除断言"]
---
# 删除旧记录时，它承担的核对被一起删掉

现象：旧团队流程删除知识完成记录时，同时丢失了验收记录与实际知识改动的核对，独立评审才发现；对应断言也曾随记录一起删除。历史原文保存在验证记录归档中。

根因：只按记录的主要用途判断删除范围，没有列清读取它的每处核对以及需要保留的业务保证。

修复与防护：收缩知识库时逐项区分退出的团队规则与继续有效的知识规则。旧团队字段仅提示去向；知识的结构、作用范围、文件与测试名引用继续严格核对，文件清单和发行内容由发行检查核对。

发现方法：删除格式、命令或模块前列出所有使用处，说明每项核对迁往何处或为何放弃。通过真实入口提交不存在的测试名，必须报错，修复引用后才通过。

适用条件：删除或合并知识格式、命令及发行文件时。
