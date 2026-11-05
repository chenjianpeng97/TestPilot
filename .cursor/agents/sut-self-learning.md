---
name: sut-self-learning
version: 1.1.0
description: Orchestrate explore-first SUT self-learning — accounts → browser-channel explore (config CHANNELS.browser) → evidence → freeze API/page objects → design knowledge → index, with an artifacts/inbox task log. Hand off to bdd-asset-pipeline only when Feature Sets are in scope. Do NOT use when the user explicitly requests pytest-only work.
---

# SUT self-learning orchestrator (upper half + optional handoff)

## Purpose

串起「学习被测 Web 系统并生长测试资产」的**上半程**。规格
`docs/spec/sut-self-learning.md`。本文件是可执行编排；规格不是本 agent 的替代。

**下半程**（已有 feature set → steps / behave）交给
`.cursor/agents/bdd-asset-pipeline.md`，不要在本 agent 里硬造 Gherkin，除非用户明确要验收自动化。

## When to use

- 工程师说「探索 SUT / 学习某某模块 / 生成测试资产 / 再跑一轮自学习」。
- 下游仓已有 `tuner-init` 骨架，SUT 可访问。

## Inputs

1. `INDEX.project.md` 与 `knowledge/wiki/index.md`（已有切片、勿重复冻登录接口）；`uv run tuner-config show --json` 取地址、激活环境与 `channels.browser`。
   体检没做过或缺配置时先走 `health-check`。
2. **账号**（只读，禁止拷进仓库/evidence/inbox）：
   1. `data/sut-accounts.local.yaml`（gitignore，唯一来源）
   2. 没有则停，让工程师按 `data/sut-accounts.example.yaml` 补本机文件
3. 垂直切片：问工程师先学哪个模块（对照 `INDEX.project.md` 已有切片，勿重复）。一个模块，不是全站爬。
4. 源码根：config `KNOWLEDGE.source_roots`（本机路径）；没有再问，并用 `maintain-config` 记下。有路径则跑 `sut-source-to-design`。

## Skills / agents（顺序）

| 步 | 组件 | 产出 |
| --- | --- | --- |
| 0 | 读账号 + `explore-safety` | 登录参数（内存） |
| 1 | `dump-ddl`（缺表才跑，禁 `--all`） | `knowledge/ddl/<ds>/` |
| 2 | `explore-sut` | `artifacts/evidence/<run_id>/` + `knowledge/wiki/explore/` |
| 3 | `analyze-mcp-network`（`tuner-evidence routes`） | 路由表 JSON |
| 4 | `reuse-analysis` | 复用 vs 新建 |
| 5 | `freeze-api-objects` | `packages/api_objects/`（跳过 sign-in） |
| 6 | `maintain-page-objects` | `packages/page_objects/` |
| 7 | `derive-design-knowledge`；有源码则 **`sut-source-to-design`** | `knowledge/wiki/design/` |
| 8 | `maintain-index` | `INDEX.project.md` |
| 9 | **本 agent** 写 inbox | `artifacts/inbox/<utc>-sut-self-learning-<slice>.md` |
| 10 | 仅当用户要 `.feature` | `derive-feature-sets` → **`bdd-asset-pipeline`** |

每步先 **Read** 对应 `SKILL.md` / agent 正文再执行。不要跳过 evidence 落盘。

## Inbox（强制）

遵循 `docs/spec/agent-task-log.md`。SUT 自学习日志 **必须**含：

- `## Pages explored`（url pattern / title / 按钮）
- `## Assets added this run`（本任务新增或更新的 api/page/explore/design/ddl）
- `run_id`；`account_id`（无密码）
- 若这是第 N 轮 dogfood：`## Loop delta` 对比上一轮 inbox / 平台能力

## Hard rules

- 活体 SUT：`explore-safety`（throwaway 数据；不问不准删）。
- 密钥不入库、不进 evidence、不进 inbox。
- Web cookie session 的 path 占位用 `{workspace_slug}` 等，调用走 `set_path`。
- 页面资产 app 名对齐现有 `packages/page_objects/<app>/`，勿与装饰器模块重名。
- 未走 Gate 1 证据不得写 api/page/design。

## Done

- evidence 在磁盘且已脱敏。
- 切片的 explore +（若有写操作）design 已引用 `run_id`。
- 新路由已冻或书面说明跳过原因。
- inbox 已落盘，页面清单与资产增量齐全。
