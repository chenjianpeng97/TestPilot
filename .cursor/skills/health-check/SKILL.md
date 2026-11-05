---
name: health-check
version: 1.0.0
group: availability
description: Checks what this TestPilot workspace still lacks (SUT identity, environments and URLs, accounts, databases, DDL freshness, source roots, API docs, browser channel, port bindings such as the backend log channel, DNA drift) from `tuner-workspace doctor --json`, then fills the gaps through maintain-config, dump-ddl, maintain-wiki, tuner-task ask, or upgrade-framework. Also the first-run setup right after tuner-init scaffold. Use when the user says health-check, 体检, 还差什么配置, init-content, 开场配置, 初始化内容, 配置基础信息, or has just scaffolded a workspace.
---

# health-check — 体检与开场配置

先用确定性的 `tuner-workspace doctor` 看清缺什么，再按缺口类型交给对应的 skill 或人。
本 skill 自己只写被测系统说明（`profile.md`）；配置写入交给 `maintain-config`。

## Scope

- **读**：`uv run tuner-workspace doctor --json`、`uv run tuner-config show --json`、`INDEX.project.md`、`knowledge/wiki/index.md`。
- **写**：`knowledge/wiki/domain-notes/<sut>/profile.md`（首次运行）、`INDEX.project.md` 人工区一行。
- **委托**：配置 → `maintain-config`；表结构 → `dump-ddl`；知识 → `maintain-wiki`；端口实现 → `create-app`；DNA → `upgrade-framework`；
  只能人定的通道 → `tuner-task ask`。
- **不写**：密码 / token / Cookie 进任何入库文件或对话。不 `git add` 本机文件。不编 explore、design、api/page objects、feature。

## 在哪执行

1. 目标目录要有 `INDEX.project.md` 和 `config/env.py`。没有就停，让用户先 `tuner-init scaffold <dir>`。
2. 仓库根有 `tuner_testkit/project.py` 时这里是平台仓：先问目标目录（下游仓），之后命令都加 `--directory <目标>` 或在目标目录执行。

## 1. 体检

```bash
uv run tuner-workspace doctor --json
```

把 `checks` 渲染成一张表给用户：检查项、状态（ok / info / warn / missing / error）、说明、下一步。不出现密码。
`summary.error` 和 `missing` 为 0 时告诉用户可以开始干活（下一步通常是 `sut-self-learning` 或 `maintain-testcases`），结束。

## 2. 按缺口处理

按下表逐项处理，一次把要问人的问题问完；用户可以跳过某项。

| doctor 检查 | 处理 |
| --- | --- |
| `layout.legacy` / `layout.dirs` | `uv run tuner-workspace migrate knowledge` 给用户看计划，同意后 `--apply`，再 `tuner-workspace index render` |
| `knowledge.sut_profile` | 首次运行：见 §3 |
| `config.env_local` / `config.urls` / `config.databases` / `config.validate` | `maintain-config`（环境、地址、数据源） |
| `data.accounts` | `maintain-config`（账号写 `data/sut-accounts.local.yaml`，带 `role`、`permissions`） |
| `channels.browser` | 问用户用 Playwright MCP 还是 Cursor 浏览器（对照 `docs/spec/browser-channel.md`），交 `maintain-config` 写 `CHANNELS.browser` |
| `ports.log-source` = missing | §4 |
| `ports.*` = error | 读 `problems`：绑定指错或 app 不满足契约 → `create-app` 修 app，或 `maintain-config` 改绑定 |
| `knowledge.ddl` missing / 过期 | 数据源配好后问用户是否导出，同意后按 `dump-ddl`；`--all` 必须明确同意 |
| `knowledge.source_roots` / `knowledge.api_docs` | 问用户要源码本机路径、API 文档；交 `maintain-config` 写 `KNOWLEDGE`。文档原件放 `knowledge/raw/`，有 OpenAPI 时提示 `tuner-openapi-import` |
| `knowledge.wiki` / `trace.requirements` | 用户有需求文档或业务说明时走 `maintain-wiki` ingest |
| `dna.version` warn / missing | `upgrade-framework` |
| `hooks.git` warn | 告诉用户执行 `git config core.hooksPath tools/git-hooks`（不替用户改 git 配置） |

## 3. 首次运行：被测系统说明

`knowledge.sut_profile` 缺失时，问：系统显示名、目录短名 `<sut>`（小写字母、数字、连字符）、一句话范围、先学的一个模块、
PostgreSQL 非 `public` 时的 schema 名。写 `knowledge/wiki/domain-notes/<sut>/profile.md`：

```markdown
---
kind: domain-note
domain: <sut>
source: 用户口述 <YYYY-MM-DD>
date: <YYYY-MM-DD>
version: 1.0.0
confidence: high
---

# <显示名>

- 范围：…
- 先学切片：…
- 地址、账号、数据源、源码路径、日志通道：见 config（`tuner-config show --json`），本页不重复。
```

然后 `uv run tuner-workspace meta stamp <path> --kind domain-note`，在 `knowledge/wiki/index.md` 的 domain-notes 下登记一行，
`uv run tuner-workspace changelog append --area wiki --skill health-check --action 新建 --items <path> --version 1.0.0`。
用户给了现成材料（用例、字段或权限说明、需求文档）时，原件放 `knowledge/raw/`，交 `maintain-wiki` ingest。

## 4. 后端日志通道（端口）

后端日志是 `log-source` 端口：kit 只定契约（`docs/spec/ports.md`），实现是本仓的 app。

1. 用户在场且能马上回答：问通道是 `ssh-dir` / `log-api` / `rancher-api` / `skip` 中哪一种，以及不含密钥的定位（目录、path、命名空间、工作负载）。
   - 选了通道 → `create-app` 按契约写 `apps/<sut>_logs/`（`port="log-source"`），`maintain-config` 写 `PORTS` 与 `OPS`（密钥由用户给，写进本机文件）。
   - 选 `skip` → 在 `profile.md` 写「本轮不做日志通道」。
2. 用户现在答不了：建任务并异步提问，**回答前不选通道、不写实现**：

   ```bash
   uv run tuner-task create --type explore --title "开场体检：后端日志通道"
   uv run tuner-task ask --task <TASK-ID> --topic sut-log-source --prompt "仓库没有写明后端日志从哪取"
   ```

## 5. 收口

1. 再跑一次 `uv run tuner-workspace doctor --json`，用同一张表回复：每项是已处理、本来就有、用户跳过、等人回答。
2. `uv run tuner-workspace index render` 刷新 `INDEX.project.md`；命令失败就如实写原因。
3. 入库的改动（profile、wiki index/log、`config/env.py` 的团队约定）可以提交，scope 用实际层（如 `knowledge`、`hooks`）；
   提醒用户 `config/env_local.py`、`config/.active_env`、`data/*.local.yaml` 在 gitignore，不要暂存。

## Hard rules

- 用户没说的 URL、主机、路径、表名保持空白，不拿示例值充数。
- 对话里复述配置时，密码和令牌说「已写入本机文件」。
- 日志通道没经人确认前，不选 SSH、日志接口或 Rancher，不写取日志实现。
