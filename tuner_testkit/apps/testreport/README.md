# testreport — 测试单出 GJB438B 测试报告

## 需求背景

测试单（`assets/testsheet/<轮次>/`）填完后，要交一份 GJB438B 格式的软件测试报告。报告里的用例数、首轮与回归、缺陷等级矩阵都应从测试单算出来，不手抄；不随轮次变化的内容（系统名称、供需方、软硬件环境、通过准则）放在画像 `assets/testreport/profiles/<sut>.md`。

流程是三步：`stats --check` 让测试单自洽，`draft` 起草报告 Markdown（`assets/testreport/<sut>/<yyyy-mm>/<slug>.md`，入库、可审），`render` 套模板出 docx（`artifacts/runs/<run_id>/`，不入库）。编排见 skill `generate-testsheet-report`。

## 试用场景

- 适用：测试单按 `maintain-testsheet` 1.1 的格式填写，缺陷表有「严重程度」「类型」「状态」列。
- 多份测试单合成一份报告：`stats` / `draft` 传多个目录，同一用例以后面那份的结果为准。
- 不适用：behave / pytest 回归报告（用 `generate-test-report`）；测试设计点击报告（用 `run-test-execution`）。
- 依赖：`stats`、`draft` 无 extra；`render` 和 `build-template` 要 `report` extra（docxtpl）。下游仓 `uv sync --inexact --extra report`（脚手架的 `report` extra 指向 `tuner-testkit[report]`）。
- 模板：默认用 kit 自带的 `templates/gjb438b.docx`（通用 GJB438B 章节，无单位信息）。版式不同的样例用 `build-template` 转成自己的模板，放在仓内（例 `data/testreport/<名称>.docx`），`render --template` 指过去。

取数规则：

| 报告项 | 从哪来 |
| --- | --- |
| 设计 / 执行 / 通过 / 未通过 / 未执行 | 测试单结果折算：通过 → 通过；失败 → 未通过；阻塞、忽略、结果为空（待执行）→ 未执行。`stats` 另给 `blocked` / `ignored` / `pending` 分别的数量 |
| 首轮 | 缺陷表引用的用例在首轮算执行且未通过 |
| 回归 | 引用它的缺陷都是已解决或关闭的用例算重用；都关闭且有结果的算回归执行 |
| 缺陷矩阵 | 严重程度 致命/严重/一般/轻微 → 1–4级；类型分列；状态关闭算归零，其余算遗留 |
| 结论 | 画像「通过准则」：遗留了不允许的等级，或不允许却有未执行用例 → 未通过测试；没有准则或遗留缺陷未定级 → 待评审 |
| 测试周期 / 测试人员 / 版本 | 测试单「本轮信息」的日期、测试人、版本 |
| 引用文档 | 画像「引用文档」，加测试单本身和「依据」里的每一项；依据是仓内 `.md` 时取其标题，发布日期取「发布日期 / 建立日期 / 编制日期」行或 front-matter `date`、`created` |

`draft` 遇到要人补的内容写 `<!-- TODO … -->`，`render` 见到 TODO 拒绝执行。画像里有意留空的表格写一行全是 `/`，不会出 TODO。

## 运行方式

在下游仓根目录运行（或设 `TUNER_ROOT`），相对路径都按仓根解析。

```text
uv run tuner-testreport --help
uv run tuner-testreport stats assets/testsheet/<轮次> --check
uv run tuner-testreport draft assets/testsheet/<轮次> --sut <sut> --slug <slug> [--env <env>] [--task TASK-…]
uv run --extra report tuner-testreport render assets/testreport/<sut>/<yyyy-mm>/<slug>.md [--template <模板.docx>]
uv run --extra report tuner-testreport build-template <样例报告.docx> --out data/testreport/<名称>.docx
```

离线单测（平台仓）：

```text
uv run pytest tuner_testkit/apps/testreport/tests -q
```

## 运行示例

```text
uv run tuner-testreport stats assets/testsheet/260101登录 --check
uv run tuner-testreport draft assets/testsheet/260101登录 --sut demo --slug 260101-login --task TASK-20260101-001
uv run --extra report tuner-testreport render assets/testreport/demo/2026-01/260101-login.md
```

预期：

- `stats --check` 每个问题一行 `issue level=… code=… sheet=… line=…`，最后一行 `rows total=… errors=… warnings=…`；有 error 退出码 1。
- `draft` 有 error 时拒绝起草；成功时打印 `todo …`（要补的地方）和 `draft out=… todos=N`。已存在的报告要 `--force` 才覆盖。
- `render` 输出 `artifacts/runs/<UTC>-testreport-<slug>/<文档标题>.docx` 与 `manifest.json`，再打开 docx 自检，打印 `check leftover_tags=… case_rows=… ok|failed`：有残留模板标签或第 6 章行数不等于用例数时退出码 1。Word 打开时会提示更新目录域，选「是」刷新页码。
- `build-template` 只在换样例时用：按样例里的文字与表头找位置，写 `--out` 指定的模板。样例版式变了导致找不到锚点时报 `TemplateLayoutError`。
- 加 `--json` 时最后一行是 envelope JSON（`status`、`outputs`、`artifacts`）。
