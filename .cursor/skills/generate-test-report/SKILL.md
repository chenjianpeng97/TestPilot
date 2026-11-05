---
name: generate-test-report
description: Single entry for test reports. Routes filled test sheets to the GJB438B flow (generate-testsheet-report, tuner-testreport docx), test-design click runs to run-test-execution, and turns a behave/pytest regression run under artifacts/reports/<run_id>/ into a curated Markdown report at assets/testreport/<sut>/<yyyy-mm>/<slug>.md. Use when the user asks to 生成测试报告 / 出报告 / write a test report / 汇总回归结果 / GJB438B.
version: 1.2.0
group: action
---

# Generate Test Report

## 路由（先判断报告的来源）

| 来源 | 走哪 |
| --- | --- |
| 填好的测试单 `assets/testsheet/<轮次>/`，或用户要 GJB438B / docx | 读并遵循 `.cursor/skills/generate-testsheet-report/SKILL.md` |
| 测试设计的端到端点击（`work/tasks` 的 `test-execution`） | 读并遵循 `.cursor/skills/run-test-execution/SKILL.md` |
| behave / pytest 回归 `artifacts/reports/<run_id>/` | 本文件下面的步骤 |

不确定时问用户报告基于哪一轮测试单或哪次回归。

## Scope

- **Write**: `assets/testreport/<sut>/<yyyy-mm>/<slug>.md` only（策展知识，不是原始报告）。
- **Read**: `artifacts/reports/<run_id>/manifest.json` + `summary.json`；可选 `artifacts/inbox/`、`knowledge/wiki/design/**`、`INDEX.project.md`。
- **Must follow**: `docs/spec/metadata-conventions.md`、`docs/spec/artifacts-layout.md`、`docs/spec/assets-knowledge-syntax.md`。

## Steps

1. 选定 `run_id`（用户给出，或取 `artifacts/reports/` 最新一份 `manifest.json`）。
2. 读 manifest / summary，**不要编造**未出现的失败数或缺陷。
3. 定 `<sut>`（`INDEX.project.md` 或用户指定，默认 `platform`）与 `<slug>`（短横线，如 `qa-daily-offline`）。
4. 写文件，front-matter：

```markdown
---
kind: testreport
id: <slug>
title: <一句话>
author: ""
created:
updated:
version: 1.0.0
sut: <sut>
env: <命名环境或 unknown>
run_id: <run_id>
period: <YYYY-MM>
result: {total: 0, passed: 0, failed: 0}
evidence: []
features: []
task_id:          # 有 work task 时填写
design:           # test-execution 指向 assets/testdesign/...
confidence: high
source: artifacts/reports/<run_id>
---
```

5. 正文固定六个二级标题，缺信息写「无」而不是省略。「缺陷」节优先引用 `knowledge/defects/DEF-…`（有缺陷库时），「范围」节列出覆盖的需求 ID：

```markdown
## 范围
## 环境
## 结果
## 缺陷
## 风险
## 证据链接
```

6. 立刻运行（不要手填邮箱）：

```bash
uv run tuner-workspace meta stamp assets/testreport/<sut>/<yyyy-mm>/<slug>.md --kind testreport
```

7. 如有 `INDEX.project.md` 的 testreport 自动区，跑 `tuner-workspace index render`；否则用 `maintain-index` 在人工区加一行。

## Hard rules

- 不得把 token / cookie / 密码写进报告。
- 不得把 `artifacts/evidence/` 原文贴进仓库；只写相对路径链接。
- `assets/testreport` 是策展知识；原始 html/junit 留在 `artifacts/reports/`。

## Verify

1. front-matter 含 `kind: testreport`、`run_id`、`result`。
2. `tuner-workspace meta stamp` 后 `author` 非空（本机有 git email）。
3. 六个章节都在。
