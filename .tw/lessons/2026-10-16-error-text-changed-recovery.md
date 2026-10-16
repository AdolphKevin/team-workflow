---
title: "报错措辞决定了下一步和问题位置"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:tests/test_error_routing.py", "self:tests/test_gap_routing.py", "self:tests/test_error_categories.py"]
source: ["self:docs/proposals/2026-10-16-issue5-leftovers.md"]
verified: {"self": {"commit": "7f7f1f531a844d9708d16eb9990d9175e5875c16", "date": "2026-10-16"}}
guards: ["self:tests/test_error_routing.py#test_error_codes_choose_same_repair_for_arbitrary_messages", "self:tests/test_error_routing.py#test_review_format_errors_keep_section_when_reason_changes", "self:tests/test_error_routing.py#test_design_line_uses_structured_key_with_arbitrary_reason", "self:tests/test_gap_routing.py#test_handoff_conflict_and_requirements_use_codes_with_arbitrary_message", "self:tests/test_error_categories.py#test_generic_object_errors_are_independent_of_field_words", "self:tests/test_error_categories.py#test_original_check_report_failure_requires_rerun"]
tags: ["错误代码", "下一步", "问题位置", "报错措辞"]
---
# 报错措辞决定了下一步和问题位置

现象：Issue #5 的评审绑定源码过期后，交付提示由报错中的单词决定；修改措辞也会改变修复命令或指出的小节。

根因：错误只传递显示文字，恢复命令和位置需要从文字片段反推。首次修复还沿用了旧文字中的词和字段名子串，把检查报告误归为交付报告，把本地提交对象缺失误归为批准缺失。批准源码链接有误与本地提交对象缺失也需要分别处理：前者修正源码并重新检查和评审，后者补齐本地对象。

修复与防护：按[工具约定](../../skills/team-workflow/references/contracts.md)选择下一步；错误来源按失败的对象与原因给出代码、位置和明确的操作指引；通用对象校验由调用方指定类别。检查解码与材料汇总继续传递该类别。守护测试对同一错误使用两段任意说明，核对修复命令、小节和行号一致。

发现方法：只替换报错说明，保留错误代码和位置，比较下一步与定位结果。

适用条件：调整命令报错、翻译用户文字或增加错误恢复分支时。
