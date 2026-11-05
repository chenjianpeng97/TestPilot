---
name: derive-test-design
version: 1.1.0
group: internal
description: Write assets/testdesign/<sut>/<slug>.md from a work task plus usecases, domain-notes, explore, or design notes. Use when the task type is test-design or the user asks for a test design. Do not invent click paths that are not in evidence or a cited source.
---

# Derive test design

## Scope

- **Write**: `assets/testdesign/<sut>/<slug>.md`，并让任务的 `outputs` 指向它。
- **Read**: `work/tasks/<id>.md`、`knowledge/wiki/usecases`、`knowledge/wiki/domain-notes`、`knowledge/wiki/explore`、`knowledge/wiki/design`、`knowledge/requirements/`、`INDEX.project.md`。
- **Must follow**: `docs/spec/test-design-syntax.md`、`docs/spec/work-task.md`。

## Steps

1. 若还没有任务：`tuner-task create --type test-design --title … --input <已有知识路径>`。
2. 只根据 inputs 里点名的知识写范围、不测、风险、策略、点击路径、用例大纲。没有页面流或证据支撑的点击行不要编。
3. 「执行反馈」写「无」。
4. front-matter：`kind: testdesign`，`task_id` 指向任务，`source` 或 `evidence` 至少一项。
5. 校验并署名：

```bash
uv run tuner-task validate assets/testdesign/<sut>/<slug>.md
uv run tuner-workspace meta stamp assets/testdesign/<sut>/<slug>.md --kind testdesign
```

6. 把该路径挂到任务上：`uv run tuner-task bind <TASK> --output assets/testdesign/<sut>/<slug>.md`。
7. 留痕：`uv run tuner-workspace changelog append --area testdesign --skill derive-test-design --action <新建|更新> --items assets/testdesign/<sut>/<slug>.md --version <1.0.0 或 旧->新>`；改已有设计时 bump `version`。

## Template

```markdown
---
kind: testdesign
id: <slug>
title: <一句话>
sut: <sut>
task_id: TASK-YYYYMMDD-nnn
source: <knowledge/requirements/REQ-… 或 knowledge/wiki/...>
version: 1.0.0
confidence: high
evidence: []
---

# <title>

## 范围

## 不测

## 风险

## 策略

## 点击路径

| id | 页面流 | 操作 | 期望 |
| --- | --- | --- | --- |

## 用例大纲

## 执行反馈

| run_id | task_id | 结果 | 要回写的结论 |
| --- | --- | --- | --- |

## 证据与来源
```

## Hard rules

- 需要日志证据时先看 `doctor` 的 `ports.log-source`；没有绑定适配器才 `tuner-task ask --topic sut-log-source`，不要写死 SSH、日志接口或 Rancher。
- 不把响应体、截图、密钥抄进设计。
