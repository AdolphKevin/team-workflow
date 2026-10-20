---
title: "解决标准库重名时仍须保留内部模块的导入优先级"
scope: ["self:skills/team-knowledge/scripts/tw_runtime/cli.py", "self:skills/team-knowledge/scripts/tw_runtime/team/**", "self:scripts/check_release.py"]
source: ["self:AGENTS.md"]
verified: {"self": {"commit": "8b536d5c3fa7cd8ce0100f47d1bc3d86618394ac", "date": "2026-10-15"}}
tags: ["导入", "标准库", "模块重名", "环境"]
---
# 解决标准库重名时仍须保留内部模块的导入优先级

现象：新模块与标准库同名，把整个 team 目录移到搜索路径末尾后，环境中同名的 metrics 包会被当成内部模块，两个命令入口都报工具缺陷。

根因：对一个文件的重名回避改变了所有内部模块的搜索顺序，干净环境会掩盖这个问题。

修复与防护：项目模块使用不与标准库冲突的文件名，保留原有内部目录优先级。守护测试在独立进程放入同名假包，经两个命令入口核对实际导入的内部模块路径，并同时核对 validation 使用标准库 platform。

适用条件：新增运行时模块或调整命令入口的 Python 搜索路径时。
