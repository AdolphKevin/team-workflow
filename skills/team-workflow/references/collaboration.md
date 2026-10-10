# 协作与交接

GitHub Issues 是首个任务平台适配器。沿用项目 MATT 规格，在原 Issue 正文增加一个 `team-workflow-task` 代码块；规格仍可用自然语言表达，结构化验收应与正文一致，由实际审查核对。本地 task.json 由该块中的 task 导出，不另外维护。原文知识仍通过 CS 读取。

```team-workflow-task
{
  "schema_version": 3,
  "parent": null,
  "task": {
    "schema_version": 2,
    "id": "https://github.com/example/project/issues/1",
    "base": "1111111111111111111111111111111111111111",
    "goal": "让用户能够继续已有工作",
    "non_goals": [],
    "kind": "code",
    "risks": [],
    "acceptance": [{"id":"A1","expectation":"下一位成员可以继续工作","checks":["unit"]}]
  }
}
```

`base` 必须是本仓真实基准提交。子任务的 `parent` 为总任务 Issue URL；总任务为 null。Issue assignee 是当前负责人。改变验收需要更新此块及规格正文，进度评论不改变要求版本。

```bash
python3 <技能目录>/scripts/workflow.py resume --root <项目> --issue <Issue-URL> --cs-skill <CS目录> --out .team-workflow/resume.json
python3 <技能目录>/scripts/workflow.py handoff --root <项目> --issue <Issue-URL> --progress .team-workflow/progress.json --cs-skill <CS目录> --out .team-workflow/handoff.json
```

`progress.json` 是草稿输入，包含下列信息；省略业务不需要的集合时填空数组，单仓 `joint_owner` 为空字符串：

```json
{
  "owner": "alice",
  "done": ["完成需求对应的实现"],
  "verified": ["https://github.com/example/project/actions/runs/100/attempts/1"],
  "remaining": ["仍需真实跨服务验证"],
  "questions": [{"question":"待确认的接口范围","owner":"bob"}],
  "next": "补齐联合验证，然后交付",
  "versions": [{"repository":"example/project","commit":"1111111111111111111111111111111111111111"}],
  "references": [],
  "participants": [],
  "contracts": [],
  "dependencies": [],
  "joint_owner": ""
}
```

工具补充要求指纹、前序评论及其指纹、工具版本，输出可阅读的 Markdown 草稿与结构化区。发布时使用输出的 `markdown` 原文追加到同一 Issue。工具只读平台，发布使用已有授权和项目工具。发布前重读要求和前序评论；发布后再次 resume，两个并行后续、被编辑的前序或不连贯历史都会形成缺口。解决冲突应保留相关评论并明确整理；不能删历史后伪造连续交接。

解决历史冲突时，先阅读所有相关评论，将合并后的状态写入草稿，并增加 `resolution: {"history_digest": "<resume 返回的历史指纹>", "reason": "各分支如何合并、保留哪些缺口"}`。工具只在历史仍一致时生成新的明确起点，原评论继续保留。后续若有人修改旧评论，该起点也会失效，必须重新核对。

跨服务额外填写：

- `participants`: 每项 `{issue, repository, owner, role}`。公共依赖也有负责方；可由同一仓任务承担，owner 必须是该任务 assignee。
- `contracts`: 每项 `{document, sha256, provider, consumer, confirmation}`。document 是 CS 登记编号，指纹来自当前原文；provider/consumer 是仓库标识，confirmation 是接口各方确认所在的 Issue/评论或 PR 链接。确认的实质内容需要接手者阅读，链接可访问不证明对方已认可。
- `dependencies`: 每项 `{issue, repository, commit, evidence}`。必须给出可获取提交及交付证据；关闭 Issue 不足以证明依赖已通过验收。
- `joint_owner`: 参与方中的一个负责人，承担联合验证。

`resume` 原样提供 CS 简报和问题清单。`verified` 中的链接只能证明可访问，实际通过仍由 verify 核对报告。阻塞问题可交给下一位处理，因此有明确负责人和下一步的未完成任务也可以交接；不可访问材料、冲突、旧要求或缺少协作责任则无法完整交接。

第三版交付核查还会重新读取平台交接：交接必须完整，且没有剩余工作或未决问题。第二版材料仍按原有本机范围解释。

跨机器交接要求已共享的提交。未提交修改留在原工作区，工具准确报告缺口，不替用户提交、丢弃或搬运代码。暂存布局和机器目录不作为可移植源码身份；实际文件内容、可执行位、提交及显式外部输入参与核对。
