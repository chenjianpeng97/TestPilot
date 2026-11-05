---
name: artifacts-layout
version: 1.1.0
description: 交付物目录 artifacts/ 的子目录职责、run 级 manifest.json 契约、与 assets/testreport 的边界。
---

# artifacts 交付物规范（artifacts-layout）

> `artifacts/` 是 workspace 的**本机运行产出**目录：工具运行、回归报告、探索证据、agent 任务记录、catalog。全部 gitignore。
> 它是唯一的同步边界——本地工作台读它，将来 `tuner-publish` 从它往企业平台送。
> 入库的内容在资产层 `assets/`（含整理后的 `assets/testreport/`）与知识层 `knowledge/`；
> 维护过程的追溯靠被维护对象自己的 changelog（`metadata-conventions.md` §4），不靠 inbox。

## 1. 目录

```text
artifacts/
├── evidence/<run_id>/     # Playwright MCP / 网络 dump（tuner-evidence persist）；脱敏；gitignore
├── inbox/<utc>-<agent>-<slice>.md   # agent 任务记录（agent-task-log.md）；gitignore
├── inbox/questions/Q-<YYYYMMDD>-<nnn>.md # 未回答的人类提问（work-task.md）；gitignore
├── inbox/archived-question/Q-<YYYYMMDD>-<nnn>.md # 已回答的提问；gitignore
├── runs/<run_id>/         # 工具 / 动作词的一次运行（tuner-workspace run、工作台）；gitignore
├── reports/<run_id>/      # 一次回归（behave / pytest）的报告与摘要；gitignore
├── catalogs/workspace.json          # tuner-workspace catalog 产物；gitignore
├── exports/               # 待发布到企业平台的暂存区（C 阶段 tuner-publish）；gitignore
├── playwright/            # 失败截图等浏览器产物；gitignore
└── page_test/             # page_test doctor / run 的产物（历史路径，保留）
```

- `run_id`：`<YYYYMMDDTHHMMSSZ>-<slug>`（UTC，slug 为短横线小写），全 workspace 唯一；`tuner_testkit.artifacts.new_run_id(slug)` 生成。
- 路径解析统一走 `tuner_testkit.project.asset_path("artifacts_<kind>")`（见 §4），禁止在代码里硬编码 `artifacts/...`。
- 除 `artifacts/.gitkeep` 外全部 gitignore；要入库的知识请策展到 `assets/`。

## 2. run 级 `manifest.json`（强制）

`runs/`、`reports/`、`evidence/` 下每个 run 目录必须带 `manifest.json`，由 `tuner_testkit.artifacts.RunManifest` 写入：

```json
{
  "manifest_version": 1,
  "kind": "run",                      // run | report | evidence
  "run_id": "20260922T081200Z-sample-tool",
  "producer": {
    "tool_id": "sample_tool",         // 或 suite: "behave --stage api"
    "argv": ["python", "-m", "apps.sample_tool", "--count", "3"],
    "user_email": "qa@example.com",   // git config user.email；无则 null
    "host": "DESKTOP-1",
    "kit_version": "5.0.0"
  },
  "params": {"count": 3, "label": "demo"},
  "started": "2026-09-22T08:12:00Z",
  "ended": "2026-09-22T08:12:03Z",
  "status": "succeeded",              // running | succeeded | failed | cancelled
  "exit_code": 0,
  "files": [{"path": "stdout.log", "kind": "log", "bytes": 1024}],
  "summary": {"total": 12, "passed": 12, "failed": 0}
}
```

- `status=running` 在开始时写入，结束时改写为终态；工作台与 catalog 靠它区分「还在跑」与「跑完」。
- `files[]` 只列 run 目录内的相对路径；`kind` 建议：`log` / `report` / `envelope` / `screenshot` / `json` / `other`。
- `summary` 自由结构但必须是 JSON 对象；报告类建议 `total / passed / failed / skipped`。
- **禁止**写入 token / cookie / 密码；`params` 中命中敏感键名（`*password*` / `*token*` / `*secret*` / `*cookie*` / `authorization`）的值写入前必须掩码为 `***`（`RunManifest` 自动处理）。

## 3. 谁写什么

| 产出者 | 目录 | 写法 |
| --- | --- | --- |
| `tuner-workspace run` / 工作台 | `runs/<run_id>/` | `stdout.log`、`stderr.log`、`envelope.json`（工具 `--json` 输出）、`manifest.json` |
| behave（`*_environment.py` 钩子） | `reports/<run_id>/` | `summary.json`（feature/scenario 状态）、`manifest.json`；`-f html-pretty -o $TUNER_REPORT_DIR/report.html` 时 html 同目录 |
| pytest | `reports/<run_id>/` | `pytest --junitxml artifacts/reports/<run_id>/junit.xml`，再 `tuner_testkit.artifacts.finish_run` 写 manifest |
| `tuner-evidence persist` / `attach` | `evidence/<run_id>/` | `network.jsonl` / `actions.jsonl` / `run_summary.md` / `screenshots/` / `logs/` / `api/`；`manifest.params.task_id` 指向 `work/tasks` |
| agent（`.cursor/agents/*` 编排） | `inbox/` | 会话流水见 `agent-task-log.md`（只有 agent 必须写；skill 写对象 changelog）；未回答提问见 `inbox/questions/`，已回答见 `inbox/archived-question/` |
| 端口适配器（如 `log-source`） | `evidence/<run_id>/logs/` | 适配器 `--out` 写脱敏日志，再 `tuner-evidence attach --log` 挂到任务 |
| `tuner-workspace catalog` | `catalogs/workspace.json` | 见 `tuner_testkit/workspace/README.md` |

环境变量 `TUNER_REPORT_DIR` 指定本次回归的 run 目录（不设则钩子自动生成 `reports/<run_id>/`）；
`TUNER_RUN_ID` 指定 run_id（不设则自动生成）。

## 4. 路径键（`tuner_testkit.project`）

| key | 默认 | 覆盖环境变量 |
| --- | --- | --- |
| `artifacts` | `artifacts` | `TUNER_ARTIFACTS_DIR` |
| `artifacts_evidence` | `artifacts/evidence` | — |
| `artifacts_inbox` | `artifacts/inbox` | — |
| `artifacts_runs` | `artifacts/runs` | — |
| `artifacts_reports` | `artifacts/reports` | — |
| `artifacts_catalogs` | `artifacts/catalogs` | — |
| `artifacts_exports` | `artifacts/exports` | — |
| `artifacts_playwright` | `artifacts/playwright` | — |
| `artifacts_page_test` | `artifacts/page_test` | `PAGE_TEST_ARTIFACTS_DIR` |

## 5. 与资产层、知识层的边界

- `artifacts/reports/<run_id>/` 是**原始交付物**；人工或 `generate-test-report` skill 整理后的报告落
  `assets/testreport/<sut>/<yyyy-mm>/<slug>.md`，front-matter 用 `evidence: [artifacts/reports/<run_id>]` 指回来源。
- `artifacts/inbox/` 不是 evidence；evidence 只认 `artifacts/evidence/<run_id>/`。
- 入库的任务在 `work/tasks/`，不在 inbox。inbox 里的 question 只是本机待答消息。
