# 验证记录

本页只保留当前候选版的验证结果；更早版本的记录见 Git 历史。

## 0.7.0-rc.1（未发布改动，2026-10-14）

本轮改动包括业务验收与质量改进标准、项目验收方式与测试能力建设、回归自动化状态、
验收场景的业务来源与验收人独立性检查，以及只保留当前记录格式（`schema_version: 5`）的
清理，以及方案批准与问题处置只要求写明确认人。

| 检查 | 实际结果与证明范围 |
| --- | --- |
| 回归 | 本机 Python 3.13 运行 156 项，全部通过。删除了仅覆盖第一至四版的用例；原先只经旧执行路径覆盖的超时、缺环境、零用例、必要用例跳过、JUnit 新鲜度、脱敏、源码变化和文档任务等保护改由当前执行路径验证。 |
| 发行与来源 | `check_release.py` 通过：相对链接、标准库边界、Python 编译及 MATT 补丁反向恢复。`matt-to-tickets` 中指向工具约定的链接随文件改名更新，锁文件同步记录新指纹。 |
| 真实 CS | 使用本机安装的 CS 2.1.0（`~/.agents/skills/cs`）：`check_cs_knowledge.py` 5 项、`check_cs_delivery.py` 5 项、`check_parallel.py` 9 项，全部通过。 |
| 远端 CI | 提交 `40ffdae` 推送到 `main` 后，[运行 38495264536](https://github.com/AdolphKevin/team-workflow/actions/runs/38495264536) 在 Python 3.10 与 3.13 上均通过：完整回归、发行检查，以及从 CS 默认分支 `960c6b76179b998205ddd069e47b26ecb1e42df8` 运行的知识接口、验收交付与并行组合检查。平台提示 `upload-artifact` 依赖的 Node.js 20 已弃用、`ubuntu-latest` 将迁移到 Ubuntu 26，不影响本次结果。 |
| 指引 | `guidance --apply` 后再次预览，全部目标为 `unchanged`。 |
| 独立代理试用：零测试项目 | 只给技能目录和一个无集成、无 E2E 的 Go + WebSocket 需求。代理判定整体交付未完成；投递与落库未降为单元测试；邮件列为仅人工并因缺少查收证据另列未验证；建设任务的确认人未知时不提前使用过渡状态措辞。产出为文档材料，未经 `verify` 实跑。 |
| 独立代理试用：两个真实项目 | live-chat（Go 多服务加前端的多仓工作区）与 langwill（go.work 下四仓的翻译服务与异步队列）各一名代理只读调查，产出项目验收方案草稿。两份方案注明事实来源，查不到写未知，业务依据标为候选，选用的入口与层次不同，没有互相照搬。方案未经两个项目的开发与测试同事确认，不作为验收依据，也未提交到项目仓库。 |
| 独立代理试用：新项目接入 | 清理后，代理从 SKILL.md 出发，在临时目录新建项目、初始化 CS，经 `schema`、`project`、`guidance`、`prepare`、`run`、`approval-draft`、`review-template`、`delivery-template` 到 `verify --phase acceptance`，结果 `business_accepted: true`、`regression_pending: false`。技能文档中未发现失效链接或对旧格式的提及。评审人与实施者由同一代理扮演，独立性检查只证明记录的名称不同。 |

两次文档试用提出的问题已补入标准与测试能力页：业务依据何为“已确认”、草稿可用范围、
已有手册上补齐、多仓只存一份方案、项目级缺口与任务级延期问题的关系、CI 不归团队维护时
的处理、已有测试的副作用与静默跳过、消息消费者、定时任务及模型输出的检查要点。

新项目接入试用提出、尚未处理的问题：任务验收文字须与方案验收节逐字一致但文档未写明；
纯函数项目的主需求验收需改为人工或完整路径的原因未说明；配置模板假设 pytest；范围不符
时 `verify` 输出整份状态而不指向 `design-diff`；方案修订后需要重跑检查的代价未写明；
无法记录不阻塞的业务疑问；CS 知识构建未完成时 `project` 仍报告就绪；接入指南对 CLAUDE.md
内容的描述与实际不符；复制到项目的记录模板中指向技能的相对链接会失效；证据文件的存放
位置未约定。

复现命令：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/check_cs_knowledge.py --cs-skill <CS仓库>/skills/cs
python3 scripts/check_cs_delivery.py --cs-skill <CS仓库>/skills/cs
python3 scripts/check_parallel.py --cs-skill <CS仓库>/skills/cs
python3 scripts/package.py --output <仓库外目录>/team-workflow-0.7.0-rc.1.zip
```

仍未执行：两位真实团队成员试点。代理试用不能代替真实成员试点，正式推广条件保留。本轮改动
已推送到 `main`；没有修改业务仓或 CS 源码，没有创建发布标签或修改全局安装。
