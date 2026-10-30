---
title: "另一个 Claude 配置目录的会话读不到知识技能"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/install.py", "self:docs/install.md"]
source: ["self:skills/team-knowledge/scripts/tw_runtime/install.py", "self:docs/install.md", "用户 2026-10-30 报告：在自定义 CLAUDE_CONFIG_DIR 下运行的 Claude Code 会话，技能列表缺少 team-knowledge，全程未读取项目知识"]
verified: {"self": {"commit": "26e9922cea1ff0c39cac61ebd4b90ae0c3467f15", "date": "2026-10-30"}}
tags: ["CLAUDE_CONFIG_DIR", "安装检查", "技能目录", "多账号"]
guards: ["self:docs/sop/tw-knowledge-only.yaml#SOP-03-P02", "self:docs/sop/tw-knowledge-only.yaml#SOP-03-N02", "self:docs/sop/tw-knowledge-only.yaml#SOP-03-P03"]
---
# 另一个 Claude 配置目录的会话读不到知识技能

现象：成员用另一个 `CLAUDE_CONFIG_DIR` 运行 Claude Code（如多个账号各用一个配置目录），会话的技能列表里没有 team-knowledge，整段开发没有执行 `tw brief`；同一台机器上的安装检查仍然通过。

根因：Claude Code 只从 `CLAUDE_CONFIG_DIR`（默认 `~/.claude`）下的 `skills/` 加载全局技能，skills CLI 只链接到安装当次该变量指向的目录。安装检查把 Claude Code 的目录固定为 `~/.claude/skills`，并跳过不存在的副本，所以缺少技能的配置目录没有任何提示。

修复与防护：安装检查在设置了 `CLAUDE_CONFIG_DIR` 时另外核对 `$CLAUDE_CONFIG_DIR/skills`，该处缺少技能或链接失效时报告安装问题；默认的 `~/.claude/skills` 照常核对，未设置时行为不变。安装说明给出链接命令，链接指向同一份技能，升级后自动生效。

发现方法：在该配置目录启动的会话里查看可用技能，或在同样设置了 `CLAUDE_CONFIG_DIR` 的终端运行 `tw version --check-install`。

适用条件：成员使用多个 Claude Code 配置目录，或修改安装检查覆盖的客户端目录时。
