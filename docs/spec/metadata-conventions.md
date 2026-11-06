---
name: metadata-conventions
version: 1.2.0
description: 统一 front-matter / run manifest 字段家族，供 catalog、工作台与未来企业平台解析「谁在何时创建了什么」。
---

# 元数据约定（metadata-conventions）

> C 阶段 0：企业平台**只解析 front-matter + manifest**，不读业务代码。
> 身份不要让 LLM 手填——用 `tuner-workspace meta stamp <path>` 写 `git config user.email`。

## 1. 通用字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `kind` | string | `app` / `action_word` / `testreport` / `inbox` / `question` / `task` / `testdesign` / `testcase` / `testcase-suite` / `testcase-module` / `testcase-index` / `explore` / `design` / `usecase` / `domain-note` / `wiki-page` / `wiki-index` / `requirement` / `defect` |
| `id` | string | 稳定标识（`tool_id` / `word_id` / 报告 slug） |
| `title` | string | 短标题 |
| `author` | email | 创建者，来自 `git config user.email` |
| `created` | date | 首次写入（ISO `YYYY-MM-DD`） |
| `updated` | date | 最近 stamp |
| `version` | string | 资产版本 |
| `tags` | list | 自由标签 |
| `sut` | string | 被测系统短名 |
| `env` | string | 命名环境（`dev` / `uat` / …） |

catalog 同时用 `git log --diff-filter=A --format=%ae -- <path>` 算首次提交者；
`author` 与之不一致时 `tuner-workspace catalog` 行上带 `author_mismatch: true`（不阻断）。

## 2. 按 kind 扩展

### `apps/<name>/README.md`（`kind: app`）

额外：`tool_id` / `summary` / `inputs` / `outputs`。

### action word

类属性 `author` / `owner`（可选）经 `describe()` 进 catalog；缺省用模块文件的 git 首次作者。
`Params` 每个字段必须有 `Field(description=...)`（表单 label）。

### 测试报告（`kind: testreport`）

落点：`assets/testreport/<sut>/<yyyy-mm>/<slug>.md`。

额外：`run_id` / `period` / `result`（`{total,passed,failed}`）/ `evidence[]` / `features[]`。
端到端执行报告再加 `task_id` / `design`（指向 `work/tasks` 与 `assets/testdesign`）。

正文固定章节：范围 / 环境 / 结果 / 缺陷 / 风险 / 证据链接。见 skill `generate-test-report`。

### inbox

沿用 `docs/spec/agent-task-log.md`，再加 `author`。

### 任务与测试设计

- `kind: task` 落在 `work/tasks/TASK-*/task.md`，字段见 `docs/spec/work-task.md`。
- `kind: question` 未回答落在 `artifacts/inbox/questions/Q-*.md`，回答后移到 `artifacts/inbox/archived-question/`（不入库）。
- `kind: testdesign` 落在 `assets/testdesign/<sut>/<slug>.md`，字段见 `docs/spec/test-design-syntax.md`。
- `kind: testcase` 落在 `assets/testcases/<模块>/<套件>/<用例ID>.md`；套件说明是 `testcase-suite`，模块说明是 `testcase-module`，总索引是 `testcase-index`。字段见 `docs/spec/testcase-syntax.md`。
- `kind: requirement` 落在 `knowledge/requirements/<REQ-ID>.md`，wiki 页落在 `knowledge/wiki/**`，字段见 `docs/spec/knowledge-syntax.md`。
- `kind: defect` 落在 `knowledge/defects/<DEF-ID>.md`，字段、章节与历史表见 `docs/spec/defect-syntax.md`。

### run manifest

`artifacts/runs|<reports>/<run_id>/manifest.json`：`producer.user_email` / `producer.host` /
`producer.tool_id`。见 `docs/spec/artifacts-layout.md`。

## 3. 谁来写

| 动作 | 命令 |
| --- | --- |
| 新建 app / 报告 / usecase | skill 落盘后立刻 `tuner-workspace meta stamp <path> --kind …` |
| 批量补作者 | 对缺 `author` 的 Markdown 再 stamp 一次（不覆盖已有 `created`） |
| 维护一个库后留痕 | `tuner-workspace changelog append --area <库> …`（§4） |

## 4. 对象级 changelog（追溯）

`artifacts/inbox/` 是本机会话流水，不入库。追溯靠被维护对象自己的记录，和改动在同一个提交里入库：

1. **单元版本**：用例、需求、缺陷、wiki 页、测试设计等带 front-matter 的单元，内容一改就 bump `version`
   （修正错字 patch，补充步骤或预期 minor，改变语义 major）。新文件从 `1.0.0` 起。
2. **库 changelog**：每次维护在库根追加一行，命令写，不手编：

   ```bash
   tuner-workspace changelog append --area testcases --skill maintain-testcases \
     --action 更新 --items Order-Refund-partial-amount --version 1.0.0->1.1.0 --reason "补充库存回填的预期"
   ```

   行格式：`- <iso-ts> | <skill> | <action> | items=<id,…> | version=<x->y> | reason=<一句话> | author=<email>`。
   `author` 默认取 `git config user.email`；`reason` 不写密钥。

| 库（`--area`） | 目录 | changelog | 维护者 |
| --- | --- | --- | --- |
| `testcases` | `assets/testcases/` | `assets/testcases/CHANGELOG.md` | `maintain-testcases` |
| `testsheet` | `assets/testsheet/` | `assets/testsheet/CHANGELOG.md` | `maintain-testsheet`、`execute-testsheet` |
| `testdesign` | `assets/testdesign/` | `assets/testdesign/CHANGELOG.md` | `derive-test-design` |
| `requirements` | `knowledge/requirements/` | `knowledge/requirements/CHANGELOG.md` | `maintain-wiki` |
| `defects` | `knowledge/defects/` | `knowledge/defects/CHANGELOG.md` | `maintain-defectlib` |
| `wiki` | `knowledge/wiki/` | `knowledge/wiki/log.md` | `maintain-wiki` |
| `ddl` | `knowledge/ddl/` | `knowledge/ddl/CHANGELOG.md` | `tuner-dump-ddl`（工具自动写） |
| `api_objects` | `packages/api_objects/` | `packages/api_objects/CHANGELOG.md` | 录制工具自动写；手改走 `freeze-api-objects` |
| `page_objects` | `packages/page_objects/` | `packages/page_objects/CHANGELOG.md` | 录制工具自动写；手改走 `maintain-page-objects` |
| `action_words` | `packages/action_words/` | `packages/action_words/CHANGELOG.md` | `create-action-word` |

3. **校验**：`tuner-workspace changelog check --staged`（pre-commit 自动跑；CI 用 `--base <ref>`）。
   维护区有改动却没有 changelog 行 → 失败；改了带 `version` 的单元却没 bump → 失败。
   基础设施文件（`__init__.py`、`registry.py`、`session.py`、`_internal/` 等）、`index.md` / `README.md` 不算单元。
   紧急情况单次绕过：`TUNER_SKIP_CHANGELOG_CHECK=1 git commit …`，并在提交正文说明原因。
4. git 历史仍然有效：一次维护一个提交，提交正文逐条写首次创建或变更原因；changelog 是不依赖 git 工具也能读的摘要。
