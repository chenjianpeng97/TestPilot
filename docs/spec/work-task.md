---
name: work-task
version: 1.3.1
description: 入库任务 work/tasks、阻塞式人类提问，以及和测试设计、证据、测试报告的闭环。
---

# 工作任务（work-task）

> 人在 workspace 里发布的任务是 Agent 的事务上下文，写入 Git。
> 会话流水仍在 `artifacts/inbox/<utc>-<agent>-<slice>.md`（gitignore）。
> 必须由人回答的问题写到 `artifacts/inbox/questions/`，不猜 SSH、日志接口或 Rancher。

## 1. 路径

```text
work/tasks/TASK-<YYYYMMDD>-<nnn>/             # 入库：一个任务一个文件夹
  task.md                                   # 主文件，front-matter 与章节见 §3
  attachments/                              # 附件：需求截图、客户邮件、接口样例、导出表……
work/tasks/archived/TASK-<YYYYMMDD>-<nnn>/    # 已完成任务的归档，结构同上
artifacts/inbox/questions/Q-<YYYYMMDD>-<nnn>.md        # 未回答；gitignore
artifacts/inbox/archived-question/Q-<YYYYMMDD>-<nnn>.md # 已回答；gitignore
```

`work/**` 的提交 scope 是 `work`。

### 任务文件夹与附件

- `tuner-task create` 生成 `TASK-x/task.md` 和空的 `attachments/`。`task.md` 是唯一的状态来源，CLI 只改它。
- 附件由人手动放进 `attachments/`，或由 LLM 用 `tuner-task attach <id> --file <路径> [--name 子路径]` 复制进去（可带子目录，不覆盖同名文件）。人直接拷文件也行，`status` 的 JSON 会列出 `attachments`。
- 附件是任务的原始素材，不是证据：运行产生的截图、网络、日志仍走 `artifacts/evidence/` 并用 `bind --evidence` 指向。
- 附件入库，所以不能含密码、token、Cookie；`attach` 会拒绝带这类赋值的文本文件，二进制文件由人自己把关。
- 任务正文用相对路径引用附件，例如 `[客户补充](attachments/需求补充.md)`。
- 任务用 `tuner-task archive <id>` 移到 `work/tasks/archived/`，避免活跃任务堆积。**是否归档由用户决定**，CLI 不拦截任何状态，不会自动归档（`finish` 也不会）。LLM 协助归档：先 `tuner-task archive <id> --check` 预览，把 `warnings`（未 done、还有未答的阻塞问题）告诉用户，用户确认后再执行。归档后 `status <id>` 仍能查到，`status --all` 才会列出已归档的任务，编号不会被复用。
- 旧的单文件 `TASK-x.md` 继续可读可写；对它执行 `attach` 时会先移成 `TASK-x/task.md`。问题文件不入库；人答完后的结论写回任务的 `## Decisions`，需要留下的通道说明再策展到 `knowledge/wiki/domain-notes/`。

## 2. 任务类型

| type | 输入 | 产出 | 证据 |
| --- | --- | --- | --- |
| `explore` | URL / account_id | `knowledge/wiki/explore/` | `artifacts/evidence/<run_id>/` |
| `test-design` | 用例、domain-notes、explore、design | `assets/testdesign/<sut>/<slug>.md` | 需求或探索来源，见 test-design-syntax |
| `test-execution` | 已存在的 testdesign（front-matter `design`） | `assets/testreport/<sut>/<yyyy-mm>/<slug>.md` | 同一次 run 的截图、网络、接口响应、日志 |

`test-execution` 按测试设计里的「点击路径」跑 `page_test run` 或 behave UI，不代替测试设计，也不承担纯 API 回归。

状态：`open` → `in_progress` → `done`。存在未回答的阻塞问题时为 `blocked`。全部答完后回到 `in_progress`。

## 3. Front-matter

```yaml
kind: task
id: TASK-20260924-001
title: 订单创建端到端
type: test-execution
status: open
objective: 按测试设计点完订单创建并写出报告
scope: [order-create]
inputs: []
outputs: []
design: assets/testdesign/order/create.md
evidence: []
questions: []
```

作者与日期用 `tuner-workspace meta stamp`（`tuner-task create` 会调用）。禁止写入密码、token、Cookie。

## 4. 人类提问循环

仓库里还没有该通道时才问。先看 `tuner-workspace doctor` 的 `ports.log-source`：config `PORTS` 已绑定适配器就直接用
（`python -m apps.<name> --since … --until … --json`）。

后端日志是**端口**（`docs/spec/ports.md`）：kit 只定契约，不提供实现，因为各团队取日志的方式差别很大。
没有绑定适配器时，主题固定为 `sut-log-source`，选项固定为：

| id | 含义 |
| --- | --- |
| `ssh-dir` | SSH 到指定目录读日志文件 |
| `log-api` | 调用已有日志接口 |
| `rancher-api` | 用 Rancher API 拉 Pod 日志 |
| `skip` | 本轮不做日志通道 |

```bash
tuner-task ask --task TASK-20260924-001 --topic sut-log-source \
  --prompt "仓库没有写明后端日志从哪取"

tuner-task answer Q-20260924-001 --option rancher-api \
  --note "命名空间见 env_local 的 OPS.rancher" \
  --curate knowledge/wiki/domain-notes/order/log-source.md
```

- 提问立刻落盘，并把任务标为 `blocked`。只挡住依赖该答案的回写；不依赖日志的点击可以先做完，但在回答前不要编写取日志实现，也不要选定通道。
- 回答后（`answer` 输出的 `next` 会列出）：`create-app` 按 `log-source` 契约在 workspace `apps/` 写适配器，`tool.py` 声明
  `port="log-source"`；`maintain-config` 在 `PORTS` 绑定、在 `env_local.ENVIRONMENTS.<env>.OPS` 写通道地址与密钥；`health-check` 复检。
  适配器不进 kit。`--curate` 的 wiki 页只写通道是什么、为什么，地址与密钥留在 config。
- `tuner-task answer` 把问题文件从 `questions/` 移到 `archived-question/`，未回答的问题仍只留在 `questions/`。同一天的新问题编号会计入归档，避免复用已回答的 ID。
- `--note` 只留可入库的指向。CLI 拒绝 `password=` / `token:` / `Bearer …` 这类赋值。
- `skip` 表示报告里日志证据写「无」，设计上的日志断言保持未验证。
- `tuner-task finish` 在仍有 `status: open` 且 `blocking: true` 的问题时失败。
- `test-execution` 收口时，`design` 与 `outputs` 里的路径必须已在磁盘上。

## 5. 和测试设计的闭环

```text
test-design（点击路径 + 期望）
  → task type=test-execution
  → 端到端点击
  → artifacts/evidence/<run_id>/（截图、network、api、logs）
  → assets/testreport（每条路径的结果 + 证据路径）
  → 回写 testdesign「执行反馈」，assets/testdesign/CHANGELOG.md 追加一行
  → 通道类决定写入 Decisions，并在需要时策展 domain-notes
```

点击失败只记入「执行反馈」。接口与落库不一致时写 Decision，并引用 evidence 相对路径。点出设计没覆盖的副作用时策展 `knowledge/wiki/design/`，风险行指向同一 `run_id`。
