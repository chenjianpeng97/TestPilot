# 资产层规范（assets-knowledge-syntax）

> 资产层是**测试资产活文档**：随测试工作演进。Markdown 资产在 `assets/`，Python 资产在 `packages/`
> （`api_objects/`、`page_objects/`、`action_words/`，见各自的 syntax 规范）。
> 被测系统的知识（DDL、wiki、需求、缺陷）在知识层 `knowledge/`，见 `docs/spec/knowledge-syntax.md`。
> 配套硬约束见 `.cursor/rules/assets-knowledge.mdc`；资产地图见 `INDEX.project.md` §2。
> （文件名保留历史名称；7.0 起 ddl、domain-notes、usecases、explore、design 已移到 `knowledge/`。）

## 1. 目录分类

```text
assets/
├── sql/<name>.sql                                  # 人类可读的业务 SQL 副本（实现在 packages/ 的 action word / 服务）
├── testdesign/<sut>/<slug>.md                      # 测试设计（test-design-syntax）；执行反馈回写在此
├── testdesign/CHANGELOG.md
├── testcases/README.md                             # 功能用例集总索引（testcase-syntax）
├── testcases/CHANGELOG.md                          # 用例库维护流水
├── testcases/<模块>/README.md                      # 模块范围与套件清单
├── testcases/<模块>/<套件>/README.md               # 套件说明与用例索引
├── testcases/<模块>/<套件>/<用例ID>.md             # 一条用例一个文件
├── testsheet/CHANGELOG.md                          # 测试单组单与执行流水
├── testsheet/<轮次>/testsheet.md                   # 一次测试单。步骤链接本目录副本
├── testsheet/<轮次>/testcase/<模块>/<套件>/<用例ID>.md  # 从用例库复制的本次步骤
├── testsheet/<轮次>/evidence/                      # 手工执行的截图等
├── testreport/<sut>/<yyyy-mm>/<slug>.md            # 测试报告（整理稿，入库）
└── testreport/profiles/<sut>.md                    # 报告画像：不随轮次变化的报告字段（tuner-testreport draft 读取）
```

- `testsheet/<轮次>/testsheet.md` 不写 YAML 头，正文按测试单格式。同目录 `testcase/` 是用例库的原样副本，保留复制时的文件头。
  组单见 skill `maintain-testsheet`，执行见 `execute-testsheet`。
- 回归的原始结果在 `artifacts/reports/<run_id>/`（不入库），整理后的报告才进 `assets/testreport/`。

## 2. 文件头元数据

Markdown 资产写 YAML front-matter；字段家族见 `docs/spec/metadata-conventions.md`，按类：

- 测试设计：`docs/spec/test-design-syntax.md`。
- 用例：`docs/spec/testcase-syntax.md`（含 `requirements`、`data` 追溯字段）。
- 报告：`kind: testreport`，见 metadata-conventions §2。
- SQL 副本用顶部 `--` 注释写 `domain / source / date / version / confidence`。

`confidence: high` 表示人工核实过，LLM 优先采信。

## 3. 可追溯

- 每份资产能回答「从哪来、何时、什么版本、多可信」：`source` 指回需求 ID、wiki 页或 evidence。
- 被维护的库（testcases、testsheet、testdesign，以及 `packages/` 三类对象）每次维护：单元 bump `version`，
  库根 changelog 追加一行（`tuner-workspace changelog append`），见 metadata-conventions §4。

## 4. 与其它层的关系

- 用例的依据来自 `knowledge/`：需求（`knowledge/requirements/`）、业务规则（`knowledge/wiki/`）、真实列名（`knowledge/ddl/`）。
- 造数 action word 从 `knowledge/ddl/<datasource>/<table>.sql` 取列名；业务 SQL 同时镜像到 `assets/sql/`。
- 生成任何测试或资产前，先查 `INDEX.project.md`。
