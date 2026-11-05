---
kind: app
tool_id: sample_log_source
title: sample_log_source — log-source 端口的参考适配器
author: ""
created: 2026-11-04
updated: 2026-11-04
version: 0.1.0
tags: [dogfood, port, log-source]
---

# sample_log_source

## 需求背景

TestPilot 不内置取后端日志的实现：各团队的通道不同（SSH 进目录、日志平台 API、Rancher）。
kit 只定义 `log-source` 端口契约（`docs/spec/ports.md`），workspace 自己写适配器。
这个 app 是 dogfood 里的参考实现：通道换成本地 `data/sample-logs/*.log`，离线就能验证契约、
`tuner-config validate` 的端口检查和 `tuner-workspace doctor` 的 `ports.log-source`。

真实项目照这个形状写：保留 `cli.py` 的参数与 `--json` envelope，把 `core.read_lines` 换成自己的通道，
通道地址与密钥从 config `OPS` 读（`tuner_testkit.config.load_project_env().OPS`），不写进代码。

## 试用场景

- 适用：演示端口契约；离线 CI；给新团队当模板。
- 不适用：读真实被测系统日志。
- 前置：`config/env.py` 里 `PORTS = {"log-source": "apps.sample_log_source"}`（dogfood 已绑定）。
  可选 `OPS = {"local_logs": {"dir": "<目录>"}}` 改读取目录，默认 `data/sample-logs`。

## 运行方式

```bash
uv run --directory dogfood python -m apps.sample_log_source --help
uv run --directory dogfood python -m apps.sample_log_source --since 2026-11-04T10:00:00Z --until 2026-11-04T10:10:00Z --trace-id t-1002
uv run --directory dogfood python -m apps.sample_log_source --since 30m --until now --json
```

## 运行示例

```bash
uv run --directory dogfood python -m apps.sample_log_source --since 2026-11-04T09:00:00Z --until 2026-11-04T11:00:00Z --grep failed --json
```

预期：stdout 一行 JSON envelope，`outputs` 里只有 `order-service` 那条 `refund 42 failed` 日志；
加 `--out artifacts/evidence/<run_id>/logs/order.log` 时同时写出文件，再用 `tuner-evidence attach --log` 挂到任务上。
