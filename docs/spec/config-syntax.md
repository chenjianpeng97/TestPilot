---
name: config-syntax
version: 1.0.0
description: config/ 只回答「在哪、用什么」：被测系统环境、运维通道、端口绑定、执行通道、知识位置。字段、覆盖顺序、密钥边界与校验。
---

# 配置规范（config-syntax）

> `config/` 是「在哪、用什么」的唯一来源。LLM 读配置只用 `tuner-config show --json`（密钥打码）；
> 改配置走 skill `maintain-config`，改完跑 `tuner-config validate`。schema 的确定性实现在 `tuner_testkit/config_schema.py`。

## 1. 文件与覆盖顺序

| 文件 | 入库 | 放什么 |
| --- | --- | --- |
| `config/env.py` | 是 | 结构与占位、团队约定（`CHANNELS`、`PORTS`、`KNOWLEDGE.api_docs`），**无密钥** |
| `config/env_overlay.py` | 是（可选） | 额外数据源别名与类型、团队约定覆盖，无密钥 |
| `config/env_local.py` | **否**（gitignore） | 真实地址、密码、令牌、本机路径；多套环境 `ENVIRONMENTS` |
| `config/.active_env` | 否 | 当前激活的环境名（`tuner-config use <name>` 写入） |
| `config/env_local.py.example` | 是 | `env_local.py` 的模板 |

后者覆盖前者：`env.py` → `env_overlay.py` → `env_local.py`（顶层的 workspace 级段 + 激活环境的 profile）→ 环境变量
（`TUNER_DB_<ALIAS>_*`、`TEST_BASE_URL`、`TEST_UI_BASE_URL`）。
激活环境：`TUNER_ENV` > `config/.active_env` > `env_local.ACTIVE_ENV` > `ENVIRONMENTS` 唯一的键。

## 2. 分类

### 2.1 被测系统环境（每个环境一套，写在 `ENVIRONMENTS.<name>`）

| 键 | 类型 | 含义 |
| --- | --- | --- |
| `TEST_UI_BASE_URL` | str | 前端地址（仅 host）。空则沿用 `TEST_BASE_URL` |
| `TEST_BASE_URL` | str | 后端 / API 网关地址（仅 host） |
| `DATABASES` | `{alias: {type, host, port, user, password, database, schema?}}` | 数据源；按别名合并。`type` = `mysql` / `sqlserver` / `postgres` |

### 2.2 运维通道 `OPS`（每个环境一套）

`{通道名: {…}}`，例如 `rancher`、`ssh`、`log_platform`、`local_logs`。kit 不解释内容，**只给端口适配器读**
（`tuner_testkit.config.load_project_env().OPS`）；键名由适配器的 README 约定。地址与密钥都只写在 `env_local.py`。

### 2.3 端口绑定 `PORTS`（workspace 级，入库）

`{端口名: "apps.<name>"}`。端口契约见 `docs/spec/ports.md`；被绑定的 app 必须在 `apps/<name>/tool.py` 里声明
`@tool(..., port="<端口名>")` 并满足契约，`tuner-config validate` 检查。

### 2.4 执行通道 `CHANNELS`（workspace 级，入库；本机可在 `env_local.py` 顶层覆盖）

| 键 | 取值 | 含义 |
| --- | --- | --- |
| `browser` | `playwright-mcp`（默认）/ `cursor-browser` | 前端操作走哪个浏览器通道，见 `docs/spec/browser-channel.md` |

### 2.5 知识位置 `KNOWLEDGE`

| 键 | 写在 | 含义 |
| --- | --- | --- |
| `api_docs` | `env.py` | API 文档 URL 或仓库路径列表（原件放 `knowledge/raw/`）。有 OpenAPI 时用 `tuner-openapi-import` 冻结接口 |
| `source_roots` | `env_local.py` | 被测系统源码的本机路径列表（`sut-source-to-design` 读） |
| `wiki` | `env.py` | wiki 根目录，默认 `knowledge/wiki` |

### 2.6 不属于 config 的

- 账号本身属于数据层：`data/sut-accounts.local.yaml`（角色、权限，见 `docs/spec/data-syntax.md`）；config 只引用 `account_id`。
- 测试数据、知识正文、DNA。

## 3. 示例

`config/env.py`（入库，节选）：

```python
CHANNELS = {"browser": "playwright-mcp"}
PORTS = {"log-source": "apps.acme_logs"}
KNOWLEDGE = {"api_docs": ["knowledge/raw/api/openapi.json"], "source_roots": [], "wiki": "knowledge/wiki"}
OPS: dict = {}
```

`config/env_local.py`（不入库，节选）：

```python
KNOWLEDGE = {"source_roots": ["D:/src/acme-backend"]}
ENVIRONMENTS = {
    "uat": {
        "TEST_UI_BASE_URL": "https://uat.acme.example",
        "TEST_BASE_URL": "https://uat-api.acme.example",
        "DATABASES": {"main": {"host": "10.0.0.8", "user": "qa", "password": "…", "database": "acme"}},
        "OPS": {"rancher": {"url": "https://rancher.acme.example", "token": "…", "namespace": "acme-uat"}},
    },
}
```

## 4. 工具

| 命令 | 作用 |
| --- | --- |
| `tuner-config show` / `show --json` | 激活环境、两个 URL、数据源别名、`CHANNELS`、`PORTS`、`KNOWLEDGE`、`OPS`（密钥打码，占位标 `<placeholder>`） |
| `tuner-config use <name>` | 切换激活环境 |
| `tuner-config validate [--json]` | schema、残留占位、入库文件里的疑似密钥、`env_local.py` 是否被 git 跟踪、`PORTS` 绑定与契约、`CHANNELS` 取值、源码根与 API 文档路径 |

## 5. 禁止

- 在 `env.py` / `env_overlay.py` 写真实密码、令牌（`validate` 用语法树扫描）。
- 把 `env_local.py`、`.active_env`、`data/*.local.yaml` 放进暂存区。
- 在任务、提问、changelog、wiki、对话总结里复述密钥：说「已写入本机文件」。
