---
name: knowledge-syntax
version: 1.1.0
description: knowledge/ 知识层：被测系统的知识，随被测系统与业务演进；ddl / raw / wiki / requirements / defects 的目录、元数据与维护方式。
---

# 知识层规范（knowledge-syntax）

> `knowledge/` 装**被测系统**的知识：表结构、原始文档、业务讲解、需求、缺陷。它不随测试工作演进，
> 而随被测系统和业务演进；测试工作产生的资产（设计、用例、测试单、报告、自动化对象）在资产层
> `assets/` + `packages/`，见 `docs/spec/assets-knowledge-syntax.md`。
> 配套硬约束见 `.cursor/rules/knowledge.mdc`。业务资产地图见 `INDEX.project.md` §1。

## 1. 目录

```text
knowledge/
├── ddl/<datasource>/<table>.sql        # 自动区：tuner-dump-ddl 生成；流水 knowledge/ddl/CHANGELOG.md
├── raw/<来源>/<文件>                    # 原件：需求文档、API 文档（OpenAPI）、会议纪要、禅道导出。只读
├── wiki/
│   ├── index.md                        # wiki 目录：每页一行（路径 + 一句话摘要），先读这里
│   ├── log.md                          # wiki 维护流水（ingest / lint），见 metadata-conventions §4
│   ├── domain-notes/<domain>/<name>.md # 业务讲解、字段含义、角色权限、环境约束；被测系统说明 <sut>/profile.md
│   ├── usecases/<domain>/<name>.md     # 业务场景与流程（从需求或用例导出整理）
│   ├── explore/<app>/<name>.md         # 探索得到的能力清单 / 站点地图（evidence 指回 artifacts/evidence）
│   └── design/<app>/<route-slug>.md    # API 与数据库效果（见 design-knowledge-syntax）
├── requirements/
│   ├── <REQ-ID>.md                     # 一条需求一个文件
│   └── CHANGELOG.md
└── defects/
    ├── <DEF-ID>.md                     # 一个缺陷一个文件，模板见 defect-syntax.md
    └── CHANGELOG.md
```

- 「在哪、用什么」（源码本机路径、API 文档地址、日志通道）是配置，写在 `config` 的 `KNOWLEDGE` / `PORTS` / `OPS`（`docs/spec/config-syntax.md`）。
  wiki 页只解释为什么、怎么理解，引用配置键名，不重复写地址与密钥。
- pre-7.0 的 workspace 把 ddl 与 wiki 四类放在 `assets/` 下。用 `tuner-workspace migrate knowledge`（默认只打印计划，`--apply` 执行）迁移；
  测试报告画像 `assets/domain-notes/testreport/` 迁到 `assets/testreport/profiles/`。

## 2. LLM Wiki 维护方式

wiki 采用 LLM Wiki 模式：raw 不可变，wiki 由 LLM 增量编译和维护，人负责提供来源和提问。skill 是 `maintain-wiki`。

- **ingest**：把 `raw/` 的新原件编译进 wiki。写或更新相关页面（摘要、实体、规则、流程），在 `index.md` 登记，在 `log.md` 追加一行；
  需求文档同时拆成 `requirements/<REQ-ID>.md`。
- **query**：先读 `index.md` 再下钻；有长期价值的回答回写成 wiki 页。
- **lint**：找孤立页（`index.md` 没登记）、过时主张（与新 raw 或 DDL 矛盾）、缺来源、需求无用例覆盖。结论写进 `log.md`。

## 3. 元数据

wiki 页（YAML front-matter）：

```markdown
---
kind: domain-note            # domain-note / usecase / explore / design / wiki-page
domain: order
source: knowledge/raw/prd/order-v3.pdf   # 指回原件、需求 ID 或 evidence
date: 2026-11-04
version: 1.0.0
confidence: high             # high = 人工核实过，LLM 优先采信
evidence: []                 # explore / design 必填：artifacts/evidence/<run_id>
---
```

需求（`requirements/<REQ-ID>.md`）：

```markdown
---
kind: requirement
id: REQ-order-refund-partial      # REQ-<slug>，与文件名一致
title: 部分退款
source: knowledge/raw/prd/order-v3.pdf#3.2
status: active                    # draft / active / deprecated
version: 1.0.0
---

# REQ-order-refund-partial 部分退款

## 描述
## 验收标准
## 业务规则
```

缺陷（`defects/<DEF-ID>.md`）：像用例一样有固定编号、front-matter、章节与历史表，完整规范见 `docs/spec/defect-syntax.md`；
建文件用 `python -m tuner_testkit.defects new`，校验用 `python -m tuner_testkit.defects check`，记录与回归走 skill `maintain-defectlib`。
缺陷库就是缺陷的记录处，不同步到别处。

## 4. 可追溯

- 用例 front-matter 的 `requirements: [REQ-…]`（或 `source` 写需求 ID）指向 `knowledge/requirements/`，`tuner_testkit.testcases` 校验 ID 存在。
- 缺陷指回发现它的测试单、用例与需求。需求 → 用例 → 缺陷的覆盖情况由 `tuner-workspace doctor` 的 `trace.requirements` 报告。
- 每个单元改动 bump `version`，库根 changelog 追加一行（`docs/spec/metadata-conventions.md` §4）。

## 5. 禁止

- 改写 `raw/` 原件的语义（只能补放到正确目录、补 front-matter 旁注文件）。
- 在 `knowledge/` 写密码、token、Cookie；在 wiki 里重复写 config 的地址与密钥。
- 凭空编造表名、字段、业务规则：wiki 主张必须有 `source` 或 `evidence`。
