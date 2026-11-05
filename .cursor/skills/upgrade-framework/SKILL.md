---
name: upgrade-framework
version: 1.0.0
group: availability
description: Upgrades this TestPilot workspace to a newer tuner-testkit release - tool domain and project .venv, DNA (rules, skills, specs, hooks) via tuner-dna sync --prune, migration notes from docs/changelog/TEMPLATE-*.md, layout migrations - without touching business data, then commits once. Use when the user says /upgrade-framework, 升级框架, 升级 TestPilot, 升级 tuner-testkit, or doctor reports DNA drift.
---

# upgrade-framework — 升级框架，不动业务数据

升级只碰平台部分：kit 包、DNA（`.cursor/**`、`docs/spec/**`、`docs/changelog/TEMPLATE-*.md`、`tools/git-hooks/**`、`AGENTS.md`）。
业务数据（`knowledge/`、`assets/`、`packages/`、`apps/`、`data/`、`tests/`、`config/`、`INDEX.project.md`）不在 DNA 里，sync 不会写。

## Scope

- **写**：`pyproject.toml`、`uv.lock`、DNA 文件、`.tuner-dna.json`、迁移说明要求的布局变化。
- **不写**：业务数据的语义；`*.local.mdc`、`AGENTS.local.md` 等本地覆盖层（sync 永远跳过它们）。

## 1. 看清起点

```bash
git status --short                      # 必须干净；不干净先让用户提交或暂存自己的改动
uv pip show tuner-testkit               # 业务仓 .venv 的版本
uv tool list                            # tool 域的版本
uv run tuner-dna check --json           # 当前 DNA 与已装 kit 的差异
```

`.tuner-dna.json` 的 `kit_version` 是上次 sync 的版本。问用户目标版本；没说就用 PyPI 最新。

## 2. 升级两处安装

```bash
uv tool upgrade tuner-testkit
uv add "tuner-testkit[<原来的 extras>]==<目标版本>"   # extras 照抄 pyproject 里原来的，如 db,api,report
uv sync
```

## 3. 读迁移说明

升级后的 kit 带来 `docs/changelog/TEMPLATE-<版本>.md`（sync 后在本仓）。读从旧版本（不含）到目标版本（含）之间的每一份，
列出「下游需要做什么」，给用户看。常见项：

- 布局迁移：`uv run tuner-workspace migrate knowledge`（先看计划，同意后 `--apply`）。
- stub 变化（如 `config/env.py` 新增段）：对照 kit 的新 stub，**只补新段**，不覆盖用户已有值。
- 规范字段变化（如测试单缺陷表列）：按说明改业务文件，每个库照常写 changelog。

## 4. 同步 DNA

```bash
uv run tuner-dna sync --prune
```

- 没被本地改过的文件自动更新；上游删掉的文件在没被改过时删除（`--prune`）。
- 输出里 `kept_local` / `prune_kept` 是本地改过的 DNA 文件：逐个 `git diff` 给用户看。
  本仓定制应移到本地覆盖层（规则写 `.cursor/rules/<名字>.local.mdc`，世界观补充写 `AGENTS.local.md`），
  用户同意后再 `uv run tuner-dna sync --prune --overwrite`。
- 用其它 AI IDE 时加 `--ide claude,agents`（与上次相同）。

## 5. 验证

```bash
uv run tuner-dna check
uv run tuner-workspace doctor --json
uv run tuner-workspace index render
uv run tuner-index-ai
uv run pytest -q                        # 有 pytest 套件时
uv run behave --stage api --tags "@offline"   # 有离线 BDD 时
```

失败就停下，把失败项和可能原因告诉用户，不要硬提交。

## 6. 一次提交

只暂存这次升级动到的文件：`pyproject.toml`、`uv.lock`、`.tuner-dna.json`、DNA 路径、迁移动到的业务文件（及其 changelog）。

```text
chore(rules,skills,agents,docs,hooks): upgrade TestPilot DNA to tuner-testkit <版本>
```

scope 必须覆盖实际改动的层（迁移动了 `knowledge/` 就加 `knowledge`）。正文列出读过的 TEMPLATE 说明与执行的迁移。不 push。

## Hard rules

- 工作区不干净不开始。
- 不对本地改过的 DNA 文件直接 `--overwrite`，先让用户看 diff 并把定制移到 `*.local.*`。
- 不改业务数据的语义；迁移说明没要求的业务文件不碰。
