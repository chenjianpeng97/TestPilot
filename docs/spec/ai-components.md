# AI 组件分组与说明

> `.cursor/**` 下有 rule、skill、agent、hook 四类 AI 组件。本文按类型分组，一句话说明每个组件做什么、什么时候用。
> 这份是**人工维护**的说明；机器生成的清单（含版本号）在 [`.cursor/REGISTRY.md`](../../.cursor/REGISTRY.md)。
> 新增、改名或删除组件时，同步改本文（`tuner-index-ai` 只刷新 REGISTRY，不改本文）。

## 1. 四类组件怎么分

| 类型 | 是什么 | 谁触发 | 位置 |
| --- | --- | --- | --- |
| rule | 约束与边界：什么必须做、什么不能做 | 编辑匹配文件时自动生效，或始终生效 | `.cursor/rules/*.mdc` |
| skill | 一件事的操作流程 | 用户点名或描述任务时进入 | `.cursor/skills/<name>/SKILL.md` |
| agent | 把多个 skill 串成一条长流程 | 任务分诊后由 AI 选用 | `.cursor/agents/*.md` |
| hook | 确定性脚本，不用 LLM | 编辑文件、提交、推送等事件 | `.cursor/hooks.json`、`tools/git-hooks/` |

选型口诀：能脚本化就用 hook；是约束就用 rule；是流程就用 skill；要串流程才用 agent。

## 2. Skills

skill 在 front-matter 用 `group` 分组。**对外入口**只有三组 13 个，用户从这里进；其余标 `internal`，由入口 skill 或 agent 调用，不用单独点名。

### 2.1 知识组（`knowledge`）：维护被测系统知识

| skill | 做什么 |
| --- | --- |
| `dump-ddl` | 从在线库导出表结构到 `knowledge/ddl/<数据源>/` |
| `maintain-wiki` | 把 `knowledge/raw/` 的原始资料整理进 `knowledge/wiki/`（领域笔记、用例场景、探索结论） |
| `maintain-defectlib` | 按固定模板在 `knowledge/defects/` 记录和维护缺陷 |

### 2.2 动作组（`action`）：做测试工作

| skill | 做什么 |
| --- | --- |
| `maintain-testcases` | 一条用例一个文件，维护 `assets/testcases/` |
| `maintain-testsheet` | 从用例库挑选用例，生成一轮测试单 `assets/testsheet/<轮次>/` |
| `execute-testsheet` | 按测试单逐条执行，手工引导或调自动化，回填结果 |
| `generate-test-report` | 汇总执行结果出测试报告；测试单走 GJB438B，回归和点击执行走普通报告 |
| `maintain-bdd-assets` | behave/BDD 自动化的总入口：特性集、复用分析、冻结 API 对象、页面对象、步骤、回归 |
| `maintain-pytest` | 在 `tests/pytest/` 写系统、数据核对、接口契约、性能、稳定性用例 |

### 2.3 可用性组（`availability`）：让仓库保持可用

| skill | 做什么 |
| --- | --- |
| `health-check` | 配置体检：基础项（前后端地址、数据库、`data/` 测试账号、浏览器通道、目录、DNA、hooks）加各功能的就绪度（执行测试单、探索、读源码、查后端日志、导入 API 文档……各缺什么配置）；按用户要用的功能补缺口（`tuner-workspace doctor`） |
| `maintain-config` | 用 LLM 读写 `config/`：环境、URL、数据库、OPS 通道、端口绑定、浏览器通道 |
| `upgrade-framework` | 升级 `tuner-testkit` 和 DNA（规则、skill、规范），处理本地覆盖 |
| `create-app` | 在 `apps/` 新建独立工具，含端口适配器模板（如后端日志） |

### 2.4 内部 skill（`internal`）：由入口调用

| skill | 被谁调用 | 做什么 |
| --- | --- | --- |
| `explore-sut` | `sut-self-learning` | 用浏览器通道探索在线系统，落脱敏证据和探索笔记 |
| `analyze-mcp-network` | `sut-self-learning`、`freeze-api-objects` | 把网络抓包整理成去重路由表 |
| `freeze-api-objects` | `maintain-bdd-assets` | 把脱敏抓包冻结成 `packages/api_objects/` |
| `derive-design-knowledge` | `sut-self-learning` | 综合抓包、DDL、源码，写接口的设计知识（含 DB 影响） |
| `derive-feature-sets` | `maintain-bdd-assets` | 把探索笔记整理成 behave 特性集 |
| `feature-authoring` | `maintain-bdd-assets` | 写或改写 `.feature` |
| `feature-review-lint` | `maintain-bdd-assets` | 审查 `.feature`，给改写建议 |
| `reuse-analysis` | `maintain-bdd-assets` | 新增步骤或对象前先查已有资产，避免重复 |
| `maintain-behave-steps` | `maintain-bdd-assets` | 写和修 behave 步骤定义 |
| `maintain-page-objects` | `maintain-bdd-assets` | 维护 `packages/page_objects/`，定位器失效时修复 |
| `create-action-word` | `maintain-bdd-assets`、`maintain-pytest` | 维护 `packages/action_words/`（造数、断言、接口动作） |
| `run-feature-playwright-mcp` | `maintain-bdd-assets` | 经浏览器通道跑场景，边跑边抓包 |
| `derive-test-design` | 任务类型为测试设计 | 从任务和知识写 `assets/testdesign/` |
| `run-test-execution` | `generate-test-report` | 按测试设计点击执行，挂截图和证据，写报告 |
| `generate-testsheet-report` | `generate-test-report` | 测试单出 GJB438B 报告（Markdown 加 docx） |
| `maintain-index` | 其它 skill 改完资产后 | 增量更新 `INDEX.md` / `INDEX.project.md` |
| `release-template` | 平台维护者（不下发） | 发版：定版本号、刷新 DNA 清单、写发行说明 |

## 3. Agents

| agent | 做什么 |
| --- | --- |
| `sut-self-learning` | 自学习被测系统：账号、探索、证据、冻结对象、设计知识、索引；结束时写任务记录 |
| `bdd-asset-pipeline` | 自学习的下半程：特性集、复用分析、冻结 API 对象、页面对象、步骤、behave 回归；内含三道门禁 |
| `sut-source-to-design` | 走读后端源码加 DDL，起草接口设计知识；不编造表 |

## 4. Rules

### 4.1 始终生效

| rule | 约束 |
| --- | --- |
| `work-task` | 人发布的任务写入 `work/tasks/`；缺日志通道等信息用 `tuner-task ask` 提问，不猜 |
| `commit-convention` | 提交遵循 Conventional Commits，scope 对齐六层 |
| `agent-task-log` | 编排 agent 跑完要在 `artifacts/inbox/` 留任务记录 |

### 4.2 按目录触发：知识与资产

| rule | 范围 | 约束 |
| --- | --- | --- |
| `knowledge` | `knowledge/**` | 知识层的目录与维护方式 |
| `defects` | `knowledge/defects/**` | 缺陷一个文件，固定 front-matter 和章节 |
| `assets-knowledge` | `assets/**` | 资产层（测试设计、用例、测试单、报告）的约定 |
| `testcases` | `assets/testcases/**` | 一条用例一个文件的格式 |
| `index-hygiene` | 知识、资产、packages、apps | 改动后保持索引与对象 changelog 更新 |
| `config` | `config/**` | 配置只放「在哪、走什么通道」，密钥放本机 |

### 4.3 按目录触发：自动化代码

| rule | 范围 | 约束 |
| --- | --- | --- |
| `bdd-asset-layering` | `**/*.py` | feature、steps、action words、page/api objects 与运行库之间的分层边界 |
| `bdd-stage-layout` | `tests/features/**/*.py` | behave `--stage` 目录布局 |
| `bdd-pipeline-gates` | features、api/page objects、design | 证据、冻结、回归三道门禁 |
| `packages-db` | `**/*.py` | 数据库只走 `tuner_testkit.db` |
| `packages-logging` | `**/*.py` | 运行日志只走 `tuner_testkit.logging` |
| `packages-fake` | `**/*.py` | 随机数据只走 `tuner_testkit.fake` |
| `packages-page-test` | page objects、features、action words | UI 定位器集中在 `page_test` 声明里，带多个候选 |

### 4.4 按目录触发：工具与探索

| rule | 范围 | 约束 |
| --- | --- | --- |
| `apps-authoring` | `apps/**` | 工具可独立运行，复用 `tuner_testkit` 和本仓 packages |
| `apps-handover` | `apps/**` | 工具创建或改动时附交接文档 |
| `explore-safety` | 证据与探索笔记 | 探索在线系统的安全约束（脱敏、不写密钥、慎用破坏性操作） |

## 5. Hooks

| hook | 触发 | 做什么 |
| --- | --- | --- |
| `afterFileEdit`（`sync_registry.py`） | 编辑 AI 组件文件后 | 自动刷新 `.cursor/REGISTRY.md` |
| `pre-commit` | `git commit` 前 | 扫描暂存文件里的密钥 |
| `commit-msg` | 写完提交信息 | 校验 Conventional Commits 和 scope 与改动一致 |
| `pre-push` | `git push` 前 | DNA 与发布清单漂移时提醒（不阻塞） |

## 6. 维护约定

- 新 skill 必须在 front-matter 写 `group`（`knowledge` / `action` / `availability` / `internal`）。除非是用户会直接点名的入口，否则标 `internal`。
- 入口 skill 控制在个位数到十来个。同类流程先考虑并进已有入口，而不是新增一个入口。
- 改完组件后跑 `uv run tuner-index-ai` 刷新 REGISTRY，再回来核对本文。
