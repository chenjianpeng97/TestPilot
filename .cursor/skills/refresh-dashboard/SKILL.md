---
name: refresh-dashboard
version: 1.0.0
group: availability
description: Refreshes the workbench dashboard numbers offline - testcases, testsheets, defects, API / page objects, action words and db seeds, BDD scenarios, pytest tests, kit and workspace tools, doctor self-check, environment overview - by running `uv run tuner-dashboard refresh`, which writes the committed DASHBOARD.md (counts plus update time) and the local artifacts/catalogs/dashboard.json that tuner-workbench reads. Use when the user says refresh-dashboard, 刷新看板, 更新看板, 统计资产数量, 看板数字不对, or the workbench home says the numbers have not been collected yet.
---

# refresh-dashboard — 刷新工作台看板

工作台首页（`tuner-workbench`）只读统计结果，不在打开页面时扫文件。统计由本 skill 手动触发，
调用 kit app `tuner-dashboard`（`tuner_testkit/apps/dashboard/README.md`）。

## Scope

- **跑**：`uv run tuner-dashboard refresh`（必要时 `status`）。
- **写**：只有 app 写的两份结果——入库的 `DASHBOARD.md`、本机的 `artifacts/catalogs/dashboard.json`（gitignore）。
- **不写**：不手改 `DASHBOARD.md`；不改资产、配置；不在对话里复述密码、令牌或账号。
- **委托**：doctor 自检里的 warn / missing / error → `health-check`；配置缺口 → `maintain-config`。

## 在哪执行

1. 目标目录要有 `INDEX.project.md` 和 `config/env.py`。没有就停，让用户先 `tuner-init scaffold <dir>`。
2. 仓库根有 `tuner_testkit/project.py` 时这里是平台仓：先问目标目录（下游仓），命令加 `--root <目标>`。

## 1. 统计

```bash
uv run tuner-dashboard refresh
```

stdout 是 JSON：`changed`（`DASHBOARD.md` 是否重写）、`counts`、`delta`（变化的计数，`旧 -> 新`）、
`errors`（失败的段）、`timings`（各段毫秒）、`doctor.not_ok`（自检里不是 ok 的项）。

只想看上次结果、不重新统计：`uv run tuner-dashboard status`。

## 2. 向用户汇报

1. 一句话：统计时间，`DASHBOARD.md` 有没有变化。
2. 有 `delta` 时列出变化的计数（如「测试用例 810 → 816」）；没有就说计数没变。
3. `errors` 非空：说明哪一段失败、原因；该段计数沿用旧值，看板上也会标出来。
4. `doctor.not_ok` 非空：列出检查项与 `fix`，建议交给 `health-check` 处理，本 skill 不修。
5. 提醒用户打开或刷新工作台首页查看（`uv run tuner-workbench`）。

## 3. 提交

- 只有 `changed` 为真（`DASHBOARD.md` 有改动）才需要提交，且只暂存这一个文件：

  ```bash
  git add DASHBOARD.md
  git commit -m "chore(index): refresh dashboard counts"
  ```

- 用户没要求提交时，只告诉用户有改动待提交。
- `artifacts/catalogs/dashboard.json` 在 gitignore，不暂存。
- 合并时 `DASHBOARD.md` 冲突：不手工合并，取任意一边后重新跑 `uv run tuner-dashboard refresh`。

## Hard rules

- 数字只来自 `tuner-dashboard` 的输出，不自己数文件、不估算。
- 不在别的 skill 结束时自动跑本 skill；用户要求时才跑。
- 环境配置只说环境名、地址、数据源别名 / 类型 / host / 库名；密码和令牌不出现。
