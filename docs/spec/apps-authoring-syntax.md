# apps 工具编写规范（apps-authoring-syntax）

> `apps/` 存放 **SUT 私有**、可独立运行的测试工具（`python -m apps.<name>`），也是**端口适配器**的家（§9）。
> **平台**工具在 `tuner_testkit.apps`（`tuner-recorder`、`tuner-dump-ddl` 等），不要再拷进下游 `apps/`。
> 领域动作（造数 / API / UI）留在 `packages/`（action words 经 `@register` 自动进入目录与工作台），不经 apps 冒充。
> 供 `apps-authoring.mdc`（创建期）与 `apps-handover.mdc`（完成期）引用。
>
> **鼓励自定义 apps**：团队之间差异大的事情（取后端日志、连 Rancher、自定义 Excel 导出）不要等 kit 提供，按本规范写进本仓 `apps/`，LLM 通过 catalog 发现并调用。

## 1. 目录与入口

单文件工具或包均可：

```text
apps/                            # 仅 SUT 私有工具
├── __init__.py
└── <your_tool>/
    ├── __init__.py __main__.py
    ├── cli.py                   # argparse build_parser() + main()
    ├── tool.py                  # import-safe @tool 清单（工作台 / catalog 读取）
    ├── README.md                # 交接文档（front-matter 见 metadata-conventions）
    └── tests/

# 平台工具（已安装的 tuner-testkit，不要写进本仓 apps/）
# tuner_testkit/apps/dump_ddl.py
# tuner_testkit/apps/recorder/
# tuner_testkit/apps/dna/
```

- 包形式必须支持 `python -m apps.<name>`（提供 `__main__.py`）。仓库根须有
  `apps/__init__.py`。平台 CLI 走 `python -m tuner_testkit.apps.<name>` / `tuner-*`。
- 需要在仓库根外可运行时，用 `tuner_testkit.project.project_root()`（禁止 kit `__file__` 当 SUT 根）。

## 2. 必须复用 kit 运行库（不得重造轮子）

- **DB** → `tuner_testkit.db.DbClient`（多数据源，`config/env.py` 的别名）。禁止 `pymysql` /
  `pymssql` / `psycopg.connect`、硬编码 DSN、SQL 字符串拼接。见 `.cursor/rules/packages-db.mdc`。
- **日志** → `tuner_testkit.logging`（`log_info/log_warn/log_error/log_data_setup/...`）。禁止 `print`、
  stdlib `logging`、自建日志文件。见 `.cursor/rules/packages-logging.mdc`。
- **配置/凭据** → `config/env.py`（`tuner_testkit.config` 解析 `env_local` 命名环境；
  再叠加 `TUNER_DB_*` / `TEST_*` 环境变量），不在代码里写死。运维通道（Rancher、SSH、日志平台）读
  `tuner_testkit.config.load_project_env().OPS`，字段见 `docs/spec/config-syntax.md`。
- **HTTP/API** → 复用 `tuner_testkit.api_test` / `packages.api_objects`；表格解析用 `tuner_testkit.excel`。

## 3. 产出去向

- **原始知识回填** → `knowledge/`（如 DDL 落 `knowledge/ddl/<datasource>/`）。
- **可复用资源** → `packages/`（如抓包冻结为 `packages/api_objects/`）。
- **自动区变更留痕**：凡是覆盖式生成 `knowledge/**`、`assets/**`、`packages/api_objects/**` 或
  `packages/page_objects/**` 的工具，运行结束**必须**向对应库的 changelog 追加一行
  （`tuner_testkit.apps._shared.changelog.append_entry(...)` 或 `tuner-workspace changelog append`，
  库与路径见 `docs/spec/metadata-conventions.md` §4），供追溯与 `maintain-index` 增量更新 `INDEX.project.md`。

## 4. 交接文档（完成期必产出）

每个工具在 `apps/<name>/README.md`（单文件工具写进 `apps/README.md` 的条目）记录：

- **需求背景**：当时为解决什么问题而造。
- **试用场景**：适用/不适用的场景，前置条件（如需要哪个数据源、是否需登录）。
- **运行方式**：完整命令（含依赖安装 extra，如 `uv sync --extra recorder`）。
- **运行示例**：一条可复制的命令 + 预期产出位置。

带 `tool.py` 的工具由 `tuner-workspace index render` 自动登记进 `INDEX.project.md` 第 3 节（端口适配器另进 3.1）。
<!-- platform-only:begin -->
平台工具（`tuner_testkit/apps/`）手工在根 `INDEX.md` 第 3 节登记一行。
<!-- platform-only:end -->

## 5. 安全与边界

- 不得写入 token / cookie / 密码 / Authorization / session 等敏感值（含产出文件与日志）。
- apps 是**独立运行**的工具，**不得被 `tests/` import**（测试复用逻辑应下沉到 `packages/`）。
- 破坏性操作（写生产库、删除文件）必须显式开关 + 默认 dry-run/只读。
- **工作台可见 vs 本地维护**：要出现在 `tuner-workspace catalog` / 工作台的工具，提供 import-safe 的
  `apps/<name>/tool.py`，用 `tuner_testkit.tools.tool` 装饰 `build_parser`（argparse → `params_schema` + `argv_plan`）。
  纯本地维护、产物直接进 git 的工具可以不写 `tool.py`，或写了但声明 `visibility="local"`。
  `tool.py` 及其 import 的模块**不得**在顶层 import DB 驱动 / 浏览器 / 代理。领域动作留在 `packages/`
  （action words 经 `@register` 自动进目录）。

## 6. 测试

- 纯逻辑（归一化、解析、代码生成）应可离线单测：可放 `packages/**/tests` 或 `apps/<name>/tests/`
  （参考 `packages/tests/test_api_objects_recording_*.py`、`tuner_testkit/apps/api_recorder/tests`）。
- 依赖真实环境的部分用参数/开关隔离，便于 CI 只跑离线单测。

## 7. `--json` 输出契约（工作台 / runner）

工作台与 `tuner-workspace run` 会把 stdout 里**最后一行 JSON 对象**当作 envelope 写入
`artifacts/runs/<run_id>/envelope.json`。约定：

```json
{
  "status": "succeeded",
  "outputs": [{"kind": "lines", "count": 2}],
  "artifacts": ["artifacts/runs/<run_id>/out.txt"],
  "log_path": null
}
```

- `status`：`succeeded` / `failed`（须与进程退出码一致：0 ↔ succeeded）。
- `outputs[]`：给人看的摘要，自由结构。
- `artifacts[]`：本次写出的文件路径（相对 workspace 根或绝对路径）。
- `log_path`：若工具自己另写了日志文件则填，否则 `null`（kit 仍会写 `stdout.log`）。
- 破坏性工具默认 dry-run；真正执行必须有显式开关。
- `create-app` 脚手架默认带 `--json` 与 `tool.py`。

## 8. 工作台入口（扫描约定）

没有入口文件 = 工作台当它不存在。不另做 `WORKBENCH.toml` 手写清单（会和 `@tool` 双源漂移）。入口就是装饰器 + 固定路径。

可见工具必须同时满足：

1. 路径是 `apps/<name>/tool.py`（平台工具是 `tuner_testkit/apps/<name>/tool.py`）；
2. `@tool(..., visibility="workbench")`（默认值）。`visibility="local"` 只走 CLI。

发现器**只**枚举上述两个 glob，不扫 `cli.py` / 其它模块。`tool.py` 及其 import **禁止**顶层 DB / Playwright / 驱动——这既是安全约束，也是扫描性能约束。工作台热路径只读目录切片（`build_directory`），不读 `assets/`、不跑 `git log`。

## 9. 端口适配器（kit 定契约，workspace 写实现）

kit 只给差异大的能力定义**端口契约**（`docs/spec/ports.md`，确定性部分在 `tuner_testkit/ports.py`），不提供实现。
本仓用一个普通 app 实现它：

1. 仓库没写明通道时先 `tuner-task ask`（如 `--topic sut-log-source`），**人回答前不选通道、不写实现**。
2. 回答后用 `create-app` 生成 `apps/<name>/`，`tool.py` 声明端口：

   ```python
   build_parser = tool(
       tool_id="acme_logs", name="Acme 后端日志", module="apps.acme_logs",
       summary="从 Rancher 读 acme-* 工作负载日志（log-source 端口）",
       port="log-source", readme_path="apps/acme_logs/README.md",
   )(_build_parser)
   ```

3. `cli.py` 提供契约要求的参数与 `--json` envelope；通道地址与密钥读 config `OPS`；输出前脱敏
   （`tuner_testkit.apps.evidence.persist.redact_text`）；只读端口不得标 `destructive`。
4. `maintain-config` 在 `config/env.py` 写 `PORTS = {"log-source": "apps.acme_logs"}`，在 `env_local.py` 的激活环境写 `OPS`。
5. `tuner-config validate` 检查绑定与契约（必填参数、只读、不在 kit 里）；`tuner-workspace doctor` 报 `ports.<端口>`；
   `INDEX.project.md` 的 `ports` 自动区列出实现。

参考实现：平台仓 `dogfood/apps/sample_log_source/`（读本地文件，离线可跑）。

