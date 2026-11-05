# design 知识规范（v0.1 草案）

> **状态**：v0.1 草案。待下游 dogfood（Plane）实践收敛后再升 v0.2。
> 不要把本文件当成冻结的 API。缺字段、多余字段、命名不贴，都记回本文件。
>
> 归属：`knowledge/wiki/design/`。总流程见 [`sut-self-learning.md`](sut-self-learning.md)。
> 与 `api-objects-syntax.md` / `page-objects-syntax.md` 平级，但是**知识**不是可执行代码。

## 1. 原则

- **来源开放**：日志、DB diff、源码、人工文档、MCP 网络均可。
- **产物收敛**：一篇文档描述 **一条业务路由** 的 DB/外部副作用，可供
  `db_assert` / action words / Then 步骤直接引用。
- **可溯源**：每条 `writes` 必须能指回 evidence 或源码位置。
- **noise 不当断言**：审计表、操作日志默认进 `noise`，禁止当业务结果断言。

## 2. 路径与命名

```text
knowledge/wiki/design/<app>/<route-slug>.md
```

- `<app>`：与 page_objects 的 app 分段对齐（如 `web`）。
- `<route-slug>`：由 method + normalized_path 派生，例如
  `post-api-v1-workspaces-projects-issues.md`。

一篇文档 **只描述一条路由**。同一 path 的 GET/POST 拆开。

## 3. Front-matter

```yaml
---
domain: issue
source: explore+source-code
date: 2026-09-13
version: 0.1.0
confidence: inferred          # observed | inferred | verified
evidence:
  - artifacts/evidence/20260913T133000Z-issue-create/
route: POST /api/v1/workspaces/{slug}/projects/{id}/issues/
method: POST
normalized_path: /api/v1/workspaces/{slug}/projects/{id}/issues/
api_object_ref: packages/api_objects/api/v1/workspaces/projects/issues/POST.v1.py
page_ref:
  page_id: web.project_issues@v1
  trigger: "New Issue"        # 按钮 / 控件名，可空
---
```

`confidence` 在本资产上的含义：

| 值 | 含义 |
| --- | --- |
| `observed` | DB diff / SQL 日志实测 |
| `inferred` | 源码或文档推导 |
| `verified` | 人工核实（对应 assets 的 `high`） |

## 4. 正文 schema（骨架）

```markdown
# POST /api/v1/workspaces/{slug}/projects/{id}/issues/

## writes
- issues            INSERT
  correlate: body.name → name, path.project_id → project_id
  identity: id
- issue_description INSERT
  correlate: issue_id ← issues.id

## noise
- issue_activities  INSERT   # 审计，默认不当业务断言

## reads
- states, project_members     # 只读校验，locate 可忽略

## notes
- 源码：apps/api/plane/db/models/issue.py Issue.save
```

字段约定：

- `writes[]`: `table` + `op`（INSERT/UPDATE/DELETE）+ 可选 `correlate` + 可选 `identity`
- `correlate`: `body.<field> → <column>` 或 `path.<seg> → <column>` 或
  `<column> ← <other_table>.<identity>`
- `identity`: 新行主键列名，供后续断言 locate
- `noise[]`: 每次操作都写、但不是业务结果的表
- `reads[]`: 请求过程中的只读表（权限/枚举），默认不断言

## 5. 硬约束

- 不得写入 token / cookie / 密码 / 真实邮箱（可用掩码）。
- `noise` 表不得写入 `db_assert` action words 作为业务断言。
- 没有 `evidence` 且 `source` 也不是明确的源码路径时，不得把 `confidence`
  标成 `observed`。
- 更新文档必须 bump `version`。

## 6. 实践待决（Plane dogfood 2026-09-13 回来改）

已用 workspace→project→issue 切片压过 v0.1。**本版不升 schema**，只把缺口记在这里，待积累第二条切片再升 v0.2。

| 缺口 | 实践 |
| --- | --- |
| 按路由还是按用户动作成文？ | **继续按路由**。本切片 Save=1 POST；登录是多条 PATCH。动作视图可写在 `knowledge/wiki/explore`，design 保持一路由一文。 |
| `page_ref` 多个 trigger | 需要。工具栏 `Add work item` 与侧栏 `New work item` 打同一 POST。v0.2 考虑 `triggers: []`。 |
| `writes` 的 `when:` | 需要。`issue_assignees` 仅当 `assignee_ids` 非空。 |
| 默认值 / 空 body → DB 有值 | `state_id=""` → `_ensure_default_state`。`correlate` 表达不了。 |
| 业务 identity 双键 | UUID `id` + UI `TUNER-{sequence_id}`。考虑 `business_identity`。 |
| slug 占位 | `normalize_path` 不替换非 uuid slug；冻结时手写 `{workspace_slug}`，运行时 `set_path`。 |
| `externals:` | 本切片未遇到（无邮件/S3）。仍待决。 |
| 源码表先于 DDL | 允许：先从 models 写 design，再 `tuner-dump-ddl` 补表。 |

样本：下游 dogfood `knowledge/wiki/design/web/post-api-workspaces-projects-issues.md`。
