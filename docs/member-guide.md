# 成员操作说明：项目知识

项目知识放在各仓库的 `.tw/`，与代码一起评审。知识的读取和更新与使用的开发流程无关。格式见[写作规范](../skills/team-knowledge/references/writing.md)。

## 日常使用

开工前用 `tw brief --task "<原始要求>" --path <相关路径>` 读取约束、决策和教训；需要全文时用 `tw read <条目>`。出现曾放弃的方向时，先核对原因，再决定是否有新理由。

完成后记录可复用的结论：改变必须保持的行为时写规则，作出需要背景才能理解的选择时写决策，解决根因不明显的缺陷时写教训。没有长期结论的小改动只需说明理由。已有原文直接更新原文，最后运行 `tw check`。

## 评审知识改动

1. 对照业务要求与实际入口判断结论是否成立；结构检查通过不能替代判断。
2. 核对作用范围、来源与防护引用。`guards` 写成 `仓库:文件#测试名`，引用只表示可追溯，运行由 CI 证明。
3. 改变决策时保留旧做法和放弃原因。一次性结果、测试计数、工具版本、行号和任务过程写入变更说明。
4. 跨仓事实写在契约提供方，其他仓通过 `related` 引用。

## 本机材料与清理

`.tw/local/` 被 Git 忽略，按检出目录隔离。`cache/` 是可重新生成的查询缓存，`repositories.json` 是本机共享仓路径映射，其余材料由成员维护。`tw audit` 只列出材料与大小；`tw cache --clear` 只清理缓存。

整目录删除或 `git clean -fdx` 会丢失映射与成员保存的原始材料。需要清理时先备份有用材料，核对删除范围；知识条目和 `config.json` 保留。升级不会自动清理本机目录。

共享仓默认路径写在 `${XDG_CONFIG_HOME:-~/.config}/tw/repositories.json`：

```json
{"projects": {"github.com/acme/core": {"repositories": {"common": "~/src/common"}}}}
```

检出目录覆盖写在 `.tw/local/repositories.json`：

```json
{"repositories": {"common": "../common"}}
```

命令行 `--repository common=<路径>` 优先，其次是检出目录、用户级配置；按别名逐项覆盖。工具只读映射，不猜测路径或克隆仓库。

## 初始化、升级与历史

新项目先 `tw init` 预览，再 `tw init --apply --guidance` 写入，填写生成的概览。旧知识目录按[迁移指南](../skills/team-knowledge/references/migration.md)逐条核实；已采用 `.tw/` 的项目按[升级说明](install.md#从-0x-升级)保留知识。

找回历史教训只在成员要求时进行，候选的支持证据、反证和未核实部分随变更一起评审。
