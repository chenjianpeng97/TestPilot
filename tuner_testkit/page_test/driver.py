"""PageDriver —— 独占 Playwright IO、多定位器解析、脱敏日志与失败截图。

对位 ``tuner_testkit.api_test.client.ApiClient``：资产只描述「是什么」，driver 负责
「怎么发生」。playwright 是**惰性 import**，因此 ``describe`` / ``validate`` /
``catalog`` 与离线单测在没装 playwright 的环境下也能跑。

用途边界：本地驱动供 page object 自检 / health check / pytest 回归 / doctor 体检。
BDD 资产生成流程里的**网络证据捕获仍必须走 Playwright MCP**（见
``.cursor/rules/bdd-pipeline-gates.mdc`` Gate 1），本地驱动不得替代。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping

from tuner_testkit.logging import log_assertion, log_ui_action, log_warn

from .errors import (
    DriverError,
    ElementNotFoundError,
    ElementSpecError,
    PageAssertError,
    StepExecutionError,
)
from .health import HealthCollector, append_events, artifacts_dir
from .locator import DEFAULT_POLICY, LocatorPolicy, ResolvedLocator, resolve_element
from .model import PageModel, PageResult, StepOutcome
from .steps import (
    AssertCount,
    AssertHidden,
    AssertText,
    AssertUrl,
    AssertVisible,
    Check,
    Click,
    ExtractAttribute,
    ExtractCount,
    ExtractText,
    Fill,
    GoBack,
    Goto,
    Hover,
    Press,
    Reload,
    RetryPolicy,
    RunFlow,
    Screenshot,
    Select,
    Step,
    Upload,
    WaitForElement,
    WaitForResponse,
    WaitForUrl,
    resolve_value,
)

_MAX_FLOW_DEPTH = 5
_MASK = "***"


def _import_playwright() -> Any:
    try:
        import playwright.sync_api as api
    except ImportError as exc:  # pragma: no cover - 依赖缺失路径
        raise DriverError(
            "playwright 未安装。安装：uv sync --extra bdd 然后 uv run playwright install chromium"
        ) from exc
    return api


def _as_url_pattern(pattern: str) -> Any:
    """``re:xxx`` 视为正则；否则按子串匹配（转义后包成正则）。"""
    if pattern.startswith("re:"):
        return re.compile(pattern[3:])
    return re.compile(re.escape(pattern))


@dataclass
class _ExecContext:
    model: PageModel
    policy: LocatorPolicy
    params: dict[str, Any]
    extracted: dict[str, Any] = field(default_factory=dict)
    outcomes: list[StepOutcome] = field(default_factory=list)
    depth: int = 0

    def values(self) -> dict[str, Any]:
        """占位符查找表：flow 入参 + 已提取变量（后者可被后续 step 引用）。"""
        return {**self.params, **self.extracted}


@dataclass
class PageDriver:
    """页面执行引擎。用 :meth:`launch` 自起浏览器，或 :meth:`attach` 复用外部 page。"""

    base_url: str
    page: Any
    policy: LocatorPolicy = DEFAULT_POLICY
    collector: HealthCollector = field(default_factory=HealthCollector)
    default_timeout_ms: int = 10_000
    #: 运行结束是否把健康事件落盘（供 doctor 跨运行聚合）
    persist_health: bool = True
    #: 失败时是否截图
    screenshot_on_failure: bool = True

    _owned: tuple[Any, ...] = field(default=(), repr=False)
    _responses: list[tuple[str, int]] = field(default_factory=list, repr=False)
    #: 元素 -> 上次命中的候选下标。每次 execute 清空，见 resolve() 的说明。
    _locator_hints: dict[str, int] = field(default_factory=dict, repr=False)
    #: 最近解析过的 page_id，供 close() 时把残余事件归档到正确的资产名下
    _last_page_id: str = field(default="", repr=False)

    # -- 生命周期 -------------------------------------------------------

    @classmethod
    def launch(
        cls,
        *,
        headless: bool = True,
        base_url: str | None = None,
        browser: str = "chromium",
        storage_state: Any = None,
        slow_mo: float = 0,
        viewport: Mapping[str, int] | None = None,
        policy: LocatorPolicy | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> "PageDriver":
        """自起浏览器。``close()`` 或 ``with`` 退出时释放。"""
        api = _import_playwright()
        if base_url is None:
            from tuner_testkit.config import get_ui_base_url

            base_url = get_ui_base_url()

        playwright = api.sync_playwright().start()
        try:
            browser_type = getattr(playwright, browser, None)
            if browser_type is None:
                raise DriverError(f"未知 browser {browser!r}（chromium/firefox/webkit）")
            browser_obj = browser_type.launch(headless=headless, slow_mo=slow_mo)
            context = browser_obj.new_context(
                storage_state=storage_state,
                viewport=dict(viewport) if viewport else None,
                **kwargs,
            )
            page = context.new_page()
        except Exception:
            playwright.stop()
            raise

        driver = cls(
            base_url=base_url.rstrip("/"),
            page=page,
            policy=LocatorPolicy.from_mapping(policy),
            _owned=(context, browser_obj, playwright),
        )
        driver._install_response_recorder()
        return driver

    @classmethod
    def attach(
        cls,
        page: Any,
        *,
        base_url: str | None = None,
        policy: LocatorPolicy | Mapping[str, Any] | None = None,
    ) -> "PageDriver":
        """复用外部注入的 page（behave ``context.page`` / pytest fixture / MCP 场景）。"""
        if page is None:
            raise DriverError("attach() 需要一个 Playwright Page")
        if base_url is None:
            from tuner_testkit.config import get_ui_base_url

            base_url = get_ui_base_url()
        driver = cls(
            base_url=base_url.rstrip("/"),
            page=page,
            policy=LocatorPolicy.from_mapping(policy),
        )
        driver._install_response_recorder()
        return driver

    def flush_health(self, page_id: str = "") -> None:
        """归档已收集的健康事件并清空缓冲。

        ``collector`` 只持有「当前这一段运行」的事件：``PageResult.locator_events``
        必须只反映本次运行（否则 ``fallbacks`` 会把历史降级算进来），落盘也不能把
        同一批事件重复 append（否则 doctor 的命中率会被重复计数污染）。
        """
        events = self.collector.snapshot()
        self.collector.clear()
        if not events or not self.persist_health:
            return
        target = page_id or self._last_page_id
        if target:
            append_events(target, events)

    def close(self) -> None:
        # 类范式的 Python 自定义动作不走 execute，事件会留在缓冲里，这里补归档
        self.flush_health()
        for resource in self._owned:
            try:
                resource.stop() if hasattr(resource, "stop") else resource.close()
            except Exception as exc:  # noqa: BLE001
                log_warn("page_driver_close_failed", error=f"{type(exc).__name__}: {exc}")
        self._owned = ()

    def __enter__(self) -> "PageDriver":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def raw_page(self) -> Any:
        """裸 Playwright Page 逃生通道。

        命名刺眼是故意的：page object 应当只用 :meth:`resolve` / ``BasePage.el()``，
        出现 ``raw_page`` 就意味着绕过了元素声明表，需要在 review 时被看见。
        """
        return self.page

    def _install_response_recorder(self) -> None:
        """缓冲响应事件，让线性的 ``WaitForResponse`` 也能等到「已发生」的响应。"""
        self._responses = []
        try:
            self.page.on(
                "response",
                lambda response: self._responses.append(
                    (str(response.url), int(response.status))
                ),
            )
        except Exception as exc:  # noqa: BLE001 - 非致命，仅失去 wait_for_response 能力
            log_warn("page_driver_response_hook_failed", error=f"{type(exc).__name__}: {exc}")

    # -- 元素解析 -------------------------------------------------------

    def resolve(
        self,
        element_name: str,
        *,
        elements: Mapping[str, Any],
        policy: LocatorPolicy | None = None,
        page_id: str = "",
    ) -> ResolvedLocator:
        """多候选顺序探测。命中备用候选时打日志，让首选失效可见。

        本次运行内已命中过的候选会被挪到探测队首：失效的首选要等满
        ``probe_timeout_ms`` 才降级，同一元素被反复引用时这笔开销会累加。
        提示只在单次 ``execute`` 内有效，因此每个 flow 的首次解析仍从声明的首选
        开始探测，doctor 统计到的「首选是否还活着」不会被缓存掩盖。
        """
        seen_before = element_name in self._locator_hints
        if page_id:
            self._last_page_id = page_id
        resolved = resolve_element(
            self.page,
            element_name,
            elements=elements,
            policy=policy or self.policy,
            page_id=page_id,
            sink=self.collector,
            prefer_index=self._locator_hints.get(element_name),
        )
        self._locator_hints[element_name] = resolved.index
        if resolved.fallback_used and not seen_before:
            # 同一元素在一次运行里可能被解析多次，日志只报第一次；
            # 完整的降级次数留在 locator_events 里交给 doctor 统计。
            log_ui_action(
                "locator_fallback",
                target=element_name,
                page_id=page_id,
                used_index=resolved.index,
                used=resolved.spec.signature(),
                preferred=(resolved.preferred or resolved.spec).signature(),
            )
        return resolved

    # -- 执行 -----------------------------------------------------------

    def execute(
        self,
        model: PageModel,
        *,
        steps: tuple[Step, ...],
        flow: str,
        params: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> PageResult:
        """跑一段 step 序列。断言失败抛 :class:`PageAssertError`（携带诊断 result）。"""
        ctx = _ExecContext(
            model=model,
            policy=LocatorPolicy.from_mapping(model.locator_policy)
            if model.locator_policy
            else self.policy,
            params=dict(params or {}),
        )
        default_timeout = timeout_ms or self.default_timeout_ms
        self._locator_hints.clear()
        # 归档上一段（可能来自类范式的 Python 动作）的事件，让本次 result 只含本次
        self.flush_health()

        try:
            self._run_steps(steps, ctx=ctx, default_timeout=default_timeout)
        except (PageAssertError, StepExecutionError, ElementNotFoundError, ElementSpecError) as exc:
            result = self._build_result(
                model,
                flow=flow,
                ctx=ctx,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                capture_screenshot=True,
            )
            self.flush_health(model.id)
            if isinstance(exc, PageAssertError):
                raise PageAssertError(str(exc), result=result) from exc
            raise type(exc)(str(exc), result=result) from exc

        result = self._build_result(model, flow=flow, ctx=ctx, ok=True)
        self.flush_health(model.id)
        return result

    def _build_result(
        self,
        model: PageModel,
        *,
        flow: str,
        ctx: _ExecContext,
        ok: bool,
        error: str = "",
        capture_screenshot: bool = False,
    ) -> PageResult:
        failed = next((o for o in ctx.outcomes if not o.ok), None)
        screenshot = ""
        if capture_screenshot and self.screenshot_on_failure:
            screenshot = self.screenshot(f"{model.id}_{flow}_failed")
        return PageResult(
            ok=ok,
            page_id=model.id,
            flow=flow,
            url=self._safe(lambda: str(self.page.url)),
            title=self._safe(lambda: str(self.page.title())),
            extracted=dict(ctx.extracted),
            steps=tuple(ctx.outcomes),
            locator_events=self.collector.snapshot(),
            screenshot=screenshot,
            failed_step=failed.summary if failed else "",
            error=error,
        )

    @staticmethod
    def _safe(getter: Callable[[], str]) -> str:
        try:
            return getter()
        except Exception:  # noqa: BLE001 - 页面可能已关闭
            return ""

    def screenshot(self, name: str) -> str:
        safe = re.sub(r"[^0-9A-Za-z_.\-]+", "_", name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = artifacts_dir("screenshots") / f"{safe}_{stamp}.png"
        try:
            self.page.screenshot(path=str(target), full_page=True)
        except Exception as exc:  # noqa: BLE001
            log_warn("page_screenshot_failed", error=f"{type(exc).__name__}: {exc}")
            return ""
        return str(target)

    def _run_steps(
        self, steps: tuple[Step, ...], *, ctx: _ExecContext, default_timeout: int
    ) -> None:
        for step in steps:
            if isinstance(step, RunFlow):
                # 纯编排：子 flow 的 step 会各自留痕，再为 RunFlow 记一条只会
                # 让轨迹里多出一个顺序错乱的条目（它必然晚于自己的子步骤）。
                self._dispatch(step, ctx=ctx, default_timeout=default_timeout)
                continue

            index = len(ctx.outcomes)
            started = time.monotonic()
            resolved: ResolvedLocator | None = None
            try:
                resolved = self._dispatch(step, ctx=ctx, default_timeout=default_timeout)
            except Exception as exc:
                ctx.outcomes.append(
                    StepOutcome(
                        index=index,
                        op=step.op,
                        summary=step.describe(),
                        ok=False,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        element=str(getattr(step, "element", "") or ""),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                raise
            ctx.outcomes.append(
                StepOutcome(
                    index=index,
                    op=step.op,
                    summary=step.describe(),
                    ok=True,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    element=str(getattr(step, "element", "") or ""),
                    locator_index=resolved.index if resolved else -1,
                    fallback_used=bool(resolved and resolved.fallback_used),
                )
            )

    def _dispatch(
        self, step: Step, *, ctx: _ExecContext, default_timeout: int
    ) -> ResolvedLocator | None:
        retry: RetryPolicy | None = getattr(step, "retry", None)
        attempts = max(1, retry.attempts if retry else 1)
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._dispatch_once(step, ctx=ctx, default_timeout=default_timeout)
            except (ElementNotFoundError, PageAssertError, StepExecutionError) as exc:
                last = exc
                if attempt + 1 >= attempts:
                    break
                log_warn(
                    "page_step_retry",
                    op=step.op,
                    attempt=attempt + 1,
                    of=attempts,
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._pause(retry.backoff_ms if retry else 200)
        assert last is not None
        raise last

    def _pause(self, milliseconds: int) -> None:
        """重试退避与轮询间隔。不是「固定 sleep 代替条件等待」。"""
        try:
            self.page.wait_for_timeout(milliseconds)
        except Exception:  # noqa: BLE001
            time.sleep(milliseconds / 1000)

    def _timeout(self, step: Step, default_timeout: int) -> int:
        explicit = getattr(step, "timeout_ms", None)
        return int(explicit) if explicit else int(default_timeout)

    def _locate(self, step: Step, ctx: _ExecContext) -> ResolvedLocator:
        return self.resolve(
            str(step.element),
            elements=ctx.model.elements,
            policy=ctx.policy,
            page_id=ctx.model.id,
        )

    def _value(self, step: Step, raw: Any, ctx: _ExecContext) -> Any:
        return resolve_value(raw, ctx.values(), where=f"{step.op}({step.describe()})")

    def _dispatch_once(  # noqa: C901 - 声明式 op 的集中分派，扁平比拆散更好读
        self, step: Step, *, ctx: _ExecContext, default_timeout: int
    ) -> ResolvedLocator | None:
        api = _import_playwright()
        expect = api.expect
        timeout = self._timeout(step, default_timeout)

        # ---- 导航 ----
        if isinstance(step, Goto):
            raw_path = step.path if step.path is not None else ctx.model.url_path
            path = self._value(step, raw_path, ctx)
            url = f"{self.base_url}{path}"
            self.page.goto(url, timeout=timeout)
            log_ui_action("goto", target=url, page_id=ctx.model.id)
            return None
        if isinstance(step, GoBack):
            self.page.go_back(timeout=timeout)
            log_ui_action("go_back", target=self._safe(lambda: str(self.page.url)))
            return None
        if isinstance(step, Reload):
            self.page.reload(timeout=timeout)
            log_ui_action("reload", target=self._safe(lambda: str(self.page.url)))
            return None

        # ---- 交互 ----
        if isinstance(step, Fill):
            resolved = self._locate(step, ctx)
            value = self._value(step, step.value, ctx)
            resolved.locator.fill("" if value is None else str(value), timeout=timeout)
            log_ui_action(
                "fill",
                target=step.element,
                page_id=ctx.model.id,
                value=_MASK if step.is_secret() else value,
            )
            return resolved
        if isinstance(step, Click):
            resolved = self._locate(step, ctx)
            resolved.locator.click(timeout=timeout)
            log_ui_action("click", target=step.element, page_id=ctx.model.id)
            return resolved
        if isinstance(step, Hover):
            resolved = self._locate(step, ctx)
            resolved.locator.hover(timeout=timeout)
            log_ui_action("hover", target=step.element, page_id=ctx.model.id)
            return resolved
        if isinstance(step, Check):
            resolved = self._locate(step, ctx)
            if step.checked:
                resolved.locator.check(timeout=timeout)
            else:
                resolved.locator.uncheck(timeout=timeout)
            log_ui_action("check", target=step.element, checked=step.checked)
            return resolved
        if isinstance(step, Select):
            resolved = self._locate(step, ctx)
            option = self._value(step, step.option, ctx)
            kwargs = {step.by if step.by != "index" else "index": option}
            resolved.locator.select_option(timeout=timeout, **kwargs)
            log_ui_action("select", target=step.element, by=step.by, option=option)
            return resolved
        if isinstance(step, Press):
            resolved = self._locate(step, ctx)
            resolved.locator.press(step.key, timeout=timeout)
            log_ui_action("press", target=step.element, key=step.key)
            return resolved
        if isinstance(step, Upload):
            resolved = self._locate(step, ctx)
            path = self._value(step, step.file, ctx)
            resolved.locator.set_input_files(str(path), timeout=timeout)
            log_ui_action("upload", target=step.element, file=str(path))
            return resolved

        # ---- 等待 ----
        if isinstance(step, WaitForElement):
            resolved = self._locate(step, ctx)
            if step.state in ("enabled", "disabled"):
                checker = (
                    expect(resolved.locator).to_be_enabled
                    if step.state == "enabled"
                    else expect(resolved.locator).to_be_disabled
                )
                checker(timeout=timeout)
            else:
                resolved.locator.wait_for(state=step.state, timeout=timeout)
            log_ui_action("wait_for_element", target=step.element, state=step.state)
            return resolved
        if isinstance(step, WaitForUrl):
            pattern = self._value(step, step.pattern, ctx)
            self.page.wait_for_url(_as_url_pattern(str(pattern)), timeout=timeout)
            log_ui_action("wait_for_url", target=str(pattern))
            return None
        if isinstance(step, WaitForResponse):
            needle = str(self._value(step, step.path_contains, ctx))
            deadline = time.monotonic() + timeout / 1000
            while True:
                if any(
                    needle in url and status == step.status for url, status in self._responses
                ):
                    log_ui_action("wait_for_response", target=needle, status=step.status)
                    return None
                if time.monotonic() >= deadline:
                    raise StepExecutionError(
                        f"等待响应超时: path 含 {needle!r} 且 status={step.status}"
                        f"（{timeout}ms 内未出现）"
                    )
                self._pause(50)

        # ---- 提取 ----
        if isinstance(step, ExtractText):
            resolved = self._locate(step, ctx)
            text = resolved.locator.inner_text(timeout=timeout)
            ctx.extracted[step.variable] = text
            log_ui_action("extract_text", target=step.element, variable=step.variable)
            return resolved
        if isinstance(step, ExtractAttribute):
            resolved = self._locate(step, ctx)
            value = resolved.locator.get_attribute(step.attribute, timeout=timeout)
            ctx.extracted[step.variable] = value
            log_ui_action(
                "extract_attribute",
                target=step.element,
                attribute=step.attribute,
                variable=step.variable,
            )
            return resolved
        if isinstance(step, ExtractCount):
            resolved = self._locate(step, ctx)
            count = int(resolved.locator.count())
            ctx.extracted[step.variable] = count
            log_ui_action("extract_count", target=step.element, count=count)
            return resolved

        # ---- 断言 ----
        if isinstance(step, AssertVisible):
            resolved = self._locate(step, ctx)
            self._assert(
                lambda: expect(resolved.locator).to_be_visible(timeout=timeout),
                claim=f"{step.element} 可见",
                expected="visible",
            )
            return resolved
        if isinstance(step, AssertHidden):
            try:
                resolved = self._locate(step, ctx)
            except ElementNotFoundError:
                # 元素根本不存在，也满足「隐藏」语义
                log_assertion(
                    f"{step.element} 隐藏", expected="hidden", actual="absent", passed=True
                )
                return None
            self._assert(
                lambda: expect(resolved.locator).to_be_hidden(timeout=timeout),
                claim=f"{step.element} 隐藏",
                expected="hidden",
            )
            return resolved
        if isinstance(step, AssertText):
            resolved = self._locate(step, ctx)
            expected = self._value(step, step.expected, ctx)
            assertion = expect(resolved.locator)
            checks = {
                "eq": lambda: assertion.to_have_text(str(expected), timeout=timeout),
                "contains": lambda: assertion.to_contain_text(str(expected), timeout=timeout),
                "not_contains": lambda: assertion.not_to_contain_text(
                    str(expected), timeout=timeout
                ),
                "matches": lambda: assertion.to_have_text(
                    re.compile(str(expected)), timeout=timeout
                ),
            }
            self._assert(
                checks[step.operator],
                claim=f"{step.element} 文本 {step.operator}",
                expected=expected,
                actual_getter=lambda: self._safe(
                    lambda: resolved.locator.inner_text(timeout=1000)
                ),
            )
            return resolved
        if isinstance(step, AssertUrl):
            pattern = str(self._value(step, step.pattern, ctx))
            self._assert(
                lambda: expect(self.page).to_have_url(
                    _as_url_pattern(pattern), timeout=timeout
                ),
                claim="URL 匹配",
                expected=pattern,
                actual_getter=lambda: self._safe(lambda: str(self.page.url)),
            )
            return None
        if isinstance(step, AssertCount):
            resolved = self._locate(step, ctx)
            expected = int(self._value(step, step.expected, ctx))
            if step.operator == "eq":
                self._assert(
                    lambda: expect(resolved.locator).to_have_count(expected, timeout=timeout),
                    claim=f"{step.element} 数量 eq",
                    expected=expected,
                    actual_getter=lambda: str(resolved.locator.count()),
                )
                return resolved
            actual = int(resolved.locator.count())
            comparators = {
                "gt": actual > expected,
                "gte": actual >= expected,
                "lt": actual < expected,
                "lte": actual <= expected,
            }
            passed = comparators[step.operator]
            log_assertion(
                f"{step.element} 数量 {step.operator}",
                expected=expected,
                actual=actual,
                passed=passed,
            )
            if not passed:
                raise PageAssertError(
                    f"{step.element} 数量断言失败: {actual} {step.operator} {expected} 不成立"
                )
            return resolved

        # ---- 组合 ----
        if isinstance(step, RunFlow):
            if ctx.depth + 1 > _MAX_FLOW_DEPTH:
                raise StepExecutionError(
                    f"flow 嵌套超过 {_MAX_FLOW_DEPTH} 层，疑似成环: {step.flow}"
                )
            child = ctx.model.flows.get(step.flow)
            if child is None:
                raise StepExecutionError(
                    f"flow {step.flow!r} 不存在；可用: {sorted(ctx.model.flows)}"
                )
            nested = _ExecContext(
                model=ctx.model,
                policy=ctx.policy,
                params=ctx.values(),
                extracted=ctx.extracted,
                outcomes=ctx.outcomes,
                depth=ctx.depth + 1,
            )
            self._run_steps(child.steps, ctx=nested, default_timeout=default_timeout)
            return None
        if isinstance(step, Screenshot):
            self.screenshot(f"{ctx.model.id}_{step.name}")
            return None

        raise StepExecutionError(f"不支持的 step: {step.op}")

    def _assert(
        self,
        check: Callable[[], None],
        *,
        claim: str,
        expected: Any,
        actual_getter: Callable[[], Any] | None = None,
    ) -> None:
        try:
            check()
        except AssertionError as exc:
            actual = actual_getter() if actual_getter else "<not visible>"
            log_assertion(claim, expected=expected, actual=actual, passed=False)
            raise PageAssertError(f"{claim} 失败: expected={expected!r} actual={actual!r}") from exc
        log_assertion(claim, expected=expected, actual=expected, passed=True)


__all__ = ["PageDriver"]
