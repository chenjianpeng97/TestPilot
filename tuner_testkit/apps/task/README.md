# task

把人发布的任务写进 Git（`work/tasks/TASK-*/task.md`，同目录 `attachments/` 放任务附件），并把必须由人回答的问题写进本机信箱
`artifacts/inbox/questions/`。回答后移到 `artifacts/inbox/archived-question/`。规范：`docs/spec/work-task.md`。

## 运行方式

无 extra。

```bash
tuner-task create --type test-design --title "订单创建测试设计" --scope order-create
tuner-task create --type test-execution --title "订单创建端到端" \
  --design assets/testdesign/order/create.md

tuner-task ask --task TASK-20260924-001 --topic sut-log-source \
  --prompt "仓库没有写明后端日志从哪取"

tuner-task answer Q-20260924-001 --option rancher-api \
  --note "命名空间见 env_local 的 OPS.rancher" \
  --curate knowledge/wiki/domain-notes/order/log-source.md

tuner-task bind TASK-20260924-001 --output assets/testdesign/order/create.md \
  --evidence artifacts/evidence/20260924T000000Z-order/
tuner-task attach TASK-20260924-001 --file D:/需求补充.md   # 复制到 attachments/
tuner-task questions
tuner-task finish TASK-20260924-001
tuner-task archive TASK-20260924-001 --check   # 预览归档提示（不移动）
tuner-task archive TASK-20260924-001           # 用户确认后移到 work/tasks/archived/
tuner-task status --all                  # 连已归档的一起列出
tuner-task validate assets/testdesign/order/create.md
```

`sut-log-source` 的选项是 `ssh-dir`、`log-api`、`rancher-api`、`skip`。
后端日志是 `log-source` 端口（`docs/spec/ports.md`）：kit 不实现取日志。回答 `sut-log-source` 后，`answer` 的 JSON 带 `next`：
用 `create-app` 按端口契约在 workspace `apps/` 写适配器，用 `maintain-config` 在 config `PORTS` / `OPS` 绑定。
`--curate` 只接受 `knowledge/wiki/domain-notes/**/*.md`（pre-7.0 布局仍接受 `assets/domain-notes/`）。
`--note` 里出现 `token:`、`password=` 或 `Bearer …` 时命令失败。

stdout 是一行 JSON。
