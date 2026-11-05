---
name: python-playwright-page-objects
user-invocable: false
description: Python + Playwright 的 Page Object 规范（中文）。以 tuner_testkit.page_test 的 PageModel（元素表 + 声明式 flow）为主范式、BasePage 逃生舱为辅；强调多定位器备用、locator_policy 确定性拦截、动作/断言分离与 AI 可维护边界。
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
---

# python-playwright-page-objects

## 目标

- **目标**：把 UI 定位与交互封装在 `packages/page_objects/`，让 steps 只表达业务意图。
- **关键边界**：steps 禁止直接写 selector；selector 只能出现在页面资产的**元素声明表**里。
- **运行库**：所有页面资产由 `tuner_testkit.page_test` 驱动（用法见 `tuner_testkit/page_test/USAGE.md`），
  与 `tuner_testkit.api_test` 同构：资产是冻结的声明式 dataclass，执行引擎独占 IO 与日志。

## 两种范式（都由同一套元素声明支撑）

| 范式 | 什么时候用 | 动作怎么写 |
| --- | --- | --- |
| **声明式 `PageModel`**（主） | 线性流程：填表、点按、等待、断言 | `flows` 里的有序 step 序列（数据，可被 recorder 生成、被平台渲染成步骤表） |
| **`BasePage` 子类**（逃生舱） | 循环 / 条件分支 / 跨页编排 | 普通 Python 方法，元素仍经 `self.el(name)` 访问 |

**逃生舱逃掉的只有「动作序列的声明式表达」，元素层一点没逃**：定位器始终在
`elements` 里，因此两种范式都享受多定位器 fallback、平台元素表可视化与 doctor 体检。

## 目录与模块组织

- `packages/page_objects/<app>/<page_slug>.py` —— 一个文件一个页面资产
  - 声明式：模块级变量 `<page_slug>_page_v1 = PageModel(...)`
  - 类范式：`class <PageSlug>Page(BasePage)`
- `packages/page_objects/session.py` —— 凭据与单文件回放（对标 `api_objects/auth.py`），**不是**资产
- 组件复用：把公共元素抽成模块级 `ElementSpec` 常量共享，或用 `scope` 收窄到容器内

## 设计原则（必须遵守）

- **单一职责**：一个资产只描述一个页面。
- **封装**：对外只暴露「业务动作」与「业务断言」，隐藏 locator 与等待细节。
- **id 约定**：`<app>.<page_slug>@v<major>`（如 `plane.login@v1`）；破坏性变更才升版本。
- **无 host**：`url_path` 与 `Goto(path=...)` 只写路径；host 由
  `tuner_testkit.config.get_ui_base_url()` 运行时注入。
- **无凭据**：敏感值写 `{{password}}` 占位符，运行时从入参或环境变量代入，**永不落盘**。
- **目录可见**：`tuner-workspace catalog` 静态扫描 `packages/page_objects/**` 中带 `page_id` 的 `PageModel` /
  `BasePage` 文件，不需要装饰器；`session.py` / `pages.py` 等辅助模块会被跳过。
- **可审计**：脆弱 locator 必须声明 `confidence="fragile"` 并在 `note` 写清风险与替代建议。

## Locator 策略

### 元素 = 一组按优先级排序的候选

稳定性的核心不是「挑一个完美 locator」，而是**每个元素挂多个候选**：运行时按序探测，
首个命中者胜出。首选失效时测试照常通过（自愈级别一），同时产出健康事件让降级可见
（自愈级别二），避免资产静默腐烂。

```python
ElementSpec(
    name="username_input",
    description="登录用户名输入框",
    role_hint="textbox",
    locators=(
        LocatorSpec("label", "用户名"),                 # 首选：语义定位
        LocatorSpec("test_id", "login-username"),       # 备用：测试标识
    ),
)
```

### 推荐优先级（从高到低）

1. **角色/标签语义定位**：`get_by_role`（配 `name=`）、`get_by_label`
   —— 同时验证了可访问性，这是它排在 test_id 之前的**唯一**理由。
2. **测试标识**：`get_by_test_id` —— 对 DOM 与样式改动**韧性最强**；若研发愿意补
   `data-testid`，它是最省心的选择，作为首选也完全可接受。
3. **结构化 CSS**：语义与 test_id 都不可用时。
4. **相对 XPath**：仅当 CSS 表达不出来（需要 `text()` 精确匹配或
   `ancestor::` / `following-sibling::` 轴向定位，典型是 `<div>` 拼的伪表格）。
   必须 `confidence="fragile"` + `note`。

**纯文本定位（`get_by_text`）不在第 1 档**：文案定位在多语言场景下会全线崩溃——切一次
语言包所有定位器一起断。文本只应作为 role 的限定词（`get_by_role("button", name="登录")`
安全；`get_by_text("登录")` 不安全）。

### 禁止与豁免

`locator_policy` 把下列约束变成**运行时可执行的校验**（违规抛 `LocatorPolicyError`），
而不是只写在文档里靠自觉：

- **绝对 XPath**（`/html/body/div[3]`）—— 硬禁（`allow_absolute_xpath=False`）。
- **依赖 DOM 层级的超长 CSS** —— 层级数超过 `max_css_depth`（默认 4）即拒。
- **索引寻址**（`nth(3)`）—— 默认禁（`allow_index=False`）。用位置代替业务标识，
  插一行数据就错位。确需豁免时在该页 `locator_policy={"allow_index": True}` 并在
  候选的 `note` 写清为何没有稳定标识——豁免因此成为资产里一行**可审计的声明**。
- **索引消歧**（`.first`）—— **允许**（`allow_disambiguation=True`）。页面有多个视觉
  等价元素时取任一都对，这是消除 Playwright strict mode violation 的标准手段；
  与「寻址」是两件事，不可一并禁掉。
- **稳定性下限**：每个元素至少 `min_stable_candidates`（默认 1）个 stable 候选；
  首选是 fragile 时必须有备用（`require_fallback_for_fragile`）。
- **探测超时**：`probe_timeout_ms`（默认 1500）。这是多定位器机制的**性能护栏**——
  Playwright 默认超时 30 秒，若首选已失效且候选很多，每次都等满超时会让单个元素
  卡上百秒。候选探测超时必须短，且与「等待条件成立」的超时分离。

用 `python -m tuner_testkit.page_test validate` 一次性校验全部资产。

### 链式收窄（提升唯一性）

候选过于宽泛时，先缩小容器再定位子元素，用 `scope` 引用父元素：

```python
elements = {
    "cart": ElementSpec(name="cart", locators=(LocatorSpec("test_id", "shopping-cart"),)),
    "price_cell": ElementSpec(
        name="price_cell",
        locators=(LocatorSpec("role", "cell", name="价格", scope="cart"),),
    ),
}
```

也可用 `has_text` 过滤：`LocatorSpec("role", "listitem", has_text="iPhone", first=True)`。

## 动作与断言

### 声明式 flow

```python
login_page_v1 = PageModel(
    id="example.login@v1",
    name="登录页",
    description="账号密码登录；前置条件：无",
    url_path="/login",
    elements=ELEMENTS,
    inputs_schema={
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "required": True},
    },
    ready=(WaitForElement("username_input", state="visible"),),
    flows={
        "login": PageFlow(
            name="login",
            description="输入账号密码并提交",
            steps=(
                Fill("username_input", "{{username}}"),
                Fill("password_input", "{{password}}"),
                Click("submit_button"),
                WaitForUrl("/dashboard"),
                AssertVisible("welcome_banner"),
            ),
            example_params={"username": "demo", "password": "demo"},
        ),
    },
)
```

- **动作 step**：`Fill` / `Click` / `Check` / `Select` / `Press` / `Hover` / `Upload`
- **断言 step**：`AssertVisible` / `AssertHidden` / `AssertText` / `AssertUrl` / `AssertCount`
- **提取 step**：`ExtractText` / `ExtractAttribute` / `ExtractCount`，提取的变量可被后续 step 用 `{{name}}` 引用
- **`asserts` / `extracts`（页面级）**：描述**页面自身的稳定契约**，在 `open()` 时执行。
  flow 级断言写在该 flow 的 steps 里——因为 UI flow 常常导航离开本页，不能像 API 那样
  每次调用后都套同一组页面断言。

### 类范式的动作与断言

对外方法命名沿用同一套约定：动作 `login()` / `open()` / `search()`；断言 `assert_*()`。
断言方法内部负责等待条件成立（不让 steps 写 sleep）。

```python
class OrderListPage(BasePage):
    """订单列表页。前置条件：已登录且有列表查看权限。"""

    page_id = "example.order_list@v1"
    name = "订单列表页"
    url_path = "/orders"
    elements = {...}

    def find_order_across_pages(self, order_no: str, *, max_pages: int = 10) -> bool:
        """翻页查找订单号 —— 声明式 step 序列表达不了的循环。"""
        for _ in range(max_pages):
            if self.el("row").locator.filter(has_text=order_no).count():
                return True
            if not self.el("next_page").locator.is_enabled():
                return False
            self.el("next_page").locator.click()
        return False

    def assert_not_empty(self) -> None:
        """业务断言：列表非空。"""
        if not self.el("row").locator.count():
            raise AssertionError("订单列表为空")
```

`BasePage` **不暴露** `self.page`。确需裸 Playwright API 时走 `self.driver.raw_page`——
命名刺眼是故意的，出现它就意味着绕过了元素声明表，需要在 review 里被看见。

## 等待策略（必须）

- 只允许等待「条件成立」，**禁止固定 sleep**：用 `WaitForElement` / `WaitForUrl` /
  `WaitForResponse`，或类范式里的 `expect(...)` 轮询。
- 优先等待 UI 条件：元素可见/隐藏、URL 变化、文本出现。
- 需要等接口时用 `WaitForResponse(path_contains=..., status=200)`，只等与业务强相关的响应。
- 幂等的定位/点击类 step 可加 `retry=RetryPolicy(attempts=2)`；提交类默认不重试。

## 与 steps / pytest 的契约（必须）

- steps 只能调用业务动作与断言，或 `model.run("<flow>")`；**禁止**访问元素声明与 locator。
- steps 里**不得**出现 `page.locator(...)` / `get_by_*` / xpath / css 字面量。
- 页面资产不做业务数据拉取，不发 API 请求，不写 SQL。

## 独立运行与体检

```bash
python -m tuner_testkit.page_test list                     # 已发现的资产
python -m tuner_testkit.page_test describe example.login@v1
python -m tuner_testkit.page_test validate                 # 静态校验，不启浏览器
python -m tuner_testkit.page_test run example.login@v1 --flow login --example --headed
python -m tuner_testkit.page_test doctor example.login@v1  # 定位器健康度 + 建议 patch
python packages/page_objects/example/login.py         # 单文件回放（__main__ 块）
```

**用途边界**：本地驱动供页面资产自检 / health check / pytest 回归 / doctor 体检。
BDD 资产生成流程中的**网络证据捕获仍必须走浏览器通道**（默认 Playwright MCP，按 config `CHANNELS.browser`，见 `docs/spec/browser-channel.md` 与
`.cursor/rules/bdd-pipeline-gates.mdc` Gate 1），本地驱动不得替代。

### doctor 与「自愈」的边界

- **级别一 · 运行时降级**：多定位器 fallback 本身，首选失效时测试不红。
- **级别二 · 审计**：`doctor` 聚合健康事件，输出体检报告与**建议** patch。
- **级别三 · 持久化自愈**（自动改写资产源码）：**本仓不做**。工具悄悄改代码没人 review，
  等发现时已说不清页面到底改了什么。采纳建议由人或 AI 显式执行，doctor 报告即证据。

## 录制（tuner-page-recorder）

本地维护 CLI：headed Playwright 打开真实页面，人工点/填/浏览时直播冻结 `PageModel`
到 `packages/page_objects/<app>/<page_slug>.py`。交接文档见 `tuner_testkit/apps/page_recorder/README.md`。
同一 headed 会话还要冻 API Object 用 `python -m tuner_testkit.apps.recorder`（见 `tuner_testkit/apps/recorder/README.md`）。

```bash
uv sync --extra bdd
uv run python -m tuner_testkit.apps.page_recorder --app plane --flow login --url /sign-in --scan
```

- 页面脚本把 `click` / `change` / `submit` 经 `expose_binding` 送回 Python；
  `tuner_testkit.page_test.harvest` 按 locator 优先级生成多候选，过 `validate_locator`
  丢掉绝对 XPath / 超长 CSS / 无 name 的裸 role。
- 密码与敏感键当场写成 `{{password}}`，真值不落盘。
- 按归一化后的 `url_path` 切资产；已有 `PageModel` **元素候选并集、flow steps 追加**
  （连续相同 Click 压成一次）。不覆盖手写 `BasePage` 文件。
- **不是** BDD Gate 1 的替代：网络证据仍走 Playwright MCP。不生成 `If`/`Loop`。
- 会话结束向 `packages/page_objects/CHANGELOG.md` 追加一行。

## AI 生成/更新页面资产的约束

- **允许修改范围**：`packages/page_objects/**`。
- **禁止**：在 steps 中新增 selector；在资产中固化 host 或凭据；用绝对 XPath 或索引寻址。
- **新增元素时给足候选**：语义定位 + `test_id`（如有）至少两个，让 fallback 有意义。
- **locator 不稳定时**：优先建议研发补 `data-testid`；未补齐前用语义定位 + `scope` /
  `has_text` 收窄，并把脆弱候选标 `fragile` + `note`。
- **改动需有证据**：Playwright MCP snapshot、`run_summary`、`doctor` 报告，或 `tuner-page-recorder` 会话产出。

## 离线单测

`tuner_testkit.page_test.testing` 提供 `FakePage` / `make_driver` / `patch_playwright`，
不装 playwright、不起浏览器也能测页面资产的 flow、插值、fallback 与断言：

```python
def test_login_flow(monkeypatch):
    patch_playwright(monkeypatch)
    page = FakePage()
    page.register("label=用户名")
    page.register("test_id=login-password")
    page.register("role=button name=登录")

    result = login_page_v1.set_inputs({"username": "demo", "password": "x"}).run(
        "login", driver=make_driver(page)
    )
    assert result.ok
```

## 反模式（Bad examples）

- **在 steps 里拿 locator 点击** —— 泄露实现细节，维护地狱。
- **页面资产把元素声明暴露给 steps** —— 同上。
- **把断言复制到 steps 里到处散落** —— 应下沉到断言 step 或 `assert_*` 方法。
- **用 `nth()` 寻址核心元素** —— 数据一变就错位（`.first` 消歧是另一回事，允许）。
- **只给一个 locator 就上线** —— 首选一失效就直接红，等于放弃了 fallback 能力。
- **给 fragile 候选不写 `note`** —— 后来者无法判断该不该换、换成什么。
