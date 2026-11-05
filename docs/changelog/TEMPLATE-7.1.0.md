# tuner-testkit 7.1.0 — 账号单一来源、测试单四态结果、健康检查按能力分层

MINOR，含两处需要下游迁移的不兼容变更。

## 变化

- **账号**：只认 `data/sut-accounts.local.yaml`（`tuner_testkit.accounts.resolve_account`）。`profile.md` 与 config 的 `TEST_ACCOUNT` 移除。`TEST_USERNAME` / `TEST_PASSWORD` 环境变量仍可在 CI 覆盖。
- **测试单结果**：只有 通过、失败、阻塞、忽略 四个词，结果格留空表示待执行。「部分通过」「未执行」不再合法，`tuner-testreport stats --check` 报 `result_invalid` 并给出改法。「忽略」必须在实测记录写原因。报告里失败折为未通过，阻塞、忽略、待执行折为未执行。
- **步骤级卡点**：用例副本的每个 `### N` 步骤下可写 执行、实际、卡点、缺少、证据，规范见 `docs/spec/testsheet-step-record.md`；失败、阻塞的用例必须有带卡点的步骤。
- **health-check**：`tuner-workspace doctor` 的检查分 core 与 feature 两层，新增 `capabilities`（各功能需要哪些配置是否就绪）；`health-check` skill 3.0.0 改为基础项表加能力缺口。
- **文档**：新增 `docs/spec/ai-components.md`，按分组说明所有 AI 组件。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.1.0"` → `uv sync` → `tuner-dna sync --prune`

## 需要迁移

1. 把账号写进 `data/sut-accounts.local.yaml`；删掉 config 里的 `TEST_ACCOUNT` 与 `profile.md`。
2. 已有测试单：把结果为「未执行」的格子清空，「部分通过」按情况改成「失败」或「阻塞」，「本轮信息」的计数行改成 通过、失败、阻塞、忽略。