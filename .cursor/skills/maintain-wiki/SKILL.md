---
name: maintain-wiki
version: 1.0.0
group: knowledge
description: Maintains the SUT knowledge wiki under knowledge/ in the LLM Wiki style - ingest originals from knowledge/raw into wiki pages and requirement files (knowledge/requirements/REQ-*.md), answer questions from the wiki first, and lint for orphan pages, stale claims, missing sources, and requirements without testcases. Use when the user says maintain-wiki, ingest, 整理需求, 沉淀业务知识, 需求入库, 知识库, wiki lint, or drops a PRD / API doc / meeting note into the repo.
---

# maintain-wiki — 被测系统知识库

规范见 `docs/spec/knowledge-syntax.md`。raw 不可变；wiki 由你增量维护；人负责给来源和提问。

## Scope

- **读**：`knowledge/raw/**`、`knowledge/wiki/index.md`、相关 wiki 页、`knowledge/requirements/`、`knowledge/ddl/`（核对字段）、`INDEX.project.md`。
- **写**：`knowledge/wiki/**`（含 `index.md`、`log.md`）、`knowledge/requirements/<REQ-ID>.md` 与其 `CHANGELOG.md`。
- **不写**：`knowledge/raw/` 原件内容；`assets/`（用例走 `maintain-testcases`）；config（地址、密钥走 `maintain-config`）。

## Ingest（新原件 → wiki 与需求）

1. 原件不在 `knowledge/raw/` 时，先放进去（`knowledge/raw/<来源>/<文件名>`），只移动不改内容。
2. 读原件和 `knowledge/wiki/index.md`，找出受影响的已有页面。
3. 写或更新 wiki 页（`wiki/domain-notes/<domain>/`、`wiki/usecases/<domain>/`）：front-matter 按 knowledge-syntax §3，
   `source` 指回原件（可带章节锚点）。和已有页面矛盾时不要静默覆盖：在页内「待确认」列出两种说法和各自来源，告诉用户。
4. 需求文档：每条可验收的需求拆成 `knowledge/requirements/REQ-<slug>.md`（描述、验收标准、业务规则，`status: active`）。
   已有同义需求就更新原文件并 bump `version`，不新开 ID；ID 发出后不改不复用。
5. 在 `knowledge/wiki/index.md` 对应分类登记新页（路径 + 一句话摘要）。
6. 留痕：
   ```bash
   uv run tuner-workspace changelog append --area wiki --skill maintain-wiki --action ingest \
     --items <新增或更新的页面> --reason "ingest <原件>"
   uv run tuner-workspace changelog append --area requirements --skill maintain-wiki --action 新建 \
     --items REQ-a,REQ-b --version 1.0.0 --reason "拆自 <原件>"
   ```
7. 新文件 `uv run tuner-workspace meta stamp <path> --kind <domain-note|usecase|requirement>`。

## Query（回答问题）

先读 `index.md` 再下钻相关页面，回答里引用页面路径。答案有长期价值（以后还会被问、可被用例引用）时，问用户是否写成 wiki 页，按 Ingest 第 3、5、6 步落盘。
wiki 没有依据时说没有，不要编；建议用户补原件，或去 `sut-self-learning` 探索。

## Lint（体检知识库）

逐项检查并在 `log.md` 追加一行 `--action lint`，问题清单回复给用户：

- 孤立页：`knowledge/wiki/**` 下没在 `index.md` 登记的页面。
- 缺来源：wiki 页或需求没有 `source`；explore / design 没有 `evidence`。
- 过时主张：与较新的原件、`knowledge/ddl/` 列名、design 证据矛盾。
- 需求覆盖：`uv run tuner-workspace doctor --json` 的 `trace.requirements`；列出没有用例 `requirements` 指向的 `REQ-…`，建议走 `maintain-testcases`。
- 废弃需求仍被用例引用：提示用户。

只有用户同意后才改页面；改了照常 bump `version` 并写 changelog。

## 收口

1. `uv run tuner-workspace index render` 刷新 `INDEX.project.md` 的 `knowledge` 自动区。
2. 一次维护一个提交，scope `knowledge`（如 `feat(knowledge): ingest refund PRD`）。提交前 `git diff --cached` 只含本次文件。

## Hard rules

- 不改写 `knowledge/raw/` 原件的语义。
- 每条主张都有来源；不凭空补业务规则、字段名、状态机。
- 不在 wiki 写地址、账号、密钥：引用 config 键名。
