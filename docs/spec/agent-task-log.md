# Agent 任务日志（`artifacts/inbox/`）

> 给 `.cursor/agents/**` 编排任务用的**本机运行记录**约定。硬约束见 `.cursor/rules/agent-task-log.mdc`。
>
> - **谁必须写**：只有按 `.cursor/agents/*.md` 编排的任务（`sut-self-learning`、`bdd-asset-pipeline`、`sut-source-to-design`）。
> - **skill 不写 inbox**：`maintain-*`、`execute-testsheet` 等 skill 的追溯写在被维护对象自己的 changelog 里并入库
>   （`docs/spec/metadata-conventions.md` §4）。inbox 不入库，换机器就没了，不能当追溯依据。
> - Evidence（网络/DOM dump）仍落 `artifacts/evidence/<run_id>/`，本目录不替代它。

## 1. 路径

```text
artifacts/inbox/<YYYYMMDDTHHMMSSZ>-<agent>-<slice>.md
```

- `<agent>`：与 agent front-matter `name` 一致（如 `sut-self-learning`）。
- `<slice>`：短横线 slug（如 `cycles`、`issue-create`）。
- 本目录默认 gitignore；本机下次会话靠读磁盘复用，不入库。

## 2. 通用模板（所有 agent）

```markdown
---
agent: sut-self-learning
slice: cycles
started: 2026-09-14T03:12:00Z
ended: 2026-09-14T03:40:00Z
status: done
account_id: dogfood-admin
evidence:
  - artifacts/evidence/20260914T031200Z-cycles/
---

# <slice> — <一句话意图>

## Intent
（用户要什么）

## Inputs
- INDEX / INDEX.project / accounts 文件 / 源码路径

## Outputs
| kind | path | action |
| --- | --- | --- |
| explore | knowledge/wiki/explore/web/….md | add |
| api_object | packages/api_objects/… | add |

## Next
- …
```

`kind` 建议：`explore` / `design` / `ddl` / `api_object` / `page_object` / `action_word` / `feature` / `index` / `inbox`。

## 3. SUT 自学习额外章节（强制）

编排 agent `.cursor/agents/sut-self-learning.md` 的 inbox **必须**再写：

```markdown
## Pages explored
| url pattern | title | primary actions |
| --- | --- | --- |
| `/{workspace}/projects/{id}/cycles/` | Cycles | New cycle, Save |

## Assets added this run
（只列本任务新增或更新的路径，不要把仓库里已有资产再抄一遍）
```

对照两轮 dogfood 时，另写 `## Loop delta`：相对上一份 inbox，少了哪些手工步骤、多了哪些平台能力。

## 4. 人类提问（阻塞）

必须由人选择的缺口（仓库没写明的后端日志来源等）不写进会话流水，立刻另存：

```text
artifacts/inbox/questions/Q-<YYYYMMDD>-<nnn>.md
```

回答后同一文件移到 `artifacts/inbox/archived-question/`。字段与命令见 `docs/spec/work-task.md`。提问后把对应 `work/tasks` 标为 `blocked`。回答写入任务的 `## Decisions`；可复用的通道说明策展到 `knowledge/wiki/domain-notes/`。

## 5. 密钥

- 可用 `account_id` 指向 `data/sut-accounts.local.yaml` 的条目。
- 禁止密码、token、Cookie、Authorization 原文。
