---
kind: testcase-index
title: 测试用例模块索引
version: 1.1.0
confidence: high
---

# 测试用例模块索引

规范：`docs/spec/testcase-syntax.md`。维护流程：skill `maintain-testcases`。

一个套件一个目录，一条用例一个文件。用例 ID 是 `<id_prefix>-<slug>`，例如 `User-Login-valid-credentials`，在全库是唯一键。模块怎么划、套件写到哪，以本页和各模块 `README.md` 为准。

## 放置规则

- 新用例优先归入已有模块的套件目录。现有模块的范围都覆盖不住时，才新建 `assets/testcases/<模块>/`。
- 套件目录名等于套件标题。用例文件名等于用例 ID。不属于任何一条用例的说明写在 `<套件>/README.md`。
- 不写密码、token、Cookie。账号只写 `account_id`。

## 模块

| 模块 | 目录 | 范围 | 状态 |
| --- | --- | --- | --- |
| _（尚无）_ | | 本仓是平台仓。业务系统的模块与用例写在下游 workspace 的 `assets/testcases/`，不要把被测业务用例堆进平台索引。 | 规划中 |

## 给编写的人

1. 先看上表，选定模块。
2. 打开该模块的 `README.md`，确认套件边界。
3. 用 skill `maintain-testcases` 在套件目录新增 `<用例ID>.md`，并沿用该套件的 `id_prefix`。
4. 改完跑 `python -m tuner_testkit.testcases assets/testcases`。
