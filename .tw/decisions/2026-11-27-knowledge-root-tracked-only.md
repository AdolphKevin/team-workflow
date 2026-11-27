---
title: ".tw/ 只放受版本管理的文件，本机材料放在并列的 .tw-local/"
scope: ["self:skills/team-knowledge/SKILL.md", "self:skills/team-knowledge/references/**", "self:skills/team-knowledge/scripts/tw_runtime/project.py", "self:skills/team-knowledge/scripts/tw_runtime/cache.py", "self:skills/team-knowledge/scripts/tw_runtime/init.py", "self:skills/team-knowledge/scripts/tw_runtime/check.py", "self:skills/team-knowledge/scripts/tw_runtime/audit.py", "self:docs/design.md", "self:docs/install.md", "self:docs/member-guide.md"]
source: ["self:docs/proposals/2026-11-27-knowledge-root-and-index-first.md"]
status: "accepted"
tags: ["本机材料", "本机目录", "知识目录", "搜索超时", "grep", "清理", "迁移", "tw-local"]
related: ["decisions/2026-10-14-one-repository-one-runtime.md"]
---
# .tw/ 只放受版本管理的文件，本机材料放在并列的 .tw-local/

`.tw/` 下的每个文件都是评审过的现行知识或配置，在其中搜索得到的都是知识。本机材料放在仓库根的 `.tw-local/`，按检出目录隔离，由目录内只含一行 `*` 的 `.gitignore` 忽略自身：`repositories.json` 是路径映射，`cache/` 是查询缓存，`<任务>/` 放方案草稿、分析、裁定原话与交接说明。可重新生成的运行产物（编译产物、构建缓存、服务日志、浏览器数据）放系统临时目录或验证手册指定的位置。收尾时把任务材料中的结论移入仓库，再删除用完的材料。

工具涉及的位置数量与之前相同：`.tw/`、一个本机目录、用户级 `~/.config/tw/`。旧位置仍是目录时，路径映射照常读取，`tw check` 给出迁移警告；迁移由代理按安装说明执行，在原位置留下指向 `.tw-local/` 的链接，由 `.tw/.gitignore` 中追加的 `local` 忽略，原有的 `local/` 保留给旧版本的 check。旧路径经链接照常可用，`grep -r`、`rg` 默认不跟进链接。

## 备选

- 本机材料移到用户目录：离开工作区后代理写入需要另行授权，材料也更难被看到和清理，不采用。
- 新增 `tw search`：`.tw/` 里只有知识后，grep 与 rg 已经够用，不采用。
- 工具自动删除本机材料：工具分不清哪些是交付前还要用的材料，清理仍由成员或代理看 `tw audit` 后执行，不采用。

## 后果

使用项目的验证手册、检查脚本和指引中写到旧路径的地方可以在迁移之后逐步改为新位置。本机目录位于仓库根，从仓库根做全量文本搜索的工具仍会经过它，大文件因此改放系统临时目录。

## 放弃过的做法

- 本机材料放在知识目录里面的 `.tw/local/`
  放弃原因：某多仓项目的核心服务仓六周内积累 8.9 GiB、6 万个文件，其中 93% 是可重新生成的运行产物，入库知识不到 1 MiB；`grep -r <词> .tw` 两周内至少 8 次撞上 120 秒超时，第一次发生在技能加载之前；草稿中的旧说法混进知识搜索结果
  重新考虑的条件：无
  来源：知识目录与索引方案第 1.1、2.1、7 节（用户确认，2026-11-27）
  关键词：.tw/local、local/、本机材料位置、搜索超时、目录过大、位置不变
- 原地保留 `.tw/local/`，增加说明文字或清理命令
  放弃原因：超时的搜索出自还没读过技能的会话和不遵守 `.gitignore` 的工具，只有目录结构能保证搜索安全；清理命令和 `tw audit` 一样需要有人运行
  重新考虑的条件：无
  来源：知识目录与索引方案第 3 节
  关键词：清理命令、prune、自动清理、说明文字
- 移动目录后不留链接，验证手册、检查脚本与指引中的旧路径必须在同一次改动中更新
  放弃原因：1.3.0 发行当天，某多仓项目的升级会话发现迁移要改 6 个仓库的文档和脚本，还可能打断正在运行的验收和看板服务，于是建议用户不迁移、忽略警告；迁移的理由只写在方案里，会话判断为“只是换个地方存”
  重新考虑的条件：无
  来源：1.3.1 发行说明（用户确认，2026-11-27）
  关键词：迁移成本、同时更新引用、不留链接、兼容链接、旧路径
