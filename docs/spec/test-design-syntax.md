---
name: test-design-syntax
version: 1.0.0
description: assets/testdesign 的章节、front-matter，以及被 test-execution 回写的执行反馈。
---

# 测试设计（test-design-syntax）

> 一篇文档描述一条可执行的测试设计。它记「测什么、怎么点、期望是什么」。
> `knowledge/wiki/design/` 仍只记一条路由的副作用，不要混进本文。

## 1. 路径

```text
assets/testdesign/<sut>/<slug>.md
```

## 2. Front-matter

```yaml
kind: testdesign
id: order-create
title: 订单创建
sut: order
task_id: TASK-20260924-001
source: knowledge/wiki/usecases/order/create.md
version: 1.0.0
confidence: high
evidence:
  - artifacts/evidence/20260924T000000Z-order-create/
```

`source` 与 `evidence` 至少有一个。`tuner-task validate <path>` 会检查。

## 3. 正文

八个二级标题都要在，缺信息写「无」：

```markdown
## 范围
## 不测
## 风险
## 策略
## 点击路径
## 用例大纲
## 执行反馈
## 证据与来源
```

「点击路径」用表，供 `test-execution` 逐行点击：

```markdown
| id | 页面流 | 操作 | 期望 |
| --- | --- | --- | --- |
| P1 | web.order_create@v1 / submit | 填写必填项并点击提交 | 列表出现新订单 |
```

「执行反馈」由执行任务回写，不在设计阶段编造结果：

```markdown
| run_id | task_id | 结果 | 要回写的结论 |
| --- | --- | --- | --- |
| 20260924T000000Z-order | TASK-20260924-002 | failed | P1 提交后列表未刷新，见证据截图 |
```

证据只写 `artifacts/evidence/<run_id>/` 下的相对路径，不粘贴截图、响应体或日志原文。
