"""定位器声明与多候选解析 —— page_test 的稳定性核心。

一个元素 = 一组**按优先级排序**的候选定位器。运行时按序探测，首个命中者胜出；
命中非首选时产出 :class:`LocatorEvent`，让「首选定位器已失效」成为可见信号，
而不是被静默吞掉后让资产慢慢腐烂。

:class:`LocatorPolicy` 把 ``docs/spec/page-objects-syntax.md`` 的 locator 硬约束
变成运行时可执行的校验，对齐 ``tuner_testkit.api_test`` 用 ``headers_policy``
拦截敏感请求头的做法：规范文字是概率性约束，policy 校验是确定性约束。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .errors import ElementNotFoundError, ElementSpecError, LocatorPolicyError

#: 支持的定位策略。前四项为语义定位，``test_id`` 为测试标识，其余为结构化兜底。
STRATEGIES = (
    "role",
    "label",
    "placeholder",
    "title",
    "alt_text",
    "text",
    "test_id",
    "css",
    "xpath",
)

#: 稳定性等级。``fragile`` 候选必须写 ``note`` 说明风险与替代建议。
CONFIDENCES = ("stable", "fragile")

_CSS_COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")


def is_absolute_xpath(value: str) -> bool:
    """``/html/body/div[3]`` 为绝对路径；``//div[@id='x']`` / ``.//td`` 为相对。"""
    v = value.strip()
    if v.lower().startswith("xpath="):
        v = v[len("xpath="):].strip()
    if not v.startswith("/"):
        return False
    return not v.startswith("//")


def css_depth(value: str) -> int:
    """CSS 选择器的层级数（按后代/子代组合符切分），用于识别依赖 DOM 层级的超长选择器。"""
    parts = [p for p in _CSS_COMBINATOR_RE.split(value.strip()) if p]
    return len(parts)


@dataclass(frozen=True)
class LocatorPolicy:
    """定位器策略。挂在每个 ``PageModel`` 上，因此豁免是资产里一行可审计的声明。"""

    #: 绝对 XPath 硬禁：任何 DOM 微调都会断
    allow_absolute_xpath: bool = False
    #: 相对 XPath 允许，但强制降权为 fragile（CSS 做不到 text() 与轴向定位）
    allow_xpath: bool = True
    #: ``nth(i)`` 寻址：用位置代替业务标识，插一行数据就错位，默认禁
    allow_index: bool = False
    #: ``.first`` 消歧：消除 Playwright strict mode violation 的标准手段，默认允许
    allow_disambiguation: bool = True
    #: 每个元素至少要有几个 stable 候选
    min_stable_candidates: int = 1
    #: 首选候选是 fragile 时必须再给至少一个备用
    require_fallback_for_fragile: bool = True
    #: 依赖 DOM 层级的 CSS 选择器最大层级数
    max_css_depth: int = 4
    #: 单个候选的探测超时。**性能护栏**：Playwright 默认 30s，5 个候选全等满
    #: 就是单元素卡 150s，所以探测超时必须短，且与「等待条件成立」的超时分离。
    probe_timeout_ms: int = 1500
    #: 最多声明几个候选
    fallback_max_attempts: int = 4
    #: 探测时是否要求元素可见（而非仅挂载）
    require_visible: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | "LocatorPolicy" | None) -> "LocatorPolicy":
        if isinstance(data, LocatorPolicy):
            return data
        if not data:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        unknown = [str(k) for k in data if str(k) not in known]
        if unknown:
            raise LocatorPolicyError(f"locator_policy 含未知键: {sorted(unknown)}")
        return cls(**{str(k): v for k, v in data.items()})

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


DEFAULT_POLICY = LocatorPolicy()


@dataclass(frozen=True)
class LocatorSpec:
    """单个候选定位器的数据描述。可被 recorder 生成、被平台可视化。"""

    strategy: str
    value: str
    #: ``get_by_role(role, name=...)`` 的可访问名
    name: str | None = None
    exact: bool | None = None
    #: ``.filter(has_text=...)``
    has_text: str | None = None
    #: 索引寻址（policy.allow_index）
    nth: int | None = None
    #: 索引消歧（policy.allow_disambiguation）
    first: bool = False
    #: 父元素名：先缩小容器再定位，提升唯一性
    scope: str | None = None
    confidence: str = "stable"
    #: 来源与风险说明（MCP snapshot / recorder / 为何脆弱）
    note: str = ""

    def signature(self) -> str:
        """人类可读签名，用于 doctor 报告与异常信息。"""
        head = f"{self.strategy}={self.value!r}"
        if self.name is not None:
            head += f" name={self.name!r}"
        if self.exact is not None:
            head += f" exact={self.exact}"
        if self.has_text is not None:
            head += f" has_text={self.has_text!r}"
        if self.nth is not None:
            head += f".nth({self.nth})"
        elif self.first:
            head += ".first"
        if self.scope:
            head += f" @{self.scope}"
        return head

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"strategy": self.strategy, "value": self.value}
        for key in ("name", "exact", "has_text", "nth", "scope"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.first:
            out["first"] = True
        out["confidence"] = self.confidence
        if self.note:
            out["note"] = self.note
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LocatorSpec":
        known = {f for f in cls.__dataclass_fields__}
        unknown = [str(k) for k in data if str(k) not in known]
        if unknown:
            raise ElementSpecError(f"LocatorSpec 含未知键: {sorted(unknown)}")
        return cls(**{str(k): v for k, v in data.items()})


@dataclass(frozen=True)
class ElementSpec:
    """一个页面元素：业务名 + 按优先级排序的候选定位器。

    这是**唯一**允许出现定位器的地方；steps 与 flows 只按名字引用元素。
    """

    name: str
    description: str = ""
    #: ``locators[0]`` 为首选
    locators: tuple[LocatorSpec, ...] = ()
    required: bool = True
    #: 平台可视化提示：textbox / button / table / dialog ...
    role_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "role_hint": self.role_hint,
            "locators": [spec.to_dict() for spec in self.locators],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ElementSpec":
        payload = dict(data)
        locators = payload.pop("locators", []) or []
        known = {f for f in cls.__dataclass_fields__}
        unknown = [str(k) for k in payload if str(k) not in known]
        if unknown:
            raise ElementSpecError(f"ElementSpec 含未知键: {sorted(unknown)}")
        return cls(
            **{str(k): v for k, v in payload.items()},
            locators=tuple(LocatorSpec.from_dict(item) for item in locators),
        )


@dataclass(frozen=True)
class LocatorEvent:
    """一次元素解析的结果留痕，供 doctor 聚合出定位器健康度。

    全量记录（``primary`` 也记），因为 doctor 需要「候选 i 命中 n/m 次」这种比率；
    日志只在 ``fallback`` / ``missing`` 时打，避免噪音。
    """

    element: str
    #: "primary" | "fallback" | "missing"
    outcome: str
    page_id: str = ""
    used_index: int = -1
    used: str = ""
    preferred: str = ""
    candidates: tuple[str, ...] = ()
    confidence: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "outcome": self.outcome,
            "page_id": self.page_id,
            "used_index": self.used_index,
            "used": self.used,
            "preferred": self.preferred,
            "candidates": list(self.candidates),
            "confidence": self.confidence,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class ResolvedLocator:
    """解析结果。``locator`` 是 Playwright Locator，仅在 page object 内部使用。"""

    element: str
    locator: Any
    spec: LocatorSpec
    index: int
    #: 本次实际探测过的候选（顺序可能因 ``prefer_index`` 提示而不同于声明顺序）
    attempted: tuple[LocatorSpec, ...] = ()
    #: 声明里的首选候选，便于对比「本该用哪个 / 实际用了哪个」
    preferred: LocatorSpec | None = None

    @property
    def fallback_used(self) -> bool:
        return self.index > 0


# ---------------------------------------------------------------------------
# 静态校验（无需浏览器；CLI validate 与离线单测走这条）
# ---------------------------------------------------------------------------


def validate_locator(spec: LocatorSpec, *, policy: LocatorPolicy) -> None:
    """单个候选的 policy 校验。违规抛 :class:`LocatorPolicyError`。"""
    if spec.strategy not in STRATEGIES:
        raise ElementSpecError(
            f"未知 strategy {spec.strategy!r}，可用: {list(STRATEGIES)}"
        )
    if not str(spec.value).strip():
        raise ElementSpecError(f"strategy={spec.strategy} 的 value 不能为空")
    if spec.confidence not in CONFIDENCES:
        raise ElementSpecError(
            f"confidence 必须是 {list(CONFIDENCES)}，得到 {spec.confidence!r}"
        )
    if spec.confidence == "fragile" and not spec.note.strip():
        raise LocatorPolicyError(
            f"fragile 候选必须写 note 说明风险与替代建议: {spec.signature()}"
        )
    if spec.strategy == "role" and spec.name is None and not spec.has_text:
        raise LocatorPolicyError(
            f"role 定位需要 name 或 has_text 才足够唯一: {spec.signature()}"
        )

    if spec.strategy == "xpath":
        if is_absolute_xpath(spec.value):
            if not policy.allow_absolute_xpath:
                raise LocatorPolicyError(
                    f"绝对 XPath 被禁止（任何 DOM 微调都会断）: {spec.signature()}"
                )
        elif not policy.allow_xpath:
            raise LocatorPolicyError(f"XPath 被本页 policy 禁止: {spec.signature()}")
        if spec.confidence != "fragile":
            raise LocatorPolicyError(
                f"XPath 候选必须声明 confidence='fragile': {spec.signature()}"
            )

    if spec.strategy == "css":
        depth = css_depth(spec.value)
        if depth > policy.max_css_depth:
            raise LocatorPolicyError(
                f"CSS 选择器层级 {depth} 超过上限 {policy.max_css_depth}"
                f"（依赖 DOM 层级的超长选择器）: {spec.signature()}"
            )

    if spec.nth is not None:
        if not policy.allow_index:
            raise LocatorPolicyError(
                f"nth({spec.nth}) 是索引寻址（用位置代替业务标识），本页 policy 禁止；"
                f"若确需豁免请设 allow_index=True 并在 note 说明: {spec.signature()}"
            )
        if not spec.note.strip():
            raise LocatorPolicyError(
                f"索引寻址必须写 note 说明为何没有稳定标识: {spec.signature()}"
            )
    if spec.first and not policy.allow_disambiguation:
        raise LocatorPolicyError(
            f".first 消歧被本页 policy 禁止: {spec.signature()}"
        )
    if spec.nth is not None and spec.first:
        raise ElementSpecError(
            f"nth 与 first 不能同时使用: {spec.signature()}"
        )


def validate_element(
    element: ElementSpec,
    *,
    policy: LocatorPolicy = DEFAULT_POLICY,
    elements: Mapping[str, ElementSpec] | None = None,
) -> None:
    """单个元素的完整校验：候选数量、稳定性下限、fragile 备用、scope 引用。"""
    if not element.locators:
        raise ElementSpecError(f"元素 {element.name!r} 没有任何候选定位器")
    if len(element.locators) > policy.fallback_max_attempts:
        raise LocatorPolicyError(
            f"元素 {element.name!r} 声明了 {len(element.locators)} 个候选，"
            f"超过 fallback_max_attempts={policy.fallback_max_attempts}"
        )

    for spec in element.locators:
        validate_locator(spec, policy=policy)

    stable = sum(1 for spec in element.locators if spec.confidence == "stable")
    if stable < policy.min_stable_candidates:
        raise LocatorPolicyError(
            f"元素 {element.name!r} 只有 {stable} 个 stable 候选，"
            f"少于 min_stable_candidates={policy.min_stable_candidates}；"
            "建议请研发补 data-testid"
        )
    if (
        policy.require_fallback_for_fragile
        and element.locators[0].confidence == "fragile"
        and len(element.locators) < 2
    ):
        raise LocatorPolicyError(
            f"元素 {element.name!r} 首选候选是 fragile 却没有备用候选"
        )

    if elements is not None:
        _validate_scope_chain(element.name, elements=elements)


def _validate_scope_chain(name: str, *, elements: Mapping[str, ElementSpec]) -> None:
    """scope 引用必须存在，且不能自引用或成环。"""
    seen: list[str] = []
    cursor = name
    while True:
        if cursor in seen:
            raise ElementSpecError(f"scope 引用成环: {' -> '.join([*seen, cursor])}")
        seen.append(cursor)
        element = elements.get(cursor)
        if element is None:
            raise ElementSpecError(f"scope 引用了不存在的元素 {cursor!r}")
        parents = {spec.scope for spec in element.locators if spec.scope}
        if not parents:
            return
        if len(parents) > 1:
            for parent in sorted(parents):
                _validate_scope_chain(parent, elements=elements)
            return
        cursor = parents.pop()


def validate_elements(
    elements: Mapping[str, ElementSpec],
    *,
    policy: LocatorPolicy = DEFAULT_POLICY,
) -> list[str]:
    """全量校验元素表，返回问题清单（空列表表示通过）。"""
    problems: list[str] = []
    for key, element in elements.items():
        if key != element.name:
            problems.append(f"元素表键 {key!r} 与 ElementSpec.name {element.name!r} 不一致")
        try:
            validate_element(element, policy=policy, elements=elements)
        except (ElementSpecError, LocatorPolicyError) as exc:
            problems.append(f"[{key}] {exc}")
    return problems


# ---------------------------------------------------------------------------
# 运行时解析（需要 Playwright Locator / Page）
# ---------------------------------------------------------------------------


def build_locator(root: Any, spec: LocatorSpec, *, scope: Any = None) -> Any:
    """按候选声明构造 Playwright Locator。``root`` 是 Page，``scope`` 是父 Locator。"""
    target = root if scope is None else scope

    if spec.strategy == "role":
        kwargs: dict[str, Any] = {}
        if spec.name is not None:
            kwargs["name"] = spec.name
        if spec.exact is not None:
            kwargs["exact"] = spec.exact
        locator = target.get_by_role(spec.value, **kwargs)
    elif spec.strategy == "test_id":
        locator = target.get_by_test_id(spec.value)
    elif spec.strategy in ("label", "placeholder", "title", "alt_text", "text"):
        getter = {
            "label": "get_by_label",
            "placeholder": "get_by_placeholder",
            "title": "get_by_title",
            "alt_text": "get_by_alt_text",
            "text": "get_by_text",
        }[spec.strategy]
        kwargs = {} if spec.exact is None else {"exact": spec.exact}
        locator = getattr(target, getter)(spec.value, **kwargs)
    elif spec.strategy == "css":
        locator = target.locator(spec.value)
    elif spec.strategy == "xpath":
        selector = spec.value if spec.value.lower().startswith("xpath=") else f"xpath={spec.value}"
        locator = target.locator(selector)
    else:  # pragma: no cover - validate_locator 已拦截
        raise ElementSpecError(f"未知 strategy {spec.strategy!r}")

    if spec.has_text is not None:
        locator = locator.filter(has_text=spec.has_text)
    if spec.nth is not None:
        locator = locator.nth(spec.nth)
    elif spec.first:
        locator = locator.first
    return locator


def probe_locator(locator: Any, *, policy: LocatorPolicy) -> bool:
    """短超时探测候选是否存在。

    用 ``wait_for`` 而非 ``count()``：后者是即时判断，页面还在渲染时会误判失败。
    统一取 ``.first`` 是为了让探测阶段不触发 strict mode violation —— 这一步只
    关心「有没有」，唯一性由候选声明自己负责。
    """
    state = "visible" if policy.require_visible else "attached"
    try:
        locator.first.wait_for(state=state, timeout=policy.probe_timeout_ms)
    except Exception:  # noqa: BLE001 -- any probe failure means this candidate is unusable
        return False
    return True


def resolve_element(
    root: Any,
    element_name: str,
    *,
    elements: Mapping[str, ElementSpec],
    policy: LocatorPolicy = DEFAULT_POLICY,
    page_id: str = "",
    sink: Callable[[LocatorEvent], None] | None = None,
    prefer_index: int | None = None,
    _resolving: tuple[str, ...] = (),
) -> ResolvedLocator:
    """按优先级探测候选，返回首个命中者。

    命中非首选时通过 ``sink`` 产出 :class:`LocatorEvent`，让首选失效可见。
    全部候选未命中时抛 :class:`ElementNotFoundError`，异常信息列出所有尝试过的
    候选，便于直接定位问题。

    ``prefer_index`` 把上次命中的候选挪到探测队首。失效的首选每次都要等满
    ``probe_timeout_ms`` 才降级（实测约 1.5s，而命中只需毫秒级），同一元素在一个
    flow 里被引用多次就会累加这笔开销。仍然逐个**探测**、``used_index`` 仍是真实
    候选下标，所以既不影响正确性，也不影响 doctor 的统计。
    """
    element = elements.get(element_name)
    if element is None:
        raise ElementSpecError(
            f"未声明的元素 {element_name!r}；已声明: {sorted(elements)}"
        )
    if element_name in _resolving:
        raise ElementSpecError(
            f"scope 引用成环: {' -> '.join([*_resolving, element_name])}"
        )
    if not element.locators:
        raise ElementSpecError(f"元素 {element_name!r} 没有任何候选定位器")

    candidates = tuple(spec.signature() for spec in element.locators)
    preferred = candidates[0]
    started = time.monotonic()

    order = list(range(len(element.locators)))
    if prefer_index is not None and 0 <= prefer_index < len(order):
        order = [prefer_index, *(i for i in order if i != prefer_index)]

    attempted: list[LocatorSpec] = []
    for index in order:
        spec = element.locators[index]
        attempted.append(spec)
        validate_locator(spec, policy=policy)

        scope_locator = None
        if spec.scope:
            scope_locator = resolve_element(
                root,
                spec.scope,
                elements=elements,
                policy=policy,
                page_id=page_id,
                sink=sink,
                _resolving=(*_resolving, element_name),
            ).locator

        locator = build_locator(root, spec, scope=scope_locator)
        if not probe_locator(locator, policy=policy):
            continue

        if sink is not None:
            sink(
                LocatorEvent(
                    element=element_name,
                    outcome="primary" if index == 0 else "fallback",
                    page_id=page_id,
                    used_index=index,
                    used=spec.signature(),
                    preferred=preferred,
                    candidates=candidates,
                    confidence=spec.confidence,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
            )
        return ResolvedLocator(
            element=element_name,
            locator=locator,
            spec=spec,
            index=index,
            attempted=tuple(attempted),
            preferred=element.locators[0],
        )

    if sink is not None:
        sink(
            LocatorEvent(
                element=element_name,
                outcome="missing",
                page_id=page_id,
                used_index=-1,
                preferred=preferred,
                candidates=candidates,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        )
    tried = "\n".join(f"  [{i}] {candidates[i]}" for i in order)
    raise ElementNotFoundError(
        f"元素 {element_name!r} 的全部 {len(candidates)} 个候选定位器均未命中"
        f"（每个探测超时 {policy.probe_timeout_ms}ms）：\n{tried}"
    )


__all__ = [
    "STRATEGIES",
    "CONFIDENCES",
    "DEFAULT_POLICY",
    "LocatorPolicy",
    "LocatorSpec",
    "ElementSpec",
    "LocatorEvent",
    "ResolvedLocator",
    "is_absolute_xpath",
    "css_depth",
    "validate_locator",
    "validate_element",
    "validate_elements",
    "build_locator",
    "probe_locator",
    "resolve_element",
]
