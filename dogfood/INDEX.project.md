<!-- version: 0.2.0 -->
# INDEX.project — dogfood workspace 业务资产地图

> 被测系统 = TestPilot 平台本身（tuner-testkit）。生成任何测试/资产前先读这里；平台能力地图见仓根 `INDEX.md`。
> 标有 `auto:` 围栏的区块由 `tuner-workspace index render` 从 `artifacts/catalogs/workspace.json`
> 确定性渲染，不要手改；人工区由 `maintain-index` skill 增量维护。

## 1. 知识层（knowledge/，随被测系统演进）

### 1.1 DDL（自动区）

<!-- auto:begin:ddl -->
| datasource | 表 | 路径 |
| --- | --- | --- |
| _(暂无)_ |  |  |
<!-- auto:end:ddl -->

### 1.2 wiki / 需求 / 缺陷（自动区：路径与元数据）

<!-- auto:begin:knowledge -->
| 路径 | 类别 | id / domain | version | confidence / status | 标题 |
| --- | --- | --- | --- | --- | --- |
| `knowledge/wiki/domain-notes/platform/roadmap.md` | domain-notes | platform | 1.1.0 | high | TestPilot（tuner-testkit）平台路线图（A → B → C → D） |
| `knowledge/wiki/usecases/platform/qa-daily-journeys.md` | usecases | platform | 1.0.0 | high | 「QA 一天」验收剧本 |
| `knowledge/wiki/usecases/workbench/lightweight-user.md` | usecases | workbench | 1.0.0 | high | 轻量用户使用工作台 |
<!-- auto:end:knowledge -->

人工区（用途 / 采信说明；wiki 目录见 `knowledge/wiki/index.md`）：

| 路径 | domain | source | confidence | 一句话用途 |
| --- | --- | --- | --- | --- |
| `knowledge/wiki/domain-notes/platform/roadmap.md` | platform | plan 2026-09-22 | high | 平台路线图 A→B→C→D、版本节奏 |
| `knowledge/wiki/usecases/platform/qa-daily-journeys.md` | platform | plan 2026-09-22 §A7 | high | 「QA 一天」五条日常路径与判据 |
| `knowledge/wiki/usecases/workbench/lightweight-user.md` | workbench | plan 2026-09-22 §B | high | 低代码成员使用工作台的主流程与验收 |

## 2. 资产层（assets/ 与 packages/，随测试工作演进）

### 2.1 业务 SQL 副本（自动区）

<!-- auto:begin:sql -->
| 文件 | 路径 |
| --- | --- |
| _(暂无)_ |  |
<!-- auto:end:sql -->

### 2.2 测试设计 / 用例 / 测试单 / 报告（自动区）

<!-- auto:begin:assets -->
| 路径 | 类别 | domain | source | confidence | 标题 |
| --- | --- | --- | --- | --- | --- |
| _(暂无)_ |  |  |  |  |  |
<!-- auto:end:assets -->

### 2.3 API Objects（自动区）

<!-- auto:begin:api_objects -->
| method + path | 文件 |
| --- | --- |
| _(暂无)_ |  |
<!-- auto:end:api_objects -->

### 2.4 Page Objects（自动区）

<!-- auto:begin:page_objects -->
| page | 文件 |
| --- | --- |
| _(暂无)_ |  |
<!-- auto:end:page_objects -->

### 2.5 Action Words（自动区）

<!-- auto:begin:action_words -->
| word_id | 名称 | 类别 |
| --- | --- | --- |
| `db_seed.sample_seed` | 示例造数（dry-run） | db_seed |
<!-- auto:end:action_words -->

## 3. 工具层（apps/，自动区）

<!-- auto:begin:apps -->
| 工具 | 运行 | 用途 | 交接文档 |
| --- | --- | --- | --- |
| `sample_log_source` | `python -m apps.sample_log_source` | log-source 端口的参考适配器：从本地 data/sample-logs 按时间窗读日志并脱敏。 | `apps/sample_log_source/README.md` |
| `sample_tool` | `python -m apps.sample_tool` | 离线生成带标签的样例行；工作台表单与 QA 一天验收的 fixture。 | `apps/sample_tool/README.md` |
<!-- auto:end:apps -->

### 3.1 端口适配器（自动区；绑定写在 config `PORTS`，见 `docs/spec/ports.md`）

<!-- auto:begin:ports -->
| 端口 | 工具 | 模块（写进 config PORTS） | 用途 |
| --- | --- | --- | --- |
| `log-source` | `sample_log_source` | `apps.sample_log_source` | log-source 端口的参考适配器：从本地 data/sample-logs 按时间窗读日志并脱敏。 |
<!-- auto:end:ports -->

## 4. 测试层（tests/，自动区）

<!-- auto:begin:features -->
| feature | 场景数 | 标签 |
| --- | --- | --- |
| `tests/features/platform/qa_daily_journeys.feature` | 5 | platform, dogfood |
| `tests/features/workbench/knowledge_browse.feature` | 3 | workbench, dogfood |
| `tests/features/workbench/run_history.feature` | 2 | workbench, dogfood |
| `tests/features/workbench/run_tool.feature` | 4 | workbench, dogfood |
| `tests/features/workbench/tool_catalog.feature` | 4 | workbench, dogfood |
<!-- auto:end:features -->

## 5. 交付物（artifacts/）

- `artifacts/inbox/`：agent 任务记录（gitignore）。
- `artifacts/evidence/<run_id>/`：探索证据（gitignore）。
- `artifacts/catalogs/workspace.json`：`tuner-workspace catalog` 产物（gitignore）。
- 追溯靠被维护对象自己的 `CHANGELOG.md`（`docs/spec/metadata-conventions.md` §4）。
