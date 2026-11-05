---
name: health-check
version: 3.0.0
group: availability
description: Checks which basics and which capability prerequisites this TestPilot workspace still lacks - UI and API URLs, database connections, test accounts in data/, browser channel, source roots, API docs, DDL, backend log port, wiki - from `tuner-workspace doctor --json` (core checks plus per-capability readiness), then fills the gaps through maintain-config, dump-ddl, create-app, maintain-wiki, tuner-task ask, or upgrade-framework. Use when the user says health-check, 体检, 还差什么配置, 开场配置, 配置基础信息, or has just scaffolded a workspace.
---

# health-check — 配置体检

回答两个问题：

1. **仓库的基础配置齐不齐**（`core`）：地址、数据库、账号、浏览器通道、目录、DNA、hooks。
2. **每项功能需要的配置齐不齐**（`capabilities`）：执行测试单、探索系统、读源码、查后端日志……各自要哪些配置，缺哪些。

先用确定性的 `tuner-workspace doctor` 看清，再问用户打算用哪些功能，只补那些功能的缺口。

## Scope

- **读**：`uv run tuner-workspace doctor --json`、`uv run tuner-config show --json`。
- **委托**：配置、账号、源码路径、API 文档 → `maintain-config`；表结构 → `dump-ddl`；知识 → `maintain-wiki`；
  端口实现 → `create-app`；DNA → `upgrade-framework`；只能人定的通道 → `tuner-task ask`。
- **不写**：密码 / token / Cookie 进任何入库文件或对话。不 `git add` 本机文件。本 skill 自己不写文件。

## 在哪执行

1. 目标目录要有 `INDEX.project.md` 和 `config/env.py`。没有就停，让用户先 `tuner-init scaffold <dir>`。
2. 仓库根有 `tuner_testkit/project.py` 时这里是平台仓：先问目标目录（下游仓），之后命令都加 `--directory <目标>` 或在目标目录执行。

## 1. 体检

```bash
uv run tuner-workspace doctor --json
```

JSON 里：`checks[]`（每条带 `tier`：`core` / `feature`）、`summary_core`、`summary_feature`、`capabilities[]`、顶层 `ok`（只看 core）。

向用户给两张表，不出现密码：

- **基础项**（`tier=core`）：检查项、状态（ok / info / warn / missing / error）、说明、下一步。
- **功能就绪度**（`capabilities`）：功能、依赖它的 skill / agent、就绪与否、缺什么（`blockers[]` 的 `id` + `detail`）。

## 2. 基础项（都要有）

| doctor 检查 | 含义 | 处理 |
| --- | --- | --- |
| `layout.legacy` / `layout.dirs` / `layout.index` | 目录结构齐全、无旧位置 | `uv run tuner-workspace migrate knowledge` 给用户看计划，同意后 `--apply`，再 `tuner-workspace index render` |
| `config.env_local` | 有本机配置 `config/env_local.py` | `maintain-config`（从 `config/env_local.py.example` 起） |
| `config.ui_url` | 前端地址 `TEST_UI_BASE_URL` 已填、不是模板示例 | `maintain-config`（只要 host，不要路径） |
| `config.api_url` | 后端 / 网关地址 `TEST_BASE_URL` 已填、不是模板示例 | `maintain-config` |
| `config.databases` | 数据源有、不是占位 | `maintain-config`（每个别名：类型、host、port、user、库名；密码写本机文件） |
| `config.db_connect.<别名>` | 数据源能连上（`doctor --check-db`，用户同意才跑） | 连接失败 → `maintain-config` |
| `config.validate` | `tuner-config validate` 通过 | 读 findings → `maintain-config` |
| `data.accounts` | `data/sut-accounts.local.yaml` 已写、无 `replace-me`、有 `role` | `maintain-config`（格式见 `docs/spec/data-syntax.md`；密码只写本机文件） |
| `channels.browser` | 浏览器启动方式已选 | 问用户用 Playwright MCP 还是 Cursor 浏览器（`docs/spec/browser-channel.md`），交 `maintain-config` 写 `CHANNELS.browser` |
| `dna.version` | DNA 与已安装 kit 一致 | warn / missing → `upgrade-framework` |
| `hooks.git` | git hooks 已启用 | 告诉用户执行 `git config core.hooksPath tools/git-hooks`（不替用户改 git 配置） |

## 3. 功能就绪度（按用户要用的功能补）

`capabilities[]` 的 `id` 与依赖：

| capability | 功能 | 依赖的检查 |
| --- | --- | --- |
| `assets` | 写用例、测试单、测试设计、缺陷 | `layout.dirs` |
| `ui-run` | 浏览器点击执行测试单 / 测试设计 | `config.ui_url`、`data.accounts`、`channels.browser` |
| `explore` | 探索被测系统（`sut-self-learning`） | `config.ui_url`、`data.accounts`、`channels.browser` |
| `api-auto` | 接口自动化（behave / pytest） | `config.api_url`、`data.accounts` |
| `db-check` | 数据核对、造数 | `config.databases` |
| `ddl` | 导出表结构（`dump-ddl`） | `config.databases`、`knowledge.ddl` |
| `source` | 读源码生成设计知识（`sut-source-to-design`） | `knowledge.source_roots` |
| `api-docs` | 导入接口文档（`tuner-openapi-import`） | `knowledge.api_docs` |
| `backend-log` | 查后端日志做取证 | `ports.log-source` |
| `wiki` | 沉淀需求与业务知识（`maintain-wiki`） | `knowledge.wiki` |

做法：

1. 列出每项功能是否就绪，并问用户**这一轮打算用哪些功能**（可多选，可全跳过）。
2. 只处理被选功能的 `blockers`，一次把要问人的问题问完。处理表：

| blocker | 处理 |
| --- | --- |
| `knowledge.source_roots` | 问用户源码本机路径（可多个），交 `maintain-config` 写 `KNOWLEDGE.source_roots`（`env_local.py`，不入库） |
| `knowledge.api_docs` | 问 API 文档 URL 或仓库路径，交 `maintain-config` 写 `KNOWLEDGE.api_docs`；原件放 `knowledge/raw/`，有 OpenAPI 时提示 `tuner-openapi-import` |
| `knowledge.ddl` | 数据源配好后问用户是否导出，同意后按 `dump-ddl`；`--all` 必须明确同意 |
| `knowledge.wiki` / `trace.requirements` | 用户有需求文档或业务说明时走 `maintain-wiki` ingest |
| `ports.log-source` | 见 §4 |
| `ports.*` = error | 读 `problems`：绑定指错或 app 不满足契约 → `create-app` 修 app，或 `maintain-config` 改绑定 |
| 其余（地址、账号、数据源、浏览器） | 对应基础项，见 §2 |

没被选中的功能不追问，只在收口时用一行列出「未配置的功能：…」。

## 4. 后端日志通道（端口 `log-source`）

kit 只定契约（`docs/spec/ports.md`），实现是本仓的 app。

1. 用户在场且能马上回答：问通道是 `ssh-dir` / `log-api` / `rancher-api` / `skip` 中哪一种，以及不含密钥的定位（目录、path、命名空间、工作负载）。
   - 选了通道 → `create-app` 按契约写 `apps/<sut>_logs/`（`port="log-source"`），`maintain-config` 写 `PORTS` 与 `OPS`（密钥由用户给，写进本机文件）。
   - 选 `skip` → 告诉用户日志相关取证本轮不做，不再追问。
2. 用户现在答不了：建任务并异步提问，**回答前不选通道、不写实现**：

   ```bash
   uv run tuner-task create --type explore --title "开场体检：后端日志通道"
   uv run tuner-task ask --task <TASK-ID> --topic sut-log-source --prompt "仓库没有写明后端日志从哪取"
   ```

## 5. 收口

1. 再跑一次 `uv run tuner-workspace doctor --json`，用同样两张表回复：每项是已处理、本来就有、用户跳过、等人回答。
2. 顶层 `ok` 为真（`summary_core` 无 error / missing）才说基础可以开工；功能是否可用以各 capability 的 `ready` 为准。
3. 下一步建议：写用例走 `maintain-testcases`；执行测试单走 `execute-testsheet`；学习被测系统走 `sut-self-learning`。
4. 改动过入库文件（如 `config/env.py` 的团队约定）才需要提交；提醒用户 `config/env_local.py`、`config/.active_env`、
   `data/*.local.yaml` 在 gitignore，不要暂存。

## Hard rules

- 用户没说的 URL、主机、路径、表名保持空白，不拿示例值充数。
- 对话里复述配置时，密码和令牌说「已写入本机文件」。
- 功能没被选中就不追问它的配置；功能被选中而缺配置，要补到就绪或让用户明确跳过。
- 日志通道没经人确认前，不选 SSH、日志接口或 Rancher，不写取日志实现。
