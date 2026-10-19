---
name: playwright-acceptance
description: 用 Playwright 连接用户已打开的 Chrome，按场景文件中的明确步骤执行 Web 场景验收（含 Shopify 内嵌应用），录屏、截图与 trace 进入 Playwright HTML report，结果可转成 team-workflow 的 tw scenarios submit 契约或 sop-verify 的结果文件，并沉淀为回归检查。适用于：按 SOP 场景做浏览器黑盒验收、把已通过的场景固化成 Playwright 回归、在 report 中按上游用例编号查看结果。
disable-model-invocation: true
---

# Playwright 场景验收

本技能把上游写好的场景步骤执行成 Playwright 测试。它不生成测试用例，不判断业务含义，也不自建看板；看板就是 Playwright 自带的 HTML report 与 Trace Viewer。
场景格式、结果契约与轮次统计由 team-workflow 的 `references/scenarios.md` 规定，本技能只负责"从步骤到执行"这一段。

## 适用边界

- 浏览器：复用用户已打开的 Chrome（CDP），不新开浏览器。建议用测试专用的 Chrome profile，详见[通用 Web 参考](references/web.md#浏览器与连接)。
- 账号与数据：只在测试店铺、测试环境操作。真实账号的登录、人机验证、二次验证都由人完成，代理遇到即停止。
- 独立性：首次验收的执行者不能是实现该功能的人或代理。实现者自己跑脚本只算自检，不能作为验收证据。
- 证据：结果与证据放在业务仓库之外或 `.tw/local/` 下，放进仓库会改变产品指纹，使已通过场景失效。

## 工作流程

1. **读输入。** 读取场景文件（`docs/sop/*.yaml`）、待执行清单与界面地图（`surface-map.md`）。接入 tw 的项目用 `tw team scenarios pending --task <身份> --format json`；没有 tw 的项目用 sop-verify 的 `sop.py pending <场景文件> --format json`，或读取调用方交来的清单。步骤含糊、前置条件不足以确定分支、预期不可观察时，按[场景写法要求](references/scenario-steps.md)列出问题并停止，由场景作者补齐业务含义。
2. **弄清界面结构。** 有产品源码时先读源码（路由、多语言文案、打开弹窗的调用），再在真实页面做只读探测；没有源码时只做只读探测，做法见[只读探测](references/web.md#只读探测)。目标是确认每一步的目标在哪一层：页面本身、应用 iframe、App Bridge modal、新标签页。结论写进界面地图；没有源码核对的条目在"依据"列写"未核对源码，探测于 <日期>"，产品改版后要重新探测。
3. **写脚本。** 把 `templates/playwright.config.mjs` 与 `global-setup.mjs` 复制到业务仓库的验收目录（如 `acceptance/`），`fixtures.mjs`、spec 文件与 `surface-map.md` 放进其下的 `scenarios/`。`global-setup.mjs` 在开跑前检查 `PW_TAB`、Chrome 远程调试和 ffmpeg，缺一项整轮不跑。一条步骤对应一个 `step()`，标题照抄场景步骤；用例标题以场景编号开头；tag 由 `scripts/case_tags.py` 从配对文件生成，不手写。定位优先用角色和可见文字，其次稳定属性；没有可用属性时建议产品方补 `data-testid`。
4. **核对前置条件。** 执行前按 `initial_state` 逐项核对。不满足时抛出以 `受阻：` 开头的错误，不跳过、不自己造数据。
5. **执行。** `npx playwright test`，`workers: 1`。有副作用的步骤（发送、保存、接管、支付）失败后不重试；记录现场后停止，由人决定恢复数据还是判失败。
6. **核对结果。** 只断言用户看得见的结果，不用 URL 或内部状态代替；逐项核对 `forbidden_effects`。预期不符即失败；人机验证、登录过期、未知遮挡、前置条件不满足为受阻。
7. **提交。** `scripts/to_scenarios.py` 把 JSON report 转成结果契约并复制证据。接入 tw 的项目照旧用 `tw team scenarios submit` 登记；没有 tw 的项目转换时加 `--finding-from-reason`，用 sop-verify 的 `submit` 登记，或把结果文件与证据交回调用方（例如 sop-board 的执行会话）。回归沉淀见下文。

## 命令

```bash
# 从 tw 配对文件生成 场景→用例 tag 映射（spec 通过 PW_CASES 读取）
python3 scripts/case_tags.py --pairs <配对.json> --out <仓库外目录>/cases.json

# 执行（环境变量见 templates/fixtures.mjs 顶部注释）
PW_TAB='/apps/<应用>/' PW_CASES=<目录>/cases.json PW_OUT=<仓库外目录> npx playwright test

# 接入 tw 的项目：tw 指 python3 <team-knowledge 技能目录>/scripts/tw.py；取清单、转换、登记，受阻与跳过给出问题编号
tw team scenarios pending --task <身份> --format json > <目录>/pending.json
python3 scripts/to_scenarios.py --report <目录>/report.json --out <目录>/round-1 \
  --executor "<执行者>" --finding SOP-02-P01=Q3 [--pending <目录>/pending.json] [--session <轮次>]
tw team scenarios submit --task <身份> --results <目录>/round-1/results.jsonl

# 没有 tw 的项目：sop 指 sop-verify 的 python3 <技能目录>/scripts/sop.py
sop pending <场景文件> --format json > <目录>/pending.json
python3 scripts/to_scenarios.py --report <目录>/report.json --out <目录>/round-1 \
  --executor "<执行者>" --pending <目录>/pending.json --finding-from-reason
sop submit <场景文件> --results <目录>/round-1/results.jsonl
# 也可把 results.jsonl 与 evidence/ 交回调用方（例如 sop-board 的执行会话）

# 查看
npx playwright show-report <目录>/html
```

超过 64 MiB 的证据可加 `--skip-large` 跳过。`--finding-from-reason` 从 `受阻：` 后的首行取原因，从 skip 注解取说明；跳过时用 `test.skip(true, '<原因>')` 写明。`--finding` 指定的值优先。

在 report 搜索框输入 `@CASE-037` 可筛出覆盖该上游用例的全部测试，再加 `s:failed` 只看失败。tag 只表示"覆盖哪条用例"；接入 tw 时，一条用例是否通过，以 `tw` 按配对与轮次算出的结果为准。

## 受阻与失败

| 情况 | 处理 | 契约状态 |
| --- | --- | --- |
| 预期不符、禁止的副作用发生 | 让断言失败 | `fail` |
| 前置条件不满足、人机验证、登录过期、来源不明的遮挡 | `throw new Error('受阻：<原因>')` | `blocked`，tw 用问题编号，独立验证可用原因 |
| 场景本轮不执行 | `test.skip(true, '<原因>')` | `skip`，tw 用问题编号，独立验证可用原因 |

不要为了跑通把受阻改成跳过或通过；也不要自动关闭来源不明的遮挡层，它可能正是要发现的缺陷。

## 回归沉淀

首次验收通过后保留脚本。接入 tw 的项目在 `.tw/config.json` 登记一项 `format: junit` 的检查运行它，场景的 `regression` 写 `{check: <检查名>, cases: ["<spec 文件名>::<测试标题>"]}`。
依赖已打开浏览器的脚本只能在本机运行，不能在 CI 执行；项目验收方案与回归状态中要如实写明。

## 参考

- [通用 Web 参考](references/web.md)：连接、定位、iframe 与弹窗、等待、证据。
- [Shopify 参考](references/shopify.md)：`app-iframe`、App Bridge modal、主题编辑器、人机验证、登录。
- [场景写法要求](references/scenario-steps.md)：对上游场景的要求与返工清单。
- `templates/`：夹具、配置、示例 spec、界面地图模板。
