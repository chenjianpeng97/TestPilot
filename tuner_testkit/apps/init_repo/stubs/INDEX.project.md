<!-- version: 0.2.1 -->
# INDEX.project — TestPilot 业务资产地图

> 本仓被测系统（SUT）的知识与资产地图。生成任何测试、资产、工具前先读这里。
> AI 组件见 `.cursor/REGISTRY.md`；kit 自带工具用 `tuner-workspace catalog --out -` 列出。
> 各类资产与工具的数量见根目录 `DASHBOARD.md`（skill `refresh-dashboard` 运行 `tuner-dashboard refresh` 生成，不要手改）。
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
| _(暂无)_ |  |  |  |  |  |
<!-- auto:end:knowledge -->

人工区（用途 / 采信说明；wiki 目录见 `knowledge/wiki/index.md`）：

- _(暂无)_

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
| _(暂无)_ |  |  |
<!-- auto:end:action_words -->

## 3. 工具层（apps/，自动区）

<!-- auto:begin:apps -->
| 工具 | 运行 | 用途 | 交接文档 |
| --- | --- | --- | --- |
| _(暂无)_ |  |  |  |
<!-- auto:end:apps -->

### 3.1 端口适配器（自动区；绑定写在 config `PORTS`，见 `docs/spec/ports.md`）

<!-- auto:begin:ports -->
| 端口 | 工具 | 模块（写进 config PORTS） | 用途 |
| --- | --- | --- | --- |
| _(暂无)_ |  |  |  |
<!-- auto:end:ports -->

## 4. 测试层（tests/，自动区）

<!-- auto:begin:features -->
| feature | 场景数 | 标签 |
| --- | --- | --- |
| _(暂无)_ |  |  |
<!-- auto:end:features -->

## 5. 交付物（artifacts/）

见 `docs/spec/artifacts-layout.md`：`evidence/`、`inbox/`、`runs/`、`reports/`、`catalogs/`、`exports/`（均 gitignore）。
追溯靠被维护对象自己的 `CHANGELOG.md`（见 `docs/spec/metadata-conventions.md` §4）。
