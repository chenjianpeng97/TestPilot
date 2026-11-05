# SUT 自学习（feature 规格）

> **定位**：本文件是 epic「repo-as-a-platform」下的旗舰 feature 规格，**不是**平台总纲。
> 稳定世界观仍是根 [`AGENTS.md`](../../AGENTS.md)；业务资产地图是 `INDEX.project.md`。
> 浏览器通道按 config `CHANNELS.browser` 选择（`docs/spec/browser-channel.md`），下文的「Playwright MCP」指默认通道。
> 本 feature 的价值是串起六层几乎全部能力，用它扩展并验证平台。

> **实践驱动**：design 知识的完备格式以下游 dogfood（Plane）为准。
> [`design-knowledge-syntax.md`](design-knowledge-syntax.md) 当前是 **v0.1 草案**。

## 1. 目标

测试工程师用任意 AI 友好 IDE 打开下游测试仓，即可：

1. **学习**被测 Web 系统（页面 / 接口 / DB 副作用 / 业务规则）；
2. **沉淀** feature sets 与测试资产（api_objects / page_objects / action_words）；
3. **交汇**成 behave 活文档，形成可回归的验收自动化。

## 2. 两条学习路径（explore-first）

知识**来源与形态完全开放**；**design 产物严格收敛**。平台不规定从哪拿证据，只规定整理出来的 design 知识长什么样、必须可溯源。

```text
Playwright MCP 探索式测试
        │
        ▼
artifacts/evidence/<run_id>/     ← 统一落盘（强制）
        │
        ├─► 路径一 用户故事
        │     knowledge/wiki/explore/** 能力清单 / 站点地图
        │     （可叠加 assets/usecases、人工文档、互联网资料）
        │           │
        │           ▼
        │     Feature Sets → tests/features/**/*.feature
        │
        └─► 路径二 系统设计
              MCP 网络 + DOM → api_objects / page_objects
              开放证据通道（任选，可组合）：
                · SUT 运行日志 / rancher / loki（用户自建 apps）
                · DB 日志 / 前后快照（用户自建 apps 或参考 tuner-db-diff）
                · 前后端源码路径（工程师给出，LLM 阅读）
                · 人工 PRD / apidoc / domain-notes
              整理收敛 → knowledge/wiki/design/<app>/<route-slug>.md
                    │
                    ▼
              Test Assets → action_words / 断言策略
                    │
                    ▼
              steps imple → Auto UAT（behave）
```

**上半程编排**：[`.cursor/agents/sut-self-learning.md`](../../.cursor/agents/sut-self-learning.md)
（本机账号 → explore → evidence → freeze → design → `artifacts/inbox/`）。
任务记录约定：[`agent-task-log.md`](agent-task-log.md)。

下半程（已有 feature set + design 时写 steps）由
[`.cursor/agents/bdd-asset-pipeline.md`](../../.cursor/agents/bdd-asset-pipeline.md) 编排。

## 3. 证据通道（开放）

平台给**建议**，不强制实现某一种：

| 通道 | 典型做法 | 落点 |
| --- | --- | --- |
| MCP 网络 + DOM | Playwright MCP；必须落盘 evidence | `artifacts/evidence/` |
| DDL | `tuner-dump-ddl` | `knowledge/ddl/` |
| 源码 | 工程师给出前后端路径，LLM 读 models/views/urls | `knowledge/wiki/design/`（inferred） |
| 应用日志 | 仓库已有说明时按 `create-app` 写 log fetcher；没有说明时 `tuner-task ask --topic sut-log-source`，等人在 SSH 目录、日志接口、Rancher API 中选一个 | `apps/<name>/`；决定记在 `work/tasks` 与 `knowledge/wiki/domain-notes` |
| DB 日志 / diff | 用户自建，或后续参考 `tuner-db-diff` | `apps/` 或 kit |
| 人工文档 | 原样放入，只补 front-matter | `knowledge/wiki/usecases` / `domain-notes` |

所有通道最终都要能指到一次 `run_id` 或明确的 `source` 字符串。

## 4. 能力覆盖矩阵（本 feature 验证什么）

| 层 / 能力 | 现状 | 本 feature 暴露的缺口 |
| --- | --- | --- |
| `assets/` | 有 ddl/sql/usecases/domain-notes/testreport | 缺 `explore/`、`design/` |
| `page_test` + harvest | DOM → PageModel 成熟 | 缺无 feature 驱动的探索入口 |
| `api_objects.recording` | 冻结最成熟 | capture 过去可不落盘，无法做时间窗关联 |
| `tuner_testkit.db` | 多数据源执行 | 无 snapshot/diff 原语 |
| `action_words` | kit 框架在，下游目录常空 | 缺「从 trace 反推 words」 |
| `apps/` CLI | 独立工具规范齐全 | 多数不产 JSON；证据 provider 缺约定 |
| `tests/` behave | 双 stage 骨架 | Gate 曾要求必须先有 `.feature` |
| `INDEX.project.md` / `knowledge/wiki/index.md` | maintain-index / maintain-wiki skill | wiki 的 lint 仍靠人触发 |
| DNA | `tuner-dna sync` 成熟 | 新组件走这条下发 |

## 5. 分阶段路线图

- **阶段 0（4.2.0）**：契约先行——本文件 + design schema v0.1 + gates/路径/分诊树纠偏。
- **阶段 1 证据落盘（4.3.0）**：`tuner-evidence persist|routes`；`explore-sut` 强制走 CLI；PageModel `url_path` 占位插值；API `set_path`。
- **阶段 2 design 闭环**：`derive-design-knowledge` + `sut-source-to-design` agent；schema 仍为 v0.1（Plane 切片缺口记在 design spec §6）。
- **阶段 3 双路汇合**：`derive-feature-sets`；bdd-asset-pipeline 下半程。
- **阶段 4 知识自治**：knowledge-curator；确定性 `secret-scan` hook。
- **编排与任务 log（4.4.0 DNA）**：`sut-self-learning` agent + `artifacts/inbox/`；
  探索账号本机文件 `data/sut-accounts.local.yaml`。

内循环用 `uv tool install --from <platform-repo>`；阶段收口才打 tag 发 PyPI。
