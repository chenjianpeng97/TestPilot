# tuner-testkit 7.4.0 — 去掉工作台「知识」页

MINOR。工作台不再提供「知识」浏览页。

## 变化

- **删除 `/knowledge` 与 `/api/catalog`**。该页打开时会全仓扫描并给每个资产跑 `git log`，大仓很慢，列表也几乎只显示路径和标题。
- **启动不再后台刷新** `artifacts/catalogs/workspace.json`。需要 catalog 时仍用 `tuner-workspace catalog`。
- 左侧导航不再有「知识」。知识仍在仓库 `knowledge/`，用编辑器或 skill `maintain-wiki` 维护。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.4.0"` → `uv sync` → `tuner-dna sync --prune` → 重启 `tuner-workbench`

## 需要迁移

不需要。书签里的 `/knowledge` 会 404。
