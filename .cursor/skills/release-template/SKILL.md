---
name: release-template
version: 1.0.1
group: internal
description: Versions the template's shared platform assets. Use when tuner_testkit/** or .cursor/** changed and the init_repo release manifest is stale (drift), to decide a semantic version bump, refresh the manifest, and write release notes.
---

# Release Template — 版本化平台公共资产

## Scope

- **目标**：本模板仓是"平台"，公共运行库发 **`tuner-testkit` wheel**，Cursor/git DNA 经
  `tuner-dna sync` 进下游。公共资产（`.cursor/**`、`docs/spec/**`、`tuner_testkit/**`、
  `tools/git-hooks/**`）更新时，要同时对齐 **wheel 版本** 与 `init_repo` DNA manifest。
- **写范围**：`pyproject.toml`（`[project] version`，与 wheel 一致）、
  `tuner_testkit/__init__.py` 的 `__version__`、
  `tuner_testkit/apps/init_repo/release_manifest.json`、必要时相关组件 front-matter 的 `version`、
  以及 release notes（`docs/changelog/`）。

## 触发（何时用）

- `python -m tuner_testkit.apps.init_repo manifest --check` 报告 DRIFT（changed/added/removed）；
- 或 `pre-push` 钩子提示平台资产漂移；
- 或有意发布一个新版本模板给下游项目仓。

## 步骤

1. **看漂移**：`python -m tuner_testkit.apps.init_repo manifest --check`，列出变化的 tracked 文件。
2. **定级（semver）**：结合变化性质决定 bump：
   - `MAJOR`：不兼容的规则/接口/目录约定变更（下游需要迁移）。
   - `MINOR`：新增 rule/skill/agent/工具或向后兼容的能力增强。
   - `PATCH`：措辞/修复/文档级改动。
   - 变更清单可结合各区 `CHANGELOG`（`knowledge/ddl/CHANGELOG.md` 等）与 git diff。
3. **bump 版本**：更新 `pyproject.toml` 的 `[project] version`；对语义变化明显的
   `.cursor/**` 组件同步 bump 其 front-matter `version`（随后 `python -m tuner_testkit.apps.index_ai`
   刷新 `.cursor/REGISTRY.md`）。
4. **刷新 manifest**：`python -m tuner_testkit.apps.init_repo manifest --write`（会以新版本重算哈希）。
5. **release notes**：简述本次模板版本变更（新增/调整了哪些平台能力、是否需要下游迁移）。
6. **验证**：再次 `manifest --check` 应为 "No drift"。

## Hard rules

- 版本号遵循 semver；不要在未 bump 版本时静默改动公共资产（那正是漂移）。
- manifest 由工具生成，不手改哈希。
- 不得写入敏感值。

## Output checklist

- 采用的版本号与定级理由；
- 变化的 tracked 文件清单（来自 `manifest --check`）；
- 是否同步 bump 了 `.cursor/**` 组件版本并刷新 REGISTRY；
- `manifest --check` 复检结果（应无漂移）。
