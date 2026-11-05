---
name: maintain-pytest
version: 1.0.0
group: action
description: Writes and maintains pytest suites under tests/pytest for system, data-check (DB), API contract, performance, and stability tests, reusing tuner_testkit (db, api_test, logging, fake, artifacts) and this repo's packages (api_objects, action_words), with reports under artifacts/reports. Use when the user explicitly asks for pytest, 性能测试, 稳定性测试, 数据核对, 接口回归脚本, or a non-Gherkin automated check.
---

# maintain-pytest — pytest 套件

pytest 是和 BDD 并列的一条路：不写 `.feature`、不造 steps，直接复用运行库和本仓业务资产。

## Scope

- **写**：`tests/pytest/**`（测试文件、`conftest.py` 的 fixture）、必要时 `packages/action_words/**`（新动作走 `create-action-word`）、`assets/sql/`（SQL 副本）。
- **读**：`INDEX.project.md`（已有 api objects / action words / page objects）、`knowledge/ddl/`、`knowledge/requirements/`、`assets/testcases/`。

## 目录

```text
tests/pytest/
├── conftest.py                 # 共享 fixture：db 会话、api client、账号（account_id → 本机账号文件）
├── system/test_<域>_<场景>.py   # 系统 / 端到端（API 或 page_test）
├── data/test_<域>_<核对>.py     # 数据核对（只读 SQL）
├── perf/test_<接口>_perf.py     # 性能（标 @pytest.mark.perf，默认不跑）
└── stability/…                 # 稳定性（@pytest.mark.stability）
```

## 写法

1. 先查能复用的：接口用 `packages/api_objects` 的 `APIModel`（`model.set_*(…).execute(…)`），动作用 action words，数据库用 `tuner_testkit.db.DbClient`，
   日志用 `tuner_testkit.logging`，假数据用 `tuner_testkit.fake`。没有接口资产时先 `freeze-api-objects` 或 `tuner-openapi-import`，不手拼请求。
2. 断言写到数据层：接口返回之外，核对落库状态、计数（`log_assertion` 记录 expected / actual）。SQL 用 `%s` 参数化，副本放 `assets/sql/`。
3. 每个测试函数的 docstring 写覆盖的需求 ID 或用例 ID（`REQ-…` / `<用例ID>`），便于追溯。
4. 账号只用 `account_id`；地址从 `tuner_testkit.config`（`get_test_base_url()`）取，不写死。
5. 性能 / 稳定性用 marker 隔离；阈值写成模块常量并注明来源（需求或用户给定）。

## 运行与报告

```bash
uv run pytest tests/pytest -m "not perf and not stability" \
  --junitxml artifacts/reports/<run_id>/junit.xml
```

跑前用 `tuner_testkit.artifacts.start_run(...)` 建 run 目录，跑完 `manifest.finish(status, exit_code=…, summary=…)` 写终态
（`docs/spec/artifacts-layout.md`），报告整理走 `generate-test-report`。

## 收口

提交 scope `tests`（动了 action words 再加 `action_words`）。新 action word 照 `create-action-word` 写 changelog。

## Hard rules

- 不为 pytest 硬造 Gherkin 或 behave steps。
- 不直连数据库驱动、不 `print`、不手写随机业务值（见 `packages-db` / `packages-logging` / `packages-fake` 规则）。
- 性能 / 稳定性测试不对生产环境跑，除非用户明确要求并确认环境名。
