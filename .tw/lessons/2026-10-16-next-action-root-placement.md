---
title: "下一步中的项目参数被知识命令拒绝"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/cli.py", "self:skills/team-knowledge/scripts/tw_runtime/team/repairs.py", "self:tests/test_recheck.py"]
source: ["self:skills/team-workflow/references/contracts.md", "self:tests/test_recheck.py"]
verified: {"self": {"commit": "ffc8fdcc8d590d18242e77bd0bb2917c3cbd17ba", "date": "2026-10-16"}}
guards: ["self:tests/test_recheck.py#test_u1_all_knowledge_commands_accept_root_after_subcommand", "self:tests/test_recheck.py#test_u1_subcommand_root_takes_precedence_like_team_root"]
tags: ["下一步", "初始化", "root", "命令参数"]
---
# 下一步中的项目参数被知识命令拒绝

现象：未初始化项目的团队状态正确指向初始化，照抄下一步中的命令却被参数解析器拒绝；工具约定中的知识检查命令也有同一问题。

根因：项目参数只在知识入口的全局解析器注册，团队入口和知识子命令的参数位置约定分离。此前测试验证了提示文字，实际执行恢复命令才暴露差异。

修复与防护：知识子命令共用项目参数定义，取值顺序与团队入口一致。守护测试通过实际知识命令覆盖全部子命令与两处取值，真实入口照抄初始化指引并核对配置写入。

发现方法：直接执行下一步与工具约定中的命令，比较两种参数位置的结果。

适用条件：增改公共命令参数、生成恢复命令或调整命令示例时。
