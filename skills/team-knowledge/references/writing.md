# 写作规范

## 文件头

`---` 之间每行一个 `字段: JSON值`，正文第一行是与 `title` 相同的 `# 标题`。

| 字段 | 说明 |
| --- | --- |
| `title` | 必填 |
| `scope` | rule、decision、lesson 必填，如 `["self:internal/orders/**"]`；`*` 不跨目录，`**` 跨目录 |
| `source` | 必填：Issue、PR、提交链接或 `仓库:原文路径` |
| `verified` | rule、lesson 必填：`{"self": {"commit": "<实际核对时的完整提交>", "date": "YYYY-MM-DD"}}`，日期填实际核对的那天 |
| `status` | decision 必填：`accepted` 或 `rejected` |
| `guards` | 可选：能发现该问题的 SOP 场景 `self:场景文件#场景编号`，或 `check:检查名` |
| `tags`、`symbols`、`related`、`owner` | 可选。`tags` 写任务描述里会出现的业务词，brief 靠它匹配中文 |

文件名：`rules/<slug>.md`，`decisions/` 和 `lessons/` 用 `YYYY-MM-DD-<slug>.md`，slug 只用小写字母、数字和连字符。

## 正文

- **rule**：必须保持的行为，条件与例外写在一起，再写依据（业务来源）。
- **decision**：背景与决定、`## 备选`（真实备选及不采用的理由）、`## 后果`。决定改变时，正文改写为现行结论，旧做法移入 `## 放弃过的做法`，每项写成：

  ```markdown
  - 满 30 天由 Owner 永久删除
    放弃原因：合规要求保留历史（EXC-018）
    重新考虑的条件：出现必须删除的合规要求
    来源：旧卡 k-20260821、提交 dedeca5
    关键词：永久删除、清理任务
  ```

  放弃原因、来源、关键词必填；关键词写任务描述里可能出现的说法，brief 靠它提醒“曾放弃”。已拒绝的决策写 `## 理由`，brief 只展示这一节。
- **lesson**：现象、根因、修复与防护、发现方法、适用条件。必须来自真实发生过的问题（Issue、修复提交或失败的测试），`source` 指向它；代码搬家时更新 scope，教训保留。
- 三种条目都可以有 `## 放弃过的做法`，格式相同。
- 技术约束也可以写成 rule，写明它保护的是什么（接口契约、数据一致性等）；业务规则写明业务来源。

## 配置 `.tw/config.json`

`tw init [--source <来源>]` 预览，`--source` 可重复；概览优先采用指定来源，其次取 `README.md`。预览列出所需的 `--source`，补齐后用 `--apply` 写入。命令生成 `format`、`data_version`、`project`。其余可选字段：

```json
{
  "context": ["docs/operations/runbook.md"],
  "shared": {"common": {"id": "github.com/acme/common"}},
  "documents": [{"id": "adr", "title": "架构决策", "source": "self:docs/adr/*.md"}]
}
```

- `documents` 是数组，`source` 写 `self:路径`（可用 glob）、`别名:路径` 或 http(s) 链接。
- `shared` 只写远端身份。用户级 `${XDG_CONFIG_HOME:-~/.config}/tw/repositories.json` 按 `project.id` 提供默认路径：`{"projects": {"github.com/acme/core": {"repositories": {"common": "~/src/common"}}}}`；检出目录 `.tw/local/repositories.json` 的格式为 `{"repositories": {"common": "../common"}}`。命令行 > 检出目录 > 用户级，按键覆盖；两个文件由成员或代理编辑，工具只读。`inputs` 的外部文件路径同样合并。
- 知识与原文写结论和关键数据，引用入库的文件；本机材料的原件留在执行者本机，试点和手工输出放在仓库外。目录布局可以说明。

## 正例

- “订单写入与库存预留必须在同一事务中提交；提交前校验库存，库存不足时报错并结束本次创建。”
- “会话语言在创建事务前判定，独立字段保存；只接受代理依据更新的买家消息回写。”
- “重复表达同一操作时沿用已有案件，只补问待补齐信息。根因：入口参数被当成业务状态。”

## 反例

- “本次 436 项测试全部通过。” 一次性结果，写进 PR。
- “修改了 3 个文件并修复测试。” 任务过程，写进提交说明。
- “见 service.go:120。” 行号会失效，写符号名。
- “CodeStable 2.1.0 已升级。” 工具版本，写进提交说明。
- 照抄标题或结论来填字段、留下 `（待填写）`：`tw check` 会报错。

## 待核实的结论

写在 Issue 或 PR 中，确认后再写成条目。
