---
name: ports
version: 1.1.0
description: 端口契约：kit 定义、workspace 用自定义 app 实现的能力（目前是后端日志 log-source）。
---

# 端口契约（ports）

> TestPilot 的扩展原则（`AGENTS.md` §4）：团队之间差异大的能力，kit 只定义**端口**，不提供实现；
> 每个 workspace 按 `docs/spec/apps-authoring-syntax.md` 写一个 CLI app 作为**适配器**。
> 契约的确定性部分在 `tuner_testkit/ports.py`（`tuner-config validate`、`tuner-workspace doctor` 使用）。
>
> 端口只用于**取数通道各团队不同**的能力。内容和位置能统一的东西（用例、缺陷、需求）不是端口：
> 它们有固定目录、固定模板和维护 skill，例如缺陷库见 `docs/spec/defect-syntax.md`。

## 1. 流程

1. 仓库没写明通道（`tuner-workspace doctor` 报 `ports.<端口>: missing`）→ `tuner-task ask --topic <主题>`，任务置 `blocked`。
   **人回答前不选通道、不写实现。**
2. 人回答（`tuner-task answer`，返回 `next` 提示）→ `create-app` 按本文件契约生成 `apps/<name>/`：
   - `tool.py` 用 `@tool(..., port="<端口>")` 声明；
   - `cli.py` 提供契约要求的参数与 `--json` envelope；
   - 通道地址与密钥从 config `OPS` 读（`tuner_testkit.config.load_project_env().OPS`），不写进代码。
3. `maintain-config` 在 `config/env.py` 的 `PORTS` 绑定 `{"<端口>": "apps.<name>"}`，在 `env_local.py` 写 `OPS`。
4. `tuner-config validate` 与 `tuner-workspace doctor` 复检；`INDEX.project.md` 的 `ports` 自动区列出实现。

## 2. 通用约定

- 参数用 argparse；`--json` 时 stdout 最后一行是 envelope（`status / outputs[] / artifacts[] / log_path`，见 apps-authoring §7）。
- 退出码：`0` 成功，`2` 参数错误，`3` 通道不可用（连不上、没权限）。
- 输出前脱敏：可复用 `tuner_testkit.apps.evidence.persist.redact_text`。日志、envelope 里不出现密钥。
- 证据：给任务取证时写到 `artifacts/evidence/<run_id>/` 或用 `tuner-evidence attach --log <file> --task-id <TASK>` 挂上。
- 适配器住在 workspace `apps/`，不进 kit；kit 只升级契约，契约变化写进 `docs/changelog/TEMPLATE-*.md`。

## 3. `log-source`（stable）

按时间窗读取被测系统后端日志。提问主题：`sut-log-source`（选项 `ssh-dir` / `log-api` / `rancher-api` / `skip`）。

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `--since` | 是 | 起点：ISO 时间，或相对时间 `15m` / `2h`（之前） |
| `--until` | 是 | 终点：ISO 时间、相对时间或 `now` |
| `--json` | 是 | 输出 envelope |
| `--service` | 否 | 只要某个服务 |
| `--grep` | 否 | 只要包含该文本的行 |
| `--trace-id` | 否 | 只要带该 trace id 的行 |
| `--limit` | 否 | 最多返回多少行（默认 500） |
| `--out` | 否 | 同时把脱敏后的行写到文件 |

envelope 的 `outputs[]` 每项：`{"ts": ISO, "level": "INFO", "service": "...", "line": "<脱敏原文>"}`。
**只读**：不能标 `destructive`。参考实现骨架见 skill `create-app` 的「端口适配器模板」；取数逻辑（读文件、调日志 API、Rancher）由各团队自己写。

## 4. 新增端口

只有「各团队取数方式不同、kit 无法给出统一实现」的能力才做成端口。先在本文件写契约（参数、输出、只读与否、提问主题），
再在 `tuner_testkit/ports.py` 的 `PORT_CONTRACTS` 登记，发版写 TEMPLATE 说明。会写外部系统的端口必须标 `destructive` 且默认 dry-run。
