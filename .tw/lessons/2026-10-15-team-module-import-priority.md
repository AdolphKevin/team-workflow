---
title: "解决标准库重名时仍须保留内部模块的导入优先级"
scope: ["self:skills/team-knowledge/scripts/tw.py", "self:skills/team-knowledge/scripts/tw_runtime/cli.py", "self:skills/team-knowledge/scripts/tw_runtime/audit.py", "self:scripts/check_release.py"]
source: ["self:docs/archive/validation-0.x.md", "self:docs/proposals/2026-10-22-knowledge-only.md"]
verified: {"self": {"commit": "777be859050a5b2a69f02c87a8975aee38239cbf", "date": "2026-10-22"}}
guards: ["self:scripts/check_release.py#import_scripts", "self:docs/sop/tw-knowledge-only.yaml#SOP-03-P01"]
tags: ["导入", "标准库", "模块重名", "环境"]
---
# 解决标准库重名时仍须保留内部模块的导入优先级

现象：旧团队模块曾与标准库重名，把整个目录移到搜索路径末尾后，环境中的同名第三方包被误当成内部模块，命令入口报错。

根因：为避开一个文件名冲突，改变了全部内部模块的搜索顺序；干净环境掩盖了问题。

修复与防护：知识入口把自身 scripts 目录放在搜索路径首位，包内使用相对导入；健康报告自行统计本机目录，避免重新引入裸模块导入。发行检查在独立解释器中导入全部知识模块。

发现方法：核对实际导入路径并运行安装后的知识入口；环境中有同名包时仍应读取本技能代码。

适用条件：新增运行时模块或调整 Python 搜索路径时。
