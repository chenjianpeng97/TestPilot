# dogfood — 用本仓 scaffold 出的 workspace

这是 `tuner-init scaffold` 从平台仓生成的一个**真实 workspace**，被测系统（SUT）就是平台本身
（TestPilot：kit CLI、skills、工作台）。它承担三件事：

- **知识管理**：`knowledge/wiki/domain-notes/platform/roadmap.md`（平台路线图 A→B→C→D）、
  `knowledge/wiki/usecases/platform/qa-daily-journeys.md`（「QA 一天」验收剧本）、
  `knowledge/wiki/usecases/workbench/lightweight-user.md`（轻量用户使用工作台）。
- **活文档**：`tests/features/platform/*.feature`（A7 验收）、`tests/features/workbench/*.feature`（B 验收）。
  未落地的场景标 `@wip`，随平台能力逐个解除。
- **参考实现**：`apps/sample_log_source/` 是 `log-source` 端口的参考适配器（读 `data/sample-logs/`），`config/env.py` 的 `PORTS` 已绑定它；
  `uv run --directory dogfood tuner-workspace doctor` 里 `ports.log-source` 应为 `ok`。

业务资产地图见 [`INDEX.project.md`](INDEX.project.md)。平台自身的能力地图在仓根 `INDEX.md`。

## 运行

本目录是根 `pyproject.toml` 的 uv workspace 成员（`[tool.uv.sources] tuner-testkit = { workspace = true }`），
与平台共用一个 `.venv`，不需要单独 `uv sync`：

```bash
uv run --directory dogfood python -m apps.sample_tool --count 2 --label demo --json
uv run --directory dogfood tuner-action-words run db_seed.sample_seed --example
uv run --directory dogfood behave --stage api --tags "@offline" --tags "~@wip"
uv run --directory dogfood pytest -q
```

### 非编码成员三步（工作台）

1. `git pull`
2. 在仓库根 `uv sync`（与平台共用 `.venv`）
3. 双击 `dogfood/workbench.cmd`（Windows）或执行 `dogfood/workbench.sh`，等价于 `uv run --directory dogfood tuner-workbench`

浏览器打开 `http://127.0.0.1:8765/`，在「工具」里找 `sample_tool`，在「造数」里找 `db_seed.sample_seed`，填参运行。工作台只绑本机，密钥不会出现在页面上。

## 为什么这里没有 `.cursor/`

Cursor 以仓库根的 `.cursor/**` 与 `AGENTS.md` 覆盖整棵树；在子目录再铺一份 DNA 会重复注入
always-on 规则。因此用 `--no-ai` 生成，DNA 的全链验证由 CI 在临时目录 scaffold 后 `tuner-dna check` 完成。

## 重新生成

```bash
uv run tuner-init scaffold dogfood --no-ai
```

scaffold 只补缺失文件（不覆盖）。生成后保持 `pyproject.toml` 为虚拟成员
（`[tool.uv] package = false` + workspace source），不要恢复成 PyPI 版本约束。

## 提交

改动本目录时 commit scope 用 `dogfood`（见 `docs/spec/commit-convention.md`）。
