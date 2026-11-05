---
name: create-app
description: Scaffolds a new standalone workspace tool under apps/ that reuses tuner_testkit plus this repo's packages business assets, following apps-authoring-syntax.md - including port adapters that implement a kit port contract such as log-source (backend logs via SSH / log API / Rancher). Use when the engineer needs an on-demand test tool (data generator, checker, exporter, capture/enrichment) or a person has answered which channel a port should use. Do not scaffold into tuner_testkit/apps/.
version: 1.3.1
group: availability
---

# Create App — 按需开发一个独立工具

TestPilot 鼓励自定义 apps：团队差异大的事情不等 kit 提供，写进本仓 `apps/`，LLM 通过 catalog 发现并调用。
其中一类是**端口适配器**：kit 定契约（`docs/spec/ports.md`），本仓写实现。

## Scope

- **目标**：把「利用 tuner_testkit + 本仓 packages / knowledge 按需开发一个可独立运行的工具」落成规范资产。
- **写范围**：`apps/<name>/**`。**不要**往 `tuner_testkit/apps/` 脚手架。
- **必须遵循**：`docs/spec/apps-authoring-syntax.md`、`.cursor/rules/apps-authoring.mdc`（创建期）、
  `.cursor/rules/apps-handover.mdc`（完成期）；端口适配器另遵循 `docs/spec/ports.md`。

## Before creating（复用优先）

1. `uv run tuner-workspace catalog --out -` 看 kit 工具（`tuner-*`）与本仓 `apps/` 是否已有同类工具。能扩展就别新建。
2. 明确输入 / 输出去向：原始知识 → `knowledge/`；可复用资源 → `packages/`；运行产出 → `artifacts/`。
3. 明确要复用哪些 kit 能力：DB(`tuner_testkit.db`)、日志(`tuner_testkit.logging`)、配置(`tuner_testkit.config`，
   运维通道读 `load_project_env().OPS`)、HTTP(`tuner_testkit.api_test`)、表格(`tuner_testkit.excel`)、脱敏(`tuner_testkit.apps.evidence.persist.redact_text`)。
4. **端口适配器**额外确认：
   - 端口名与契约（`docs/spec/ports.md`；`tuner_testkit.ports.PORT_CONTRACTS`）。
   - 通道已经由人确认（`tuner-task answer` 的结论，或用户本次明确说了）。**没确认就停**，走 `tuner-task ask`。
   - 通道需要的 `OPS` 键名（地址、命名空间、目录、令牌）：只定键名，值由 `maintain-config` 写进本机文件。

## 脚手架结构（包形式）

```text
apps/<name>/
├── __init__.py
├── __main__.py        # from .cli import main; raise SystemExit(main())
├── cli.py             # argparse：build_parser() + main()；每个参数有 help；带 --json
├── tool.py            # import-safe：用 @tool 装饰 build_parser（工作台 / catalog）
├── <core>.py          # 纯逻辑，尽量可离线单测
├── README.md          # 交接文档 + metadata-conventions front-matter
└── tests/             # 离线单测
```

单文件工具（如仅一个脚本）可直接 `apps/<name>.py`，但交接文档仍需写进 `apps/README.md`。

## 端口适配器模板（以 log-source 为例）

取数逻辑由各团队自己实现，骨架如上。

- `tool.py`：

  ```python
  build_parser = tool(
      tool_id="<sut>_logs", name="<系统> 后端日志", module="apps.<sut>_logs",
      summary="从 <通道> 读后端日志（log-source 端口）", port="log-source",
      readme_path="apps/<sut>_logs/README.md", hide_params=("out",),
  )(_build_parser)
  ```

- `cli.py`：契约参数 `--since --until --json`，可选 `--service --grep --trace-id --limit --out`；
  通道不可用返回 3；参数错误返回 2；`--json` 输出 envelope，`outputs[]` 每项 `{ts, level, service, line}`。
- `<core>.py`：从 `OPS["<通道>"]` 读连接信息，按时间窗取日志，每行过 `redact_text` 再返回。不打印连接信息。
- `README.md`：写清实现的端口、通道、读取的 `OPS` 键名（不写值）、退出码。
- 写完交给 `maintain-config` 在 `config/env.py` 写 `PORTS = {"log-source": "apps.<sut>_logs"}`。

## Hard rules（强制）

- 支持 `python -m apps.<name>`；参数用 `argparse`。不要做成 `python -m tuner_testkit.apps.<name>`。
- DB 只走 `tuner_testkit.db.DbClient`；日志只走 `tuner_testkit.logging`；凭据只从 config + 环境变量取；
  **禁止** `print` 诊断输出、直连驱动、硬编码 DSN / 地址 / 令牌、SQL 拼接、自建日志文件。
- 覆盖式生成 `knowledge/**` / `assets/**` / `packages/api_objects/**` / `packages/page_objects/**` 的工具，运行结束必须向对应库 changelog 追加一行。
- 不得被 `tests/` import；不得写入敏感值；破坏性操作默认 dry-run / 只读，`@tool(..., destructive=True)`。
- 只读端口（`log-source`）不得标 `destructive`；会写外部系统的端口必须默认 dry-run。
- `tool.py` 及其 import **禁止**顶层 import DB / Playwright / mitmproxy / SSH 客户端。没有 `apps/<name>/tool.py` + `@tool` = 工作台当它不存在。
- `--json` 时 stdout 打印 envelope：`status / outputs[] / artifacts[] / log_path`（见 apps-authoring-syntax §7）。
- README 写完后立刻 `uv run tuner-workspace meta stamp apps/<name>/README.md --kind app`（不要手填邮箱）。

## 交接文档（完成期必产出）

`apps/<name>/README.md` 写清：**需求背景 / 试用场景与前置条件 / 运行方式(含依赖 extra) / 运行示例(可复制命令 + 预期产出)**。
然后 `uv run tuner-workspace index render`，让工具进 `INDEX.project.md` 第 3 节（端口适配器进 3.1）。

## Verify

1. `python -m apps.<name> --help` 正常输出用法。
2. `tuner-workspace catalog` 的 `tools[]` 出现该 `tool_id`，且 `params_schema.properties` 每项有 `description`；端口适配器的 `port` 正确。
3. 离线单测 `uv run pytest apps/<name>/tests -q`。
4. 端口适配器：绑定后 `uv run tuner-config validate` 无 `ports.*` error，`uv run tuner-workspace doctor --json` 的 `ports.<端口>` 为 `ok`。
5. 有环境时跑一条示例命令，确认产出位置与 changelog 追加正确。

## Output checklist

- 新建/更新的文件清单（含入口与交接文档）。
- 复用了哪些 tuner_testkit 模块 / 本仓 packages（reuse 证据）。
- 产出去向与 changelog 是否接入；端口与 `OPS` 键名。
- `INDEX.project.md` 是否已渲染。
