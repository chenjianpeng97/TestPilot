---
domain: platform
source: 工作台愿景评估与演进（plan 2026-09-22 §A7）
date: 2026-09-22
version: 1.0.0
confidence: high
---

# 「QA 一天」验收剧本

A 阶段的收口判据：一名测试工程师在 `dogfood/`（用平台 scaffold 出的 workspace）里，
五条日常路径都能闭环并留下 inbox 记录。Gherkin 活文档：`tests/features/platform/qa_daily_journeys.feature`。

| # | 路径 | 前置 | 步骤 | 预期产出 | 判据 | 标签 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 拉表结构 → 造数动作词 → 试跑 | 可连的数据源 `main`（`config/env_local.py`） | `/dump-ddl` 单表 → `create-action-word` 一个 `db_seed` → `tuner-action-words run <word_id> --example` | `knowledge/ddl/<ds>/<table>.sql`、`packages/action_words/db_seed/<word>.py`、`assets/CHANGELOG.md` 一行 | run 退出码 0；`tuner-action-words list` 可见 | `@cli @needs-db` |
| 2 | 探索 SUT → 冻结接口与页面 | `data/sut-accounts.local.yaml`；Playwright MCP | `sut-self-learning` agent：explore-sut → analyze-mcp-network → freeze-api-objects → maintain-page-objects | `artifacts/evidence/<run_id>/`、`packages/api_objects/<route>/`、`packages/page_objects/<app>/`、inbox | evidence 已脱敏；inbox 列出页面与资产 | `@llm @needs-sut` |
| 3 | 能力清单 → Feature Set → 回归 → 报告 | 路径 2 的 explore / design 知识 | `derive-feature-sets` → `bdd-asset-pipeline` → `behave --stage api` | `tests/features/<domain>/*.feature`、steps、`artifacts/reports/<run_id>/` | 报告落交付物目录且 manifest 完整 | `@llm @needs-sut` |
| 4 | 开发私有工具 → 目录可见 | 无 | `create-app` skill 生成 `apps/<name>/`（`tool.py` + README）→ `python -m apps.<name> --help` → `tuner-workspace catalog` | `apps/<name>/**`、`artifacts/catalogs/workspace.json` | `--help` 列出全部参数；catalog `tools[]` 含该工具与 `params_schema` | `@cli @offline` |
| 5 | 按六层 scope 提交 | `git config core.hooksPath tools/git-hooks` | 暂存改动 → `git commit -m "feat(apps): …"` | 提交成功 | scope 覆盖改动层则通过，否则被拒并提示缺的层 | `@cli @offline` |

## 执行约定

- `@offline` 场景进 CI：`uv run --directory dogfood behave --stage api --tags @offline`。
- `@needs-db` / `@needs-sut` 场景在有环境时人工或由 agent 驱动执行，结果写 `artifacts/inbox/`。
- 每条路径完成后记录 `## Loop delta`：相对上一轮少了哪些手工步骤。

## 变更说明

- 1.0.0（2026-09-22）：首版。
