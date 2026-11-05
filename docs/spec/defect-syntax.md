---
name: defect-syntax
version: 1.0.0
description: 缺陷库 knowledge/defects/：一个缺陷一个文件，固定编号、front-matter、章节与历史表；由 maintain-defectlib 记录，python -m tuner_testkit.defects 校验。
---

# 缺陷库规范（defect-syntax）

> 缺陷和用例一样，是仓库里规定位置、规定模板的记录，不是要同步到别处的东西。仓库里的缺陷库就是缺陷的记录处。
> 记录和更新走 skill `maintain-defectlib`；`python -m tuner_testkit.defects check` 做确定性校验。
> 缺陷是被测系统的知识，放在知识层 `knowledge/defects/`；发现它的测试单在 `assets/testsheet/`。

## 1. 位置

```text
knowledge/defects/
├── DEF-<yyyymmdd>-<nnn>.md   # 一个缺陷一个文件，文件名就是 id
└── CHANGELOG.md              # 维护流水（tuner-workspace changelog append --area defects）
```

目录里只放这两类文件（可选 `README.md` 写本仓的分级口径）。

## 2. 编号

- `DEF-<发现日期 yyyymmdd>-<当天顺序号 3 位>`，例 `DEF-20261104-001`。
- 取号：`uv run python -m tuner_testkit.defects next-id [--date 2026-11-04]`。
- 同一个缺陷跨轮次复现、修复、回归、关闭，都更新同一个文件，不新开编号。编号发出后不改、不复用；
  误报用 `status: 关闭` 并在历史写明原因，不删文件。

## 3. 模板

`uv run python -m tuner_testkit.defects new --title … --severity … --type …` 按下面的模板建文件（正文写 `（待填）`，填完才能通过校验）：

```markdown
---
kind: defect
id: DEF-20261104-001
title: 部分退款后库存未回填
severity: 严重
type: 编码
status: 激活
blocking: false
found: 2026-11-04
found_in: assets/testsheet/261104订单/testsheet.md#D1
testcase: Order-Refund-partial-amount
requirements: [REQ-order-refund-partial]
sut_version: "3.2.0"
env: uat
version: 1.0.0
---

# DEF-20261104-001 部分退款后库存未回填

## 现象

部分退款成功后，商品库存没有加回。

## 环境

uat，被测版本 3.2.0，账号 account:qa-admin。

## 前置条件

订单 42 已支付，商品 A-1 库存 10。

## 复现步骤

1. 对订单 42 发起部分退款 1 件
2. 退款审核通过
3. 查看商品 A-1 库存

## 预期结果

库存回到 11。

## 实际结果

库存仍为 10；`stock-service` 日志 `release skipped: refund not confirmed`。

## 证据

- assets/testsheet/261104订单/evidence/Order-Refund-partial-amount.png
- artifacts/evidence/20261104T101500Z-refund/logs/stock.log

## 历史

| 日期 | 轮次 | 状态 | 说明 |
| --- | --- | --- | --- |
| 2026-11-04 | 261104订单 | 激活 | 首次发现（D1） |
```

## 4. 字段

| 字段 | 必填 | 取值 |
| --- | --- | --- |
| `kind` | 是 | `defect` |
| `id` | 是 | 等于文件名 |
| `title` | 是 | 一句话，不含编号 |
| `severity` | 是 | `致命` / `严重` / `一般` / `轻微`（与测试单缺陷表一致，报告里依次是 1 到 4 级） |
| `type` | 是 | `需求` / `设计` / `编码` / `文档` / `其它` |
| `status` | 是 | `激活`（待处理）/ `已解决`（已修复待回归）/ `关闭`（回归通过或不再跟踪） |
| `blocking` | 是 | `true` / `false`：是否阻塞后续测试 |
| `found` | 是 | 发现日期 `YYYY-MM-DD` |
| `found_in` | 是 | 发现它的测试单与缺陷编号 `assets/testsheet/<轮次>/testsheet.md#D<n>`；不是在测试单里发现的（探索、线上反馈）写 `/` |
| `testcase` | 是 | 用例 ID；不对应用例写 `/` |
| `requirements` | 否 | 需求 ID 列表（`knowledge/requirements/<REQ-ID>.md`） |
| `sut_version` | 否 | 被测版本 |
| `env` | 否 | 命名环境 |
| `version` | 是 | 文件版本，每次更新 bump |

## 5. 章节

固定顺序：`现象`、`环境`、`前置条件`、`复现步骤`、`预期结果`、`实际结果`、`证据`、`历史`。

- 必填：`现象`、`复现步骤`（至少一条 `1. ` 编号步骤）、`预期结果`、`实际结果`、`历史`。其余可省略，省略就不写标题。
- 一级标题是 `# <id> <title>`。
- `历史` 是一张表，表头 `| 日期 | 轮次 | 状态 | 说明 |`，一次状态变化一行；最后一行的状态等于 front-matter 的 `status`。
- 证据只写路径（测试单 `evidence/`、`artifacts/evidence/<run_id>/`），不贴响应原文、不贴密钥。账号写 `account:<id>`。

## 6. 与测试单、报告的关系

- 测试单的「缺陷」表仍按 `maintain-testsheet` 的七列记录本轮编号 `D<n>`；记录进缺陷库后在该行「现象」末尾补 `（DEF-…）`。
- 后续轮次回归：只改原缺陷文件的 `status`、在历史追加一行、bump `version`。
- 报告的缺陷节引用 `DEF-…`。需求 → 用例 → 缺陷的追溯由 `requirements` 与 `testcase` 字段承担。

## 7. 校验

```bash
uv run python -m tuner_testkit.defects check          # 默认 knowledge/defects
```

检查：文件名与 `id`、编号格式与日期、必填字段与取值、一级标题、章节集合与顺序、必填章节非空、`（待填）` 未残留、
历史表最后一行状态、`found_in` 指向的测试单存在且没有被两个缺陷重复记录、`testcase` 在 `assets/testcases/` 存在、`requirements` 在 `knowledge/requirements/` 存在。
`tuner-workspace doctor` 的 `knowledge.defects` 报告各状态数量与校验错误。
