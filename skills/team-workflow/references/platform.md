# 项目平台脚本契约

工具只调用项目登记的只读脚本，不附带平台实现。脚本和配置与项目一起评审。

## 登记与调用

`.tw/config.json` 的可选 `platform`：

```json
{"argv":["python3",".tw/platform.py"],"timeout":60,"operations":["task","commit","reference","ci-result"]}
```

`argv` 是非空字符串数组，`timeout` 是正整数秒，默认 60；`operations` 无重复，
只能含上述操作，必须含 `task`。登记的仓内 Python 脚本不作为知识条目。
工具在项目根目录执行 `argv + [操作, 参数...]`。同一命令相同参数只调用一次；复查下载另用空目录。

没有配置时沿用本地任务；http(s) 任务身份必须配置平台，否则提示初始化时生成平台脚本。
仓库身份统一为 git 远端规范化的 `主机/完整路径`，去掉协议、账号、端口与 `.git`。

## 参数与输出

标准输出恰好是一个 JSON 对象，字段必填，标 `?` 的除外；不接受多余字段。
时间都是带时区的 ISO 8601 字符串；完整提交号是 40 或 64 位十六进制。

| 操作 | 参数 | 输出字段 |
| --- | --- | --- |
| task | `--id <任务身份>` | `id,url,repository,state,owners,items,raw` |
| commit | `--repo <仓库身份> --revision <完整提交号>` | `exists,revision,author,time` |
| reference | `--url <链接>` | `reachable,kind,revision?` |
| ci-result | `--locator <JSON> --output <工具给的空目录>` | `provenance,archive` |

`task.id` 必须等于请求身份；发生重定向时拒绝，让调用者改用规范地址。`url` 为规范
任务地址，`repository` 为所属仓库，供跨仓归属核对。`state` 为 `open` 或 `closed`；
`owners` 是负责人字符串数组，可为空。`items` 非空，首项是唯一的 `kind: task`，
地址与顶层 `url` 相同；其余按创建时间、再按地址升序，完整包含评论、变更请求描述与评审。
脚本须处理全部分页，不得截断、改写正文或悄悄替换已删除对象。

`change` 描述展示方案原文；发布记录追加评论，批准可在 `review` 中；评审保留绑定区；隐藏数据见[方案格式](designs.md)。
`review --from-platform` 读取最新绑定评审，`deliver` 无已提交评审时自动读取。
须包含 `change` 的实际作者，供核对评审作者身份；缺失时不能验收。

每个 item：`url,author,created_at,updated_at,body,kind`。地址为 http(s)，作者非空，
`body` 是原文字符串，可为空；`kind` 为 `task/comment/change/review`。
`updated_at` 是最后编辑时间，不早于创建时间，未编辑时两者表示同一时刻。历史记录被编辑时
继续拒绝作为不可变历史。`raw` 保存平台原始 JSON 响应，只存档进任务目录的
`platform/task-<参数哈希>-<响应哈希>.json`，不参与核查，不得夹带凭据。

`commit.exists` 与 `reference.reachable` 是布尔值；提交号必须与请求逐字相同。
`commit.author` 使用 git 作者的 `姓名 <邮箱>`，`time` 是作者时间；提交不存在时两者为 null。
引用 `kind` 为 `commit/file/task/change/comment`；可选提交号也必须完整。
不存在的提交、不可达引用在实际核查时失败。

## 持续集成来源

`locator` 对工具不透明，按 JSON 值传递并原样记入导入记录。`archive` 是下载到
output 内的文件名或相对路径；禁止绝对路径、越界及符号链接，摘要必须匹配。
脚本将平台原始关系映射为以下 `provenance` 对象，不可省略归属核对：

- `repository,revision`：源仓库及完整提交号。
- `run: {id,attempt,latest_attempt,succeeded,url}`：编号、选中与最新重试次数、已完成且成功、地址。
- `job: {id,name,run_id,attempt,started_at,finished_at,succeeded}`：任务及所属运行、重试、时间和完成结果。
- `artifact: {id,run_id,revision,digest,created_at,expired}`：产物及所属运行、源提交、SHA-256 摘要、创建时间、过期状态。

编号为正整数或非空字符串；重试次数为正整数；成功与过期字段是布尔值，
摘要格式 `sha256:<64位小写十六进制>`。仅接收最新成功运行的成功任务，产物未过期，
归属运行与提交一致，创建时间处于任务时间内。

执行 `run --portable` 时，由项目在环境变量 `TW_RUN_CONTEXT` 提供 JSON：
`{"repository":"主机/路径","run_id":"运行编号","attempt":"次数","job":"任务标识"}`。
导入核对仓库、运行、次数、任务名称与执行时间，以及实际测试的提交和全部输入仓库；
任务显示名须等于标识或以 `标识 (` 开头。原始报告、文件摘要、环境、源码和用例核查保持生效。
导入结束另用空目录再读一次，来源不同即失败；以后复用也重新核对来源。

## 错误与凭据

超时、字段缺失、类型、排序或身份错误一律拒绝，不猜测修复。非零退出只展示标准错误
第一行，其余内容及标准输出不展示。未声明操作时说明所需操作，并指向项目脚本和
`.tw/config.json` 的 `platform.operations`。
脚本只能读平台，凭据由现有客户端或环境变量提供；不得写进脚本、输出或存档。

一致性入口：`tw team platform --check --id <任务身份> [--commit <本地提交>] [--reference <链接>]`。
依次核对已声明操作的格式与耗时；提交默认 HEAD，与本地作者、时间交叉核对；引用默认任务地址。
声明 `ci-result` 时还需 `--locator <JSON>`，缺少即失败。输出不含平台正文，全部通过退出 0，
否则退出 1。它不能证明分页完整或替代人工评审。
