---
name: maintain-config
version: 1.0.0
group: availability
description: Reads and edits the workspace config (SUT environments and URLs, databases, test account, OPS channels such as Rancher or SSH, PORTS bindings to workspace adapter apps, CHANNELS such as the browser channel Playwright MCP vs Cursor browser, KNOWLEDGE locations such as API docs and source roots) and the local accounts file, then validates with tuner-config validate. Use when the user asks to 配置环境, 改地址, 加数据库, 切换环境, 换浏览器通道, 绑定端口, 配置日志通道参数, 登记源码路径或 API 文档, or when health-check hands over a config gap.
---

# maintain-config — 用 LLM 管理配置

`config/` 只回答「在哪、用什么」。字段与覆盖顺序见 `docs/spec/config-syntax.md`；schema 实现在 `tuner_testkit/config_schema.py`。

## Scope

- **读**：`uv run tuner-config show --json`（密钥已打码，占位显示 `<placeholder>`）、`docs/spec/config-syntax.md`。
- **写**：`config/env.py`（团队约定，入库，无密钥）、`config/env_overlay.py`（新数据源别名与类型，入库）、
  `config/env_local.py`（本机，gitignore）、`data/sut-accounts.local.yaml`（本机账号，gitignore）、`config/.active_env`（经 `tuner-config use`）。
- **不写**：密钥进入库文件、任务、提问、changelog、wiki、对话。不暂存 `env_local.py` / `.active_env` / `*.local.yaml`。

## 1. 先看现状

```bash
uv run tuner-config show --json
uv run tuner-config validate --json
```

`env_local: false` 时从模板起：`config/env_local.py.example` 复制成 `config/env_local.py`（模板不在就按 config-syntax §3 的形状新建）。

## 2. 改哪里

| 用户要改 | 写到 | 说明 |
| --- | --- | --- |
| 前端 / 后端地址、数据源连接 | `env_local.py` → `ENVIRONMENTS.<env>` 的 `TEST_UI_BASE_URL` / `TEST_BASE_URL` / `DATABASES` | 只要 host，不要路径 |
| 新增一套环境 | `env_local.py` → `ENVIRONMENTS` 加一项，然后 `uv run tuner-config use <env>` | 生产类名字会打 warning，按用户选择执行 |
| 新数据源别名（如第二个库） | 类型写 `config/env_overlay.py`（无密码），连接写 `env_local.py` 该环境的 `DATABASES` | |
| Rancher / SSH 跳板 / 日志平台 | `env_local.py` → `ENVIRONMENTS.<env>.OPS.<通道>` | 键名按适配器 README；密钥只在这里 |
| 端口绑定 | `config/env.py` → `PORTS = {"<端口>": "apps.<name>"}` | 只绑定已存在且声明了同名 `port` 的 app；没有就先 `create-app` |
| 浏览器通道（团队默认） | `config/env.py` → `CHANNELS["browser"]` | `playwright-mcp` 或 `cursor-browser`（`docs/spec/browser-channel.md`） |
| 浏览器通道（只改本机） | `env_local.py` 顶层 `CHANNELS = {"browser": …}` | |
| API 文档 | `config/env.py` → `KNOWLEDGE["api_docs"]` | URL 或仓库路径；原件放 `knowledge/raw/` |
| 源码本机路径 | `env_local.py` 顶层 `KNOWLEDGE = {"source_roots": [...]}` | 本机路径不入库 |
| 探索 / 执行账号 | `data/sut-accounts.local.yaml`（模板 `data/sut-accounts.example.yaml`） | 每个账号写 `id`、`role`、`permissions`（`docs/spec/data-syntax.md`） |

编辑规则：

- 只改用户点名的项；已填的值不动。模板环境（仍含 `CHANGE_ME`）在用户给出真实值后整段替换。
- 用户没给的键不要写，也不要留 `...`。
- 端口通道还没经人确认（`tuner-task ask` 未答）时，不往 `PORTS` / `OPS` 填猜测值。

## 3. 校验

```bash
uv run tuner-config validate
```

有 `error` 就修到没有；`warn` 逐条告诉用户（例如仍是占位、源码路径不存在）。改了 `PORTS` 时再跑
`uv run tuner-workspace doctor --json`，确认 `ports.<端口>` 为 `ok`。

## 4. 收口

- 用打码的状态表回复：改了哪个环境的哪些键、值是否「已写入本机文件」。路径用仓库相对路径。
- 入库的改动只有 `config/env.py` / `config/env_overlay.py`：提交 scope 用 `config`（如 `chore(config): bind log-source port`）。
- 提醒用户本机文件在 gitignore。

## Hard rules

- 对话里不复述密码、令牌：说「已写入本机文件」。
- `env.py` 里出现真实密钥时 `tuner-config validate` 会报 `committed.secret`：立刻移到 `env_local.py`。
- 不为了让校验通过而填示例地址或假密码。
