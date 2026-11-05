---
name: run-test-execution
version: 1.1.0
group: internal
description: Internal step (reached via generate-test-report or a test-execution task). Run the click paths in a test design, attach screenshots and sanitized API or log evidence, and write a curated test report that links back to the design. Use when the task type is test-execution or the user asks for an end-to-end click report.
---

# Run test execution

## Scope

- **Read**: 任务的 `design`（`assets/testdesign/**`）及其「点击路径」。
- **Write**: `assets/testreport/<sut>/<yyyy-mm>/<slug>.md`，回写设计的「执行反馈」，必要时 `tuner-evidence attach`。
- **Must follow**: `docs/spec/work-task.md`、`docs/spec/test-design-syntax.md`、`generate-test-report` skill。

## Steps

1. `tuner-task create --type test-execution --title … --design assets/testdesign/<sut>/<slug>.md`，或继续已有任务。然后 `tuner-task start <id>`。
2. 按「点击路径」每一行执行 `python -m tuner_testkit.page_test run <page_id> --flow <flow>`，或对应的 behave UI 场景。失败步使用 page_test 已有的整页截图路径。
   没有页面资产、需要交互点击时，用 config `CHANNELS.browser` 指定的浏览器通道（`docs/spec/browser-channel.md`）。
3. 把当次网络、截图、接口 JSON、日志片段放进同一次 evidence run，并带上任务号：

```bash
uv run tuner-evidence persist --run-id <run_id> --scenario explore:<slug> --network captures.jsonl --task-id <TASK> --screenshot <png> --api <response.json>
uv run tuner-evidence attach --run-id <run_id> --task-id <TASK> --log <excerpt.log> --screenshot <png>
```

4. 设计要求日志证据时，先看 `uv run tuner-workspace doctor --json` 的 `ports.log-source`：
   - `ok`：用绑定的适配器取同一时间窗的日志，`uv run python -m <模块> --since <开始> --until <结束> --trace-id <id> --out artifacts/evidence/<run_id>/logs/<slug>.log --json`，再 `tuner-evidence attach --log`。
   - `missing`（仓库没有日志端口实现）时，立刻：

```bash
uv run tuner-task ask --task <TASK> --topic sut-log-source --prompt "仓库没有写明后端日志从哪取"
```

然后停止依赖日志的回写。不要选择 SSH、日志接口或 Rancher，也不要开始写 fetcher。人回答后按 `answer` 输出的 `next`：`create-app` 按 `log-source` 端口契约写适配器，`maintain-config` 绑定 `PORTS`。人选择 `skip` 时，报告里日志写「无」。

5. 用 `generate-test-report` 写报告。front-matter 额外加上 `task_id` 与 `design`。结果表每一行带证据相对路径（截图、`api/*.json`、`logs/*.log`）。
6. 在测试设计「执行反馈」追加一行：`run_id`、`task_id`、通过或失败、要回写的结论。不改「范围」，除非人确认。bump 设计的 `version`，
   `uv run tuner-workspace changelog append --area testdesign --skill run-test-execution --action 执行反馈 --items <设计路径> --version <旧->新> --reason <run_id>`。
7. `uv run tuner-task bind <id> --output assets/testreport/<sut>/<yyyy-mm>/<slug>.md --evidence artifacts/evidence/<run_id>/`，然后 `tuner-task finish <id>`。仍有未答问题时 CLI 会失败。

## Hard rules

- 报告和设计只链到 `artifacts/evidence/<run_id>/`，不入库截图或响应原文。
- 不编造未出现在 summary 或证据里的失败数。
- 点出的新副作用策展到 `knowledge/wiki/design/`，并在设计的风险里加一行指向同一 `run_id`。
