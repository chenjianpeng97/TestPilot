---
kind: app
tool_id: sample_tool
title: sample_tool — 离线示例工具
author: ""
created: 2026-09-22
updated: 2026-09-22
version: 0.1.0
tags: [fixture]
---

# sample_tool

## 需求背景

工作台（B 阶段）与「QA 一天」验收（A7）需要一个**完全离线**、参数类型齐全的工具，
用来验证「argparse → 参数结构 → 表单 → 运行 → 产物」这条链，而不依赖数据库或被测系统。

## 试用场景

- 适用：演示 / 验收工作台表单渲染与运行；CI 离线冒烟。
- 不适用：任何真实业务造数。
- 前置：无（不需要数据源、不需要登录）。

## 运行方式

```bash
uv run python -m apps.sample_tool --help
uv run python -m apps.sample_tool --count 3 --label demo
uv run python -m apps.sample_tool --count 3 --label demo --json
```

## 运行示例

```bash
uv run python -m apps.sample_tool --count 2 --label demo --style upper --out artifacts/runs/manual/sample.txt
```

预期：stdout 打印 `DEMO-001`、`DEMO-002` 与 `label=demo count=2 dry_run=False`，并写出 `artifacts/runs/manual/sample.txt`。
带 `--json` 时 stdout 只有一行 JSON envelope（`status / outputs[] / artifacts[] / log_path`）。
