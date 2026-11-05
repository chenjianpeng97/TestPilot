---
name: create-action-word
version: 1.2.0
group: internal
description: Creates or updates action words under packages/action_words/ following action-words-syntax.md. Use when adding DB seed/assert, API request/assert, or UI action/assert business actions, or when migrating ad-hoc test logic (SQL scripts, step bodies) into reusable action words.
---

# Create / Maintain Action Words

## Scope

- **Primary goal**: turn a business action (造数 / 断言 / 接口编排) into a
  registered, standalone-runnable action word.
- **Write scope**: `packages/action_words/**`（必要时步骤层接线：
  `tests/features/*_steps/**`）。
- **Must follow**: `docs/spec/action-words-syntax.md`（模板细节以 spec 为准）。

## Before creating (reuse first)

1. `uv run python -m tuner_testkit.action_words list` — 确认没有同义 word；有则
   优先扩展其 Params（兼容性新增），而不是新建。
2. 明确类别与 `word_id = "<category>.<snake_name>"`；一个模块默认一个 word，
   同一聚合的强相关 word 可同模块。
3. **确定目标数据源**：框架支持 MySQL / SQL Server / PostgreSQL 共存，业务数据长期
   存在哪个库就在类上声明哪个别名（`datasource = "main"` /
   `"sqlserver"` / `"postgres"` / ...，别名与类型见 `config/env.py`
   `DATABASES`）；默认 `"main"`。
4. 造数类：先在 `knowledge/ddl/<别名>/<table>.sql` 核对列名（generated/computed
   列**不得**出现在插入列表；缺 DDL 时先走 `/dump-ddl` 或
   `python -m tuner_testkit.apps.dump_ddl <table> --datasource <别名>`），列名固化为模块级
   `*_COLUMNS` 元组。
5. API 类：只编排 `packages/api_objects/**` 冻结资产（`_internal/api.load_api`），
   缺资产时先走 freeze-api-objects / `tuner-recorder` 合录 / `tuner-api-recorder` 代理
   （`python -m tuner_testkit.apps.recorder` / `api_recorder`），**不得**手写 request 契约。

## Hard template rules (enforced)

`@register`（导入期）与 `packages/tests/test_action_word_template.py`（回归期）
会拦截违规：

- 类与模块 docstring 描述业务/前置条件/副作用（非一行占位）；
- `word_id` / `name`（中文业务名）/ `category` 必填，word_id 前缀与 category 一致；
- `Params`：pydantic v2，`extra="forbid"`，**每个字段**带类型 + `Field(description=中文)`（工作台表单 label）；
- `Result` 继承 `ActionResult`，业务字段同样带 description；
- `example_params` 非空且能通过 `Params.model_validate`；
- `run(params)` 带完整类型标注；
- **造数类必须登记 `cleanup`**（`TableRows` 逐表行 id）；
- 断言类失败抛 `AssertionError`（含定位信息），异步数据用 `_internal/wait.wait_until` 轮询；
- 资源一律经 `self.ctx`（DB 用 `self.db`，即
  `ctx.get_db(cls.datasource)`；API 用 `ctx.api_token`），不自建连接；
- 源码 / example / 日志中不得出现真实 token、密码、Cookie。
- 工作台只扫 `packages/action_words/{db_seed,db_assert,api_request,api_assert,ui_action,ui_assert}/`
  （含子目录 `*.py`）上的 `@register`；没有入口文件 = 工作台当它不存在。
  **必须用 kit 的 register**：`from packages.action_words import register`，且
  `__init__.py` re-export `tuner_testkit.action_words.register`（或本仓 register 双写 kit）。
  本仓自建 registry、不接到 kit 的 `@register` **不会**进工作台。
  默认 `visibility = "workbench"`，`local` 不进目录。模块顶层不得连库 / 读 `env_local`。

## Recommended structure (db_seed)

- 纯构建函数 `build_<x>_rows(params, ids) -> dict[table, rows]`（无 DB，便于离线单测）
  与 `run` 内 `bulk_insert` 落库分离；
- 默认值与真实主数据样例同源（`_internal/params.py`）；随机值用
  `tuner_testkit.fake`（`_internal/generators` 只是 re-export），id 用 `_internal/ids.default_id_generator`；
- 跨 word 复用的行结构放 `packages/action_words/models.py`；
- 文件末尾**必须**提供 `if __name__ == "__main__"` 手工改参入口：显式构造
  `Params(...)`（关键业务字段逐个列出，带行内注释），`with ActionContext()`
  执行并打印 Result JSON，保证 `python -m <module>` 可独立造数。
- **DB 方言跟随 `datasource` 声明**（`tuner_testkit.db.DbClient`，底层 SQLAlchemy
  引擎自动路由 pymssql / pymysql / psycopg，值一律 `%s` 占位）：
  - 造数走 `_internal/db.bulk_insert`（标识符按 `client.dialect` 自动
    `[table]` / `` `table` `` / `"table"`）；
  - MySQL：禁止 `[ident]`、`TOP`、`GETDATE()`、`MERGE`；探测用 `LIMIT`，时间用 `NOW()`；
  - SQL Server：禁止反引号、`LIMIT`、`INSERT IGNORE`、`ON DUPLICATE KEY`、
    `NOW()` / `IFNULL`；探测用 `TOP`，时间用 `GETDATE()`；
  - PostgreSQL：禁止 `[ident]`、反引号、`TOP`、`ON DUPLICATE KEY`；探测用 `LIMIT`，
    时间用 `NOW()` / `CURRENT_TIMESTAMP`，冲突用 `ON CONFLICT`。

## Changelog（追溯）

新建或修改词条后，在同一个提交里：

```bash
uv run tuner-workspace changelog append --area action_words --skill create-action-word \
  --action <新建|更新|删除> --items <word_id> --reason "<一句话>"
```

列名来自 `knowledge/ddl/<datasource>/<table>.sql`，不要凭空写列。

## Verify (must pass)

1. `uv run python -m tuner_testkit.action_words describe <word_id>` — schema/样例正常导出；
2. `uv run pytest packages/tests/test_action_word_template.py -q`；
3. 有环境时 `... run <word_id> --example` 冒烟，确认 cleanup 登记完整；
4. 若接线 behave：`uv run behave --stage api --dry-run <feature>` 步骤全匹配。

## Output checklist

- 新建/更新的 word 列表（word_id → 文件路径）；
- 是否复用了既有 word / models / _internal 工具（reuse-first 证据）；
- cleanup 覆盖的表清单（造数类）；
- 未走 CLI 冒烟时说明原因（如无目标环境）。
