---
name: maintain-page-objects
version: 2.2.1
group: internal
description: Creates or updates page assets under packages/page_objects/ on the tuner_testkit.page_test runtime (PageModel element table + declarative flows, or BasePage escape hatch) following page-objects-syntax.md. Use when UI steps fail due to locators, new UI flows are needed, selector leakage must be removed from steps, or doctor reports locator rot.
---

# Maintain Page Objects (tuner_testkit.page_test)

## Scope

- **Primary goal**: 把 UI 定位与交互封装成可被驱动直跑、可被平台可视化的页面资产。
- **Write scope**: `packages/page_objects/**` only.
- **Must follow**: `docs/spec/page-objects-syntax.md`；API 用法见 `tuner_testkit/page_test/USAGE.md`。
- **Runtime**: `tuner_testkit.page_test`（与 `tuner_testkit.api_test` 同构的三层解耦）。

## 选范式

- **声明式 `PageModel`（默认）**：线性流程（填表、点按、等待、断言）。动作是
  `flows` 里的有序 step 数据，因此能被平台渲染成步骤表、被 page recorder 生成。
- **`BasePage` 子类（逃生舱）**：只在需要 `if` / `for` / `try` 时用——翻页找行、
  条件性关引导弹窗、轮询状态、跨页编排。**不要**为了绕过声明式而滥用。

两种范式共用同一份 `elements` 声明，所以元素层的处理完全一致。

## Hard rules

- **定位器只能写在 `ElementSpec.locators` 里**。steps、action words、以及页面资产的
  方法体内不得出现 `page.locator(...)` / `get_by_*` / xpath / css 字面量。
- **每个元素给足候选**（这是本运行库稳定性的核心）：语义定位 + `test_id`（如有）
  至少两个，按优先级排序。只给一个候选就上线等于放弃 fallback。
- **locator 优先级**：
  1. `role`（必须配 `name` 或 `has_text`）/ `label` —— 顺带验证可访问性
  2. `test_id` —— 对 DOM/样式改动韧性最强，作首选也完全可接受
  3. 结构化 CSS（层级不超过 `max_css_depth`）
  4. 相对 XPath —— 仅当 CSS 表达不出（`text()` / `ancestor::` / `following-sibling::`），
     必须 `confidence="fragile"` + `note`
- **纯文本定位（`get_by_text`）不作首选** —— 多语言切换会让它全线失效。
- **绝对 XPath 禁止**；`nth(i)` 寻址默认禁（豁免须在该页 `locator_policy` 声明 + 写 `note`）；
  `.first` 消歧允许。
- **禁止固定 sleep**：用 `WaitForElement` / `WaitForUrl` / `WaitForResponse` 或 `expect(...)`。
- **无 host、无凭据**：`url_path` 只写路径；敏感值写 `{{password}}` 占位符。
- **id 约定**：`<app>.<page_slug>@v<major>`；文件路径 `packages/page_objects/<app>/<page_slug>.py`。
- 页面资产不做业务数据拉取、不发 API 请求、不写 SQL。

## Output expectations

- 一个文件一个页面资产：声明式用模块级 `<page_slug>_page_v1 = PageModel(...)`；
  类范式用 `class <PageSlug>Page(BasePage)`。
- 元素声明带 `description` 与 `role_hint`（平台可视化要用）。
- 每个 flow 带 `description` 与 `example_params`（让 `run --example` 可一键跑）。
- 页面级 `asserts` / `extracts` 只放**页面自身的稳定契约**（`open()` 时执行）；
  flow 级断言写在该 flow 的 steps 里。
- 不需要任何装饰器就会出现在 `tuner-workspace catalog` 与工作台的只读页面清单里（静态扫描 `page_id`）。

## Quick validation（必须跑）

```bash
python -m tuner_testkit.page_test validate            # policy + 元素/flow 引用完整性，不启浏览器
python -m tuner_testkit.page_test describe <page_id>  # 确认平台看到的元素表与步骤表
```

自检清单：

- 没有 locator 泄漏到 steps / action words。
- 每个元素 ≥ 2 个候选；fragile 候选都有 `note` 且有备用。
- flow 引用的元素与子 flow 都存在（`validate` 会报）。
- 提取变量名不重复。

## 处理 locator 失效（doctor 驱动）

```bash
python -m tuner_testkit.page_test doctor <page_id>
```

- 报告说「首选定位器连续失效，实际靠 [i] ... 兜住」→ 把命中的候选提到首选，
  把失效的下移或删除，并在 commit 里说明依据（doctor 报告即证据）。
- 报告说「仅有脆弱候选」→ 优先建议研发补 `data-testid`；未补齐前用 `scope` /
  `has_text` 收窄并标 `fragile` + `note`。
- **不要**写脚本自动改写资产（自愈级别三本仓不做）：采纳建议必须是显式改动。

## Pipeline expectation (required)

- 页面资产改动必须有证据：浏览器通道（config `CHANNELS.browser`）snapshot、`run_summary`、`doctor` 报告，
  或 `tuner-page-recorder`（`python -m tuner_testkit.apps.page_recorder`）会话产出。
- 缺证据时明确声明不确定性，不要凭猜测拟合 selector。
- 本地 `PageDriver` 用于自检 / health check / pytest 回归；BDD 流程的**网络证据捕获
  仍必须走浏览器通道**（默认 Playwright MCP；`bdd-pipeline-gates.mdc` Gate 1），不得用本地驱动或
  `tuner-page-recorder` 替代。

## Changelog（追溯）

`tuner-page-recorder` / `tuner-recorder` 会自动追加 `packages/page_objects/CHANGELOG.md`。手工新增或修改页面资产时，同一个提交里：

```bash
uv run tuner-workspace changelog append --area page_objects --skill maintain-page-objects \
  --action <新建|更新> --items <page_id> --reason "<证据 run_id 或 doctor 报告>"
```

## 离线单测

用 `tuner_testkit.page_test.testing` 的 `FakePage` / `make_driver` / `patch_playwright`
给新资产补一条 happy path 与一条 fallback 用例（不装 playwright 也能跑）。
