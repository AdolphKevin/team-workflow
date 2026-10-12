# Team Workflow

本仓集中维护团队工作流程、直接复用的 MATT 开发方法和验证工具。使用前独立安装 CS，并完成项目知识初始化。

用 `team-workflow` 开始新任务，默认进入团队流程：评估、分节方案、评审、实施与交接、业务验收、知识回写和最终交付。简单任务可以先实施，再由具体评审人一并批准方案和代码；中等、复杂任务先批准方案再实施。复杂度与风险分别判断，简单任务涉及接口、数据库或权限时仍保留合并评审路径，并完成相应真实验证。

直接调用 MATT 方法保持轻量，不要求团队配置。已经进入团队流程的任务，切换方法继续沿用其有效批准、验收与交接要求。已有批准且已指派的任务，接手者核对共享材料后即可实施；批准范围内不重复请求开工确认。

| 内容 | 维护位置 |
| --- | --- |
| 开发方法 | 15 个 MATT 技能及配套资源 |
| 任务流程与验证工具 | `skills/team-workflow` |
| 术语、架构决策和项目规则 | 所属项目已有原文，通过独立 CS 登记与读取 |
| 方案、职责、进度和交接 | 共享任务材料，首批支持 GitHub Issues |
| 最终任务记录与可复用经验 | 所属项目的 CS 知识库 |
| 业务命令、测试及环境准备 | 业务仓库 |

## 安装与开始

按[安装与升级](docs/install.md)安装完整技能集合，保留同级目录关系。新会话中使用 `/team-workflow` 或 `$team-workflow`；直接调用 MATT 时沿用同一份 CS 接入约定。

```bash
npx skills add AdolphKevin/codestable-compact -g --skill '*' --agent claude-code codex cursor
npx skills add AdolphKevin/team-workflow -g --skill '*' --agent claude-code codex cursor
```

新项目使用第四版配置与任务格式。从已安装技能获得模板和字段说明：

```bash
python3 <team-workflow技能目录>/scripts/workflow.py schema --root <项目目录>
python3 <team-workflow技能目录>/scripts/workflow.py project --root <项目目录> --cs-skill <CS技能目录>
```

首次接入读[接入指南](skills/team-workflow/references/onboarding.md)，日常任务读[团队协作与交付](skills/team-workflow/references/team-delivery.md)，实际命令和记录格式读[第四版工具约定](skills/team-workflow/references/contracts-v4.md)。旧任务继续使用其原格式与工具版本；历史记录不会被静默解释为新版通过证明。

## 0.6.0-rc.1 候选版

本次增加分节方案及逐节批准、可追溯的局部重审、简单任务合并评审、独立的业务验收与知识核对，以及多任务共用实际检查结果。CS 通过结构化任务关联、不可覆盖的计划文件和分类复核提示提供知识能力；本仓按公开能力检查兼容性，不锁定 CS 提交或复制运行脚本。

检查结果绑定源码内容、具体检查与可确认环境。仅提交知识记录或改变暂存布局，不要求重复业务测试。构建依赖、修改仓库和联合验收服务分别声明；跨仓材料保留仓库身份、相对位置及内容指纹。平台命令只生成草稿，提交、发布、关闭任务继续遵循已有授权。

模板随技能安装。清理先预览，只处理已结束任务中没有被引用的请求材料；在途任务、共享批准历史与交付证据继续保留。正式推广仍需两位真实成员完成双向接续，代理试用不能替代该条件。

本轮先交付两仓配套的本地候选版，真实成员试点另行安排。远端 CS 默认分支目前尚未包含新版所需的三项能力；推广前须先交付 CS 改动，再从远端默认分支重新通过第四版接口检查。不能仅更新 team-workflow 后沿用缺少能力的 CS；兼容判断仍依据能力声明，不固定某个提交。具体已执行范围见[本轮验证记录](docs/validation.md#060-rc1-联合候选版2026-10-12)。

## 维护与验证

MATT 基于 [mattpocock/skills](https://github.com/mattpocock/skills) 1.3.1，保留源码、配套资源和 MIT 许可；适配补丁可反向恢复并逐文件校验，见[来源与更新](docs/upstream.md)。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/check_cs.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/check_cs_v4.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/check_parallel.py --cs-skill <独立CS源码目录>/skills/cs
python3 scripts/package.py --output <仓库外目录>/team-workflow-0.6.0-rc.1.zip
```

[验收标准](docs/acceptance.md)区分自动化测试、隔离技能试用和真实成员试点。实际结果记录在[验证记录](docs/validation.md)，未执行项目不得写成通过。工具核对所列检查与材料，不替代业务判断，也不把未签名的本地文件当成防伪证明。
