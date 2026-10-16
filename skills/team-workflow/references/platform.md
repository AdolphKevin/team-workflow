# 项目平台脚本契约

平台使用项目脚本，职责见[工具约定](contracts.md#工具做什么)。脚本和配置随项目评审。

## 登记与调用

`.tw/config.json` 的可选 `platform`：

```json
{"argv":["python3",".tw/platform.py"],"timeout":60,"operations":["task","commit","reference","ci-result","file-url"]}
```

`argv` 为非空字符串数组，`timeout` 为正整数秒，默认 60；`operations` 从下列操作中选择，含 `task` 且各项唯一。
在项目根执行 `argv + [操作, 参数...]`，同一命令相同参数只调用一次；复查下载另用空目录。

无配置时沿用本地任务；http(s) 任务须配置平台。仓库身份为 git 远端规范化的 `主机/完整路径`，去掉协议、账号、端口与 `.git`。

## 参数与输出

输出为单个 JSON 对象，仅含表中字段，`?` 表示可选。时间为带时区的 ISO 8601 字符串，完整提交号为 40 或 64 位十六进制。

| 操作 | 参数 | 输出字段 |
| --- | --- | --- |
| task | `--id <任务身份>` | `id,url,repository,state,owners,items,raw` |
| commit | `--repo <仓库身份> --revision <完整提交号>` | `exists,revision,author,time` |
| reference | `--url <链接>` | `reachable,kind,revision?` |
| file-url（可选） | `--repo <仓库身份> --revision <完整提交号> --path <仓内路径#片段>` | `url`：绝对 http(s) 地址 |
| ci-result | `--locator <JSON> --output <工具给的空目录>` | `provenance,archive` |

`task.id` 等于请求身份，重定向须改用规范地址；`url` 为规范任务地址，`repository` 为所属仓库。
`state` 为 `open/closed`，`owners` 为负责人数组，可空。`items` 非空，首项是唯一的 `task`，地址等于顶层 `url`；
其余按创建时间、地址升序，含全部评论、变更请求描述及评审。处理全部分页，保留正文及平台实际返回的已删除对象。

`change` 展示方案原文并提供实际作者；记录追加评论，批准可在 `review` 中，隐藏数据见[方案格式](designs.md)。
评审保留绑定区，`review --from-platform` 读取最新绑定评审，`deliver` 无已提交评审时自动读取；
证据按[术语定义](business-acceptance.md#1-术语)保留作者。

每个 item：`url,author,created_at,updated_at,body,kind`。地址为 http(s)，作者非空，
`body` 是原文字符串，可为空；`kind` 为 `task/comment/change/review`。
`updated_at` 为最后编辑时间，等于或晚于创建时间；不可变历史使用创建后保持原文的记录。
`raw` 为脱敏原始 JSON，存档到任务目录 `platform/task-<参数哈希>-<响应哈希>.json`；核查使用结构字段。

`commit.exists` 与 `reference.reachable` 是布尔值；提交号必须与请求逐字相同。
`commit.author` 使用 git 作者的 `姓名 <邮箱>`，`time` 是作者时间；提交不存在时两者为 null。
引用 `kind` 为 `commit/file/task/change/comment`；可选提交号也必须完整。
核查需要本地可读取的提交与引用，具体缺口随核查结果列出。`file-url` 按参数缓存；未声明时链接转纯文本路径，见[方案展示](designs.md#发布与隐藏记录)。例如 GitHub 可拼出 `blob/<提交>/<路径>#片段`。

## 持续集成来源

`locator` 按 JSON 值原样传递并记入导入记录。`archive` 是下载到
output 内的常规文件相对路径，摘要须匹配。
脚本将平台原始关系映射为以下 `provenance` 对象：

- `repository,revision`：源仓库及完整提交号。
- `run: {id,attempt,latest_attempt,succeeded,url}`：编号、选中与最新重试次数、已完成且成功、地址。
- `job: {id,name,run_id,attempt,started_at,finished_at,succeeded}`：任务及所属运行、重试、时间和完成结果。
- `artifact: {id,run_id,revision,digest,created_at,expired}`：产物及所属运行、源提交、SHA-256 摘要、创建时间、过期状态。

编号为正整数或非空字符串，次数为正整数，状态为布尔值，摘要为 `sha256:<64位小写十六进制>`。
仅收最新成功运行的成功任务；产物未过期，归属运行与提交一致，创建时间处于任务时间内。

执行 `run --portable` 时，由项目在环境变量 `TW_RUN_CONTEXT` 提供 JSON：
`{"repository":"主机/路径","run_id":"运行编号","attempt":"次数","job":"任务标识"}`。
导入核对仓库、运行、次数、任务名、时间、实际提交及全部输入仓库；显示名等于标识或以 `标识 (` 开头。
原始报告、摘要、环境、源码及用例照常核查。结束后用另一个空目录重读，来源不同失败；复用时也核对来源。

## 错误与凭据

超时、缺字段、类型、排序或身份错误均拒绝。非零退出仅展示标准错误首行；未声明操作时指向项目脚本和 `platform.operations`。
凭据由客户端或环境变量提供，脚本、输出和存档仅记录公开信息。

一致性入口：`tw team platform --check --id <任务身份> [--commit <本地提交>] [--reference <链接>]`。
依次核对已声明操作的格式与耗时；提交默认 HEAD，与本地作者、时间交叉核对；引用默认任务地址。
声明 `ci-result` 时还需 `--locator <JSON>`，缺少即失败。输出不含平台正文，全部通过退出 0，
否则退出 1；`file-url` 核对当前提交的 `.tw/config.json` 地址。分页完整性与评审内容由成员核对。
