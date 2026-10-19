---
title: "浏览器场景验收由独立技能 playwright-acceptance 执行，只消费 tw 的场景与结果契约"
scope: ["self:skills/playwright-acceptance/**", "self:tests/test_playwright_case_tags.py", "self:tests/test_playwright_to_scenarios.py", "self:tests/fixtures/playwright_acceptance/**"]
source: ["self:skills/playwright-acceptance/SKILL.md", "self:skills/team-workflow/references/scenarios.md"]
status: "accepted"
tags: ["场景验收", "Playwright", "浏览器", "CDP", "录屏", "回归", "上游用例"]
---
# 浏览器场景验收由独立技能 playwright-acceptance 执行，只消费 tw 的场景与结果契约

`tw team scenarios` 规定了场景文件、待执行清单、逐行结果契约与轮次统计，但不规定场景怎么在浏览器里执行。`playwright-acceptance` 补的是“从步骤到执行”这一段：

- 用 Playwright 通过 CDP 接管用户已打开的 Chrome 中指定的一个标签页，不新开浏览器；执行者在真实登录态下操作，登录、人机验证由人完成。
- 一条场景步骤对应一个 `test.step`，标题照抄场景文字；预期不符为 `fail`，前置条件不满足、人机验证、未知遮挡以 `受阻：` 前缀抛出并转成 `blocked`。
- 看板就是 Playwright 自带的 HTML report 与 Trace Viewer（与 D6 一致，tw 不自建看板）；上游用例编号由 `case_tags.py` 从配对文件生成为 report 的 tag，只表示覆盖关系，用例是否通过以 `tw` 按配对与轮次的结论为准。
- `to_scenarios.py` 把 JSON report 转成 `scenario_results.py` 接受的 `results.jsonl` 并把证据复制到结果目录内；提交仍由执行者运行 `tw team scenarios submit`。

技能的两个脚本只用标准库；夹具与配置模板是 JavaScript，随技能分发，复制到业务仓库的验收目录后使用。它的行为测试放在本仓 `tests/`，纳入 `scripts/test.py` 与 `check_release.py`。

## 备选

- 把执行逻辑并入 `tw` 运行时：运行时要引入 Node 与浏览器依赖，违反“通用工具只用 Python 标准库”，不采用。
- 用 Playwright MCP 让代理逐步操作浏览器：每步都经模型往返，成本随步骤数线性增长且不可重放，不采用；脚本一次写成后可反复运行并沉淀为回归。
- 自建验收看板：与 D6 冲突，不采用。

## 后果

技能已在隔离工作区由独立代理试用一轮（一条只读场景通过、一条前置条件不满足的场景正确判为受阻）。按本仓规则，合并发行前仍需两位真实成员试点；试用反馈中尚未处理的事项：无 `tw` 项目时退回清单与问题编号如何降级、前置条件须在首个有副作用的步骤前可核对、测试专用 Chrome profile 是否升级为硬性检查。
