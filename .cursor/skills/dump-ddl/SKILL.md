---
name: dump-ddl
version: 1.3.1
group: knowledge
description: Dumps live table DDL into knowledge/ddl/<datasource>/ via tuner_testkit/apps/dump_ddl.py, then updates the knowledge index from CHANGELOG. Use when the user says /dump-ddl, dump DDL, 拉取 DDL, 导出表结构, or needs schema files before writing action words / SQL.
---

# Dump DDL — 把线上/本地库表结构回填到 knowledge/ddl

## Scope

- **目标**：按命名数据源把基表 DDL（+ 可选示例 INSERT）写到
  `knowledge/ddl/<datasource>/<table>.sql`，并留下 `knowledge/ddl/CHANGELOG.md` 供索引增量更新。
- **写范围**：`knowledge/ddl/<datasource>/**`、`knowledge/ddl/CHANGELOG.md`；有
  `INDEX.project.md` §1.1（`tuner-workspace index render` 渲染）。
- **不写**：`config/env_local.py`（gitignore，永不提交）、token/密码、平台 DNA
  （`tuner_testkit/db`、`tuner_testkit/apps/dump_ddl.py`）——缺方言支持要先改平台仓的 `main`。
- **必须走**：`python -m tuner_testkit.apps.dump_ddl` → `tuner_testkit.db.DbClient`。禁止直连驱动、
  手写 `pg_dump` / `mysqldump` 替代、把密钥写进仓库。

## Before running

1. 读 `config/env.py` + 若存在的 `config/env_overlay.py`，确认 `DATABASES` 别名与
   `type`（`mysql` / `sqlserver` / `postgres`）。**不要把 `env_local.py` 的密码回显到对话。**
2. 本机真实连接只存在于 `config/env_local.py` 或 `TUNER_DB_<ALIAS>_*`。文件不存在则
   先让用户从 `config/env_local.py.example` 复制并填值，**不要替用户把密钥提交进 git**。
   多套环境时先 `python -m tuner_testkit.config show` 确认激活名（`tuner_testkit.config` 解析
   `ENVIRONMENTS`）；需要换套则 `python -m tuner_testkit.config use <name>`。
3. 缺别名时：试验田/下游仓把无密钥的 `type`/host/库名写进 `env_overlay.py`；密钥仍只放
   `env_local.py`。
4. PostgreSQL（如 Plane 本地）：容器内 hostname 是 `plane-db`，**从宿主机 dump 必须用
   `127.0.0.1:5432`**。库名/用户默认与 Plane `.env` 的 `POSTGRES_DB` / `POSTGRES_USER`
   一致；schema 默认 `public`。
5. 产出目录是 `knowledge/ddl/<datasource>/`。换 SUT 时不要把旧系统的表文件混进同一别名目录
   （先清该别名目录再 `--all`，或换一个 datasource 别名）。

## Steps

```
Task Progress:
- [ ] 确认 datasource 别名与 type
- [ ] 运行 dump_ddl
- [ ] 核对 CHANGELOG 新行与产出路径
- [ ] `tuner-workspace index render` 刷新 INDEX.project.md §1.1
```

1. **选定数据源**
   - 用户指定了别名 → 用那个 `--datasource`。
   - 未指定 → `main`。
   - 用户指定了表名 → 传表名；否则 `--all`（排除视图）。
   - PostgreSQL 需要非 `public` schema 时加 `--schema <name>`。
   - 只要结构、不要示例 INSERT → `--no-sample`。
   - **默认带注释掉的最新一行 INSERT**（造数参考）。`dump_ddl` 会从样例中去掉
     `password` / `token` / `session_*` / `*_token` 等密钥列；过长行（stdout/jsonb）
     改写为省略说明。不要为了“怕泄密”对整库加 `--no-sample`，除非用户只要结构。

2. **执行**（仓库根目录）

   ```bash
   uv run python -m tuner_testkit.apps.dump_ddl --all --datasource main
   ```

   指定表：

   ```bash
   uv run python -m tuner_testkit.apps.dump_ddl issues cycles --datasource main
   ```

   PostgreSQL 显式 schema：

   ```bash
   uv run python -m tuner_testkit.apps.dump_ddl --all --datasource main --schema public
   ```

   只要结构：

   ```bash
   uv run python -m tuner_testkit.apps.dump_ddl --all --datasource main --no-sample
   ```

3. **留痕**：工具会 `append_entry` 到 `knowledge/ddl/CHANGELOG.md`。不要手改 `knowledge/ddl/**`
   正文；要更新就重跑本工具。

4. **索引**：`uv run tuner-workspace index render` 刷新 `INDEX.project.md` §1.1（DDL 自动区）；需要写用途时读
   `knowledge/ddl/CHANGELOG.md` **尾部新行**，按 `maintain-index` 在人工区补一句。
5. **提交**：scope `knowledge`（如 `chore(knowledge): refresh order ddl via dump_ddl`）。

## Hard rules

- DB 只经 `tuner_testkit.db.DbClient`；本 skill 只**调用** `tuner_testkit/apps/dump_ddl.py`，不在对话里
  拼 DSN、不 `psql`/`mysql` 客户端替代。
- 日志走 `tuner_testkit.logging`（工具已接好）。不要 `print` 连接串。
- 不得提交 `config/env_local.py`、`.env`、密码、token。
- 平台缺 PostgreSQL / 某方言：切到平台仓的 `main` 改
  `tuner_testkit/db` + `tuner_testkit/apps/dump_ddl.py`，提交后再 `git merge` 进试验田。禁止把平台改动只留在
  `plane-dogfood`。
- 覆盖式 dump 会改写同名 `.sql`；换库前确认 alias 目录不会混入另一套 SUT。

## Verify

1. `uv run python -m tuner_testkit.apps.dump_ddl --help` 能看到 `--datasource` / `--all` / `--schema`。
2. 目标 `knowledge/ddl/<alias>/` 出现 `.sql`；文件头含 `-- auto-generated definition`。
3. `knowledge/ddl/CHANGELOG.md` 末行 `tool=dump_ddl` 且 `count=` 与文件数一致。
4. 对应索引 §1.1 已登记 datasource / 路径 / 表文件数（不要把每一张表名都抄进 INDEX）。

## Output checklist

- 使用的 `--datasource` / `--schema` / `--all` 或表名列表。
- 产出目录与表文件数（来自 CHANGELOG，不逐个读 `.sql` 正文）。
- 更新了哪份 INDEX。
- 是否误把 `env_local.py` 纳入暂存区（必须否）。
