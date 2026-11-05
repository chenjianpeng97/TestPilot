---
name: maintain-bdd-assets
version: 1.0.0
group: action
description: Single entry for behave/BDD automation - turns knowledge and testcases into feature sets, reuses or freezes API objects, maintains page objects, action words and behave steps, and runs the staged regression - by routing to the bdd-asset-pipeline agent and its internal skills. Use when the user asks for UI/API flow automation, BDD, behave, .feature, 自动化这个流程, or 把用例自动化. Do NOT use when the user explicitly asks for pytest (use maintain-pytest).
---

# maintain-bdd-assets — BDD 自动化入口

对外只有这一个入口。具体步骤由 agent `.cursor/agents/bdd-asset-pipeline.md` 编排，内部 skill 各管一段。

## 路由

| 情况 | 走哪 |
| --- | --- |
| 还没有被测系统的探索证据（`knowledge/wiki/explore/` 为空、没有相关 evidence） | 先 `.cursor/agents/sut-self-learning.md`（探索 → 冻结 → design），再回到这里 |
| 有探索笔记或用例，需要 `.feature` | `derive-feature-sets` → `feature-authoring` → `feature-review-lint` |
| 写 steps / page / api / action word 之前 | `reuse-analysis`（先找能复用的） |
| 需要接口资产 | `freeze-api-objects`（从 evidence）；有 OpenAPI 时可先 `tuner-openapi-import` |
| 需要页面资产 | `maintain-page-objects` |
| 需要造数 / 断言动作 | `create-action-word` |
| 实现步骤 | `maintain-behave-steps` |
| 回归 | `uv run behave --stage api|ui …`，报告走 `generate-test-report` |

整条流水线（三门禁：证据、冻结、分 stage 回归）以 `bdd-asset-pipeline` agent 为准；它要求写 `artifacts/inbox/` 任务记录。

## 依据

- 场景来自 `knowledge/requirements/`、`knowledge/wiki/usecases/` 与 `assets/testcases/`；feature 的 `@` 标签可带需求 ID（如 `@REQ-order-refund-partial`），便于追溯。
- 浏览器通道按 `CHANNELS.browser`（`docs/spec/browser-channel.md`）。

## 留痕

- 冻结或手改 `packages/{api_objects,page_objects,action_words}` → 对应库 `tuner-workspace changelog append`（录制工具已自动写的不用重复）。
- 提交 scope 覆盖实际层（如 `feat(api_objects,page_objects,tests): automate order refund`）。

## Hard rules

- 用户明确要 pytest 时不产出 `.feature`，改走 `maintain-pytest`。
- 没有证据不写 api / page / design 资产（Gate 1）。
