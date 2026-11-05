---
name: browser-channel
version: 1.0.0
description: 前端操作的浏览器通道（Playwright MCP / Cursor 浏览器）由 config CHANNELS.browser 选择；各通道怎么操作、怎么落证据。
---

# 浏览器通道（browser-channel）

> 前端操作走哪个浏览器是**配置**，不是写死在 skill 里的约定。读 `tuner-config show --json` 的
> `channels.browser`，取值 `playwright-mcp`（默认）或 `cursor-browser`；改用 `maintain-config`。
> `tuner_testkit.page_test`（PageDriver 回放、`page_test run`）是代码里的 Playwright，不受此配置影响。

## 1. 通道对照

| 能力 | `playwright-mcp` | `cursor-browser` |
| --- | --- | --- |
| MCP 命名空间 | Playwright MCP（`browser_navigate` / `browser_snapshot` / `browser_click` …） | Cursor 内置浏览器（`browser_navigate` / `browser_snapshot` / `browser_click` / `browser_cdp` …） |
| 页面结构 | `browser_snapshot` | `browser_snapshot` |
| 截图 | `browser_take_screenshot` | `browser_take_screenshot` |
| 网络请求 | `browser_network_requests` / `browser_network_request` | `browser_cdp` 的 `Network.enable` 后按事件采集，或 `Runtime.evaluate` 读 `performance.getEntriesByType("resource")`（无响应体） |
| 适合 | explore 抓接口、冻结 api_objects（证据最完整） | 在 IDE 里边看边点的执行、截图取证；接口证据较弱 |

## 2. 证据落盘（两种通道一致）

1. 把网络记录整理成 JSONL（每行一次请求：`method`、`url`、`status`，可选请求头 / 请求体 / 响应体），写到临时文件。
2. `tuner-evidence persist --run-id <id> --scenario <scenario> --network <jsonl> [--screenshot …] [--task-id …]`，
   落到 `artifacts/evidence/<run_id>/`，脱敏由工具完成。
3. 只需要截图或单个接口 JSON 时用 `tuner-evidence attach`。

`cursor-browser` 拿不到响应体时，`freeze-api-objects` 只能冻结请求契约；需要响应断言的切片请切回 `playwright-mcp`
（`maintain-config` 改 `CHANNELS.browser`，本机覆盖写在 `env_local.py` 顶层）。

## 3. skill 的写法

- 第一步读 `channels.browser`，在 inbox / 报告里写明本次用的通道。
- 动作描述用通道无关的说法（打开页面、读结构、点击、截图、取网络记录），再按上表映射工具名。
- 配置的通道在当前 IDE 不可用（MCP 未连接）时，停下来告诉用户，不要静默换通道。
