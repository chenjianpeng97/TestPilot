---
name: maintain-index
description: Internal step (usually reached via other skills after they change assets). Updates INDEX.project.md (the workspace map of knowledge, assets, tools, ports and tests) incrementally - deterministic auto zones via tuner-workspace index render, manual notes from changelog deltas and front-matter, never full asset bodies. Use after new knowledge/assets/tools/objects are added, or when the index drifts from reality.
version: 2.0.0
group: internal
---

# Maintain INDEX.project.md（增量、省 token）

## Scope

- **目标**：`INDEX.project.md`（业务资产地图）与仓库真实状态一致。
- **规范**：`.cursor/rules/index-hygiene.mdc`、`docs/spec/knowledge-syntax.md`、`docs/spec/assets-knowledge-syntax.md`。
- **写范围**：`INDEX.project.md` 围栏外的人工区。AI 组件不手写（`tuner-index-ai` 生成 `.cursor/REGISTRY.md`）。
<!-- platform-only:begin -->
- **平台仓**：另有根 `INDEX.md`（平台能力地图）。平台工具（`tuner_testkit/apps/`）、kit 模块、DNA 变化写那里；
  `dogfood/` 的业务资产写 `dogfood/INDEX.project.md`。
<!-- platform-only:end -->

## 先跑确定性渲染，再做人工区

被 `<!-- auto:begin:<zone> -->` … `<!-- auto:end:<zone> -->` 围起来的区块**不要手写**：

```bash
uv run tuner-workspace catalog          # 刷新 artifacts/catalogs/workspace.json
uv run tuner-workspace index render     # 渲染 INDEX.project.md 的 auto 围栏
uv run tuner-workspace index check      # CI：自动区过期则 exit 1
```

zone：`ddl` / `knowledge` / `sql` / `assets` / `api_objects` / `page_objects` / `action_words` / `apps` / `ports` / `features`。
pre-7.0 的索引没有 `knowledge` / `ports` 围栏时，`uv run tuner-workspace migrate knowledge --apply` 会补上。
本 skill 只负责围栏**之外**的人工区（用途一句话、confidence 采信说明）。

## 核心原则：读 delta，不全量读

- **各库 changelog 的尾部增量**（清单见 `docs/spec/metadata-conventions.md` §4：`knowledge/ddl/CHANGELOG.md`、`knowledge/wiki/log.md`、
  `knowledge/requirements/CHANGELOG.md`、`knowledge/defects/CHANGELOG.md`、`assets/testcases/CHANGELOG.md`、`packages/*/CHANGELOG.md` …），
  据此判断人工区要补什么。**禁止**为维护索引而逐个打开 `knowledge/ddl/*.sql` 正文。
- 新增文件只读 **front-matter**（domain / source / version / confidence / status）即可写用途，不必读全文。
- wiki 页的目录归 `knowledge/wiki/index.md`（`maintain-wiki`），这里不重复列每一页。

## 步骤

1. `index render`，看 `changed` 与 `zones`。
2. 读各库 changelog 自上次索引更新之后的新行；不确定分界就读尾部若干行。
3. 对人工区做最小 diff：新知识或新资产写一句用途和采信说明；删除的写明去向。只改变化的小节。
4. `.cursor/**` 有变化时跑 `uv run tuner-index-ai`。

## Verify

- `uv run tuner-workspace index check` 返回 `up_to_date: true`。
- 人工区每条都能在仓库找到对应文件或 changelog 行。
- 未全量读取 `.sql` 正文。

## Output checklist

- 渲染了哪些 zone、人工区改了哪些行。
- 读取了哪些 changelog 的 delta（来源证据）。
- 是否重跑了 `tuner-index-ai`。
