---
title: "提交知识使执行证据过期，导致整轮重跑"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/team/common.py", "self:skills/team-knowledge/scripts/tw_runtime/team/validation.py"]
source: ["https://github.com/AdolphKevin/team-workflow/commit/2b3b8d1", "https://github.com/AdolphKevin/team-workflow/commit/41b1a5a"]
verified: {"self": {"commit": "b0247ca6a68c818c565dbe60fe6c07e18c61ab52", "date": "2026-10-14"}}
guards: ["self:tests/test_unified_team.py#test_knowledge_only_commit_preserves_execution_review_and_final_delivery", "self:tests/test_unified_team.py#test_config_in_snapshot_and_bound_only_when_explicitly_declared"]
tags: ["执行绑定", "证据过期", "重跑", "知识提交"]
---
# 提交知识使执行证据过期，导致整轮重跑

现象：提交知识记录后，执行证据被判过期，只能重跑检查并重做评审与交付；代理因此先写知识再提交，按“让工具通过”的顺序操作。一个 +18/−5 的改动产生了 10 个请求，关闭 3 个 Issue 时正式检查全量跑了 4 轮。

根因：执行结果绑定的输入包含了知识与流程文件，或绑定提交号；知识写入属于另一个工具，顺序约束只写在文档里。

修复与防护：执行绑定排除知识正文与 `.tw/local/`，`.tw/config.json` 只按检查绑定各自的配置项；只有声明 revision_sensitive 的检查才绑定 HEAD。

发现方法：只提交知识后再运行最终 verify，按内容绑定的检查结果必须仍被采用。

适用条件：任何把新文件类型加入仓库、或调整快照范围的改动。
