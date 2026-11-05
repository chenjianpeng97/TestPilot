# workspace（`tuner-workspace`）

确定性的 workspace 操作 CLI：不连 SUT、不写 git、只读 repo（`migrate --apply` 与 `changelog append` 除外，见下），产物落 `artifacts/`。

## 需求背景

工作台、INDEX 自动区、企业平台同步都需要同一份「这个 workspace 里有什么」的机器可读描述。
5.0.0 之前它以 `tuner-index-platform`（Plane Sync catalog）存在，绑定企业 Runner 语义；现在中立化为
`tuner_testkit.catalog`（扫描）+ `tuner_testkit.tools`（`@tool` 清单），本 CLI 是它们的入口。
7.0.0 起又承担 TestPilot 的三件确定性工作：体检（`doctor`）、对象级 changelog（`changelog`）、布局迁移（`migrate`）。

## 试用场景

- 适用：刷新 `artifacts/catalogs/workspace.json`；渲染 / 校验 `INDEX.project.md` 自动区；在命令行按清单运行工具或动作词；
  给 Markdown 写 `author/created/updated`；体检 workspace 还缺什么；维护库的 changelog 并在提交前校验；把 pre-7.0 布局迁到 `knowledge/`。
- 不适用：维护 `.cursor/REGISTRY.md`（用 `tuner-index-ai`）；探索 SUT（用浏览器通道 + `tuner-evidence`）；改配置（用 `maintain-config` skill + `tuner-config`）。
- 前置：在 workspace 根（或 `--root`）运行；`run` 需要该工具的依赖已装进 `.venv`；`changelog check` 需要 git。

## 运行方式

```bash
uv run tuner-workspace catalog                       # → artifacts/catalogs/workspace.json
uv run tuner-workspace catalog --out -               # 打印到 stdout
uv run tuner-workspace index render                  # 渲染 INDEX.project.md（无则 INDEX.md）的 auto 围栏
uv run tuner-workspace index check                   # 自动区过期则 exit 1（进 CI）
uv run tuner-workspace run sample_tool --params '{"count": 2, "label": "demo"}'
uv run tuner-workspace run db_seed.sample_seed --params '{"count": 2}' --confirm
uv run tuner-workspace meta stamp apps/sample_tool/README.md --kind app

uv run tuner-workspace doctor                        # 体检 JSON：layout / config / data / channels / ports / knowledge / trace / dna / hooks
uv run tuner-workspace doctor --check-db --strict    # 另连每个数据源跑 SELECT 1；有 error / missing 时 exit 1

uv run tuner-workspace changelog append --area testcases --skill maintain-testcases \
  --action 更新 --items User-Login-ok --version 1.0.0->1.1.0 --reason "补充预期"
uv run tuner-workspace changelog check --staged      # pre-commit：维护区改动要有 changelog 行与 version bump
uv run tuner-workspace changelog check --base origin/main   # CI

uv run tuner-workspace migrate knowledge             # 打印迁移计划（dry-run）
uv run tuner-workspace migrate knowledge --apply     # assets/{ddl,domain-notes,usecases,explore,design} → knowledge/
```

- `doctor` 的检查项与状态（`ok / info / warn / missing / error`）见 `tuner_testkit/workspace/doctor.py`；skill `health-check` 读它的 JSON。
- `changelog` 的库清单与行格式见 `docs/spec/metadata-conventions.md` §4；平台仓里只检查带 `INDEX.project.md` 的子 workspace（`dogfood/`）。
  紧急绕过一次：`TUNER_SKIP_CHANGELOG_CHECK=1`。
- `migrate knowledge` 不碰 DNA（`.cursor/`、`docs/spec/`…，由 `tuner-dna sync` 刷新）与本机密钥文件；目标已存在且内容不同时报 conflict，不覆盖。

## 运行示例

```bash
uv run --directory dogfood tuner-workspace catalog --out -
uv run --directory dogfood tuner-workspace doctor
```

预期：catalog 一行 JSON，`catalog_version: 3`，`tools[]` 含 `sample_tool`、`sample_log_source`（`port: log-source`）与 kit 工具，
`action_words[]` 含 `db_seed.sample_seed`；doctor 里 `ports.log-source` 为 `ok`（dogfood 绑定了参考适配器）。

## catalog 结构（v3）

| 键 | 内容 |
| --- | --- |
| `git` | branch / sha / user_email / user_name |
| `counts` | tools / action_words / api_objects / page_objects / ddl_tables / assets / features / scenarios / docs / inbox / runs / reports / evidence_runs / ai_components |
| `tools[]` | `@tool` 清单：tool_id / name / group / origin / argv / params_schema / argv_plan / destructive / timeout / runtime / visibility / readme_path / **port** / author |
| `action_words[]` | `describe()` + destructive / argv / module |
| `api_objects[]` / `page_objects[]` | 静态扫描（method+path / page_id） |
| `knowledge` | ddl（`knowledge/ddl`，未迁移时回落 `assets/ddl`）/ sql_files / assets（每行带 `layer`: knowledge / assets，`category`，front-matter：id / domain / source / version / confidence / status / author …） |
| `tests` | features（含 scenarios 与 tags）/ pytest_nodes |
| `artifacts` | inbox（状态统计 + 最近）/ runs / reports（`manifest.json` 摘要）/ evidence_runs |
| `ai_components` | `.cursor/` 下 rules / skills / agents / hooks 计数 |

INDEX 自动区：`ddl` / `knowledge` / `sql` / `assets` / `api_objects` / `page_objects` / `action_words` / `apps` / `ports` / `features`。
没有 `knowledge` 围栏的旧索引，`assets` 区继续列出知识文件。
