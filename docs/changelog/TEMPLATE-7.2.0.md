# tuner-testkit 7.2.0 — 任务文件夹与附件、任务与测试单归档

MINOR，向后兼容：旧的单文件任务继续可用，不需要迁移。

## 变化

- **任务是文件夹**：`tuner-task create` 生成 `work/tasks/TASK-x/task.md` 加 `attachments/`。`task.md` 的字段与章节不变。附件由人手动放入，或由 LLM 用 `tuner-task attach <id> --file <路径>` 复制进去；`attach` 拒绝带密码、token 赋值的文本文件和越界路径。
- **任务归档**：`tuner-task archive <id>` 移到 `work/tasks/archived/`；`status --all` 才列出已归档任务；编号不复用。
- **测试单归档**：`tuner-testreport archive <轮次>` 移到 `assets/testsheet/archived/<轮次>/` 并自动写 changelog。缺陷的 `found_in` 写原路径仍通过校验。
- **归档由用户决定**：两条命令都不拦截任何状态、不会自动归档。`--check` 只预览，列出归档前要告诉用户的 `warnings`（任务未 done、还有未答阻塞问题；测试单有待执行或阻塞用例、stats 有 error）。LLM 协助归档的流程是：先 `--check`，把 warnings 告诉用户，用户确认再执行。
- 规范与组件：`docs/spec/work-task.md` 1.3.1，`work-task.mdc` 1.4.1，`maintain-testsheet` 1.5.1，`execute-testsheet` 1.3.1，`derive-test-design` 1.2.0，`generate-testsheet-report` 1.2.1。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.2.0"` → `uv sync` → `tuner-dna sync --prune`

## 需要迁移

不需要。已有的 `work/tasks/TASK-x.md` 照常读写；对它执行 `attach` 时会先移成 `TASK-x/task.md`。
