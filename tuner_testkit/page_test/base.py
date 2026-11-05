"""BasePage —— 受控的逃生舱（escape hatch）。

声明式 step 序列是线性的，没有 ``if`` / ``for`` / ``try``；而 UI 自动化必然撞上
翻页找行、条件性关引导弹窗、轮询等状态流转、跨页编排这些场景。往 step DSL 里加
``If`` / ``Loop`` 等于用 dataclass 发明一门半成品编程语言，硬用线性 step 拼出来的
东西又必然脆。

所以承认「少数复杂交互直接用 Python 写」，但**约束逃生的方式**：必须继承本类、
必须经 :meth:`el` 访问元素、必须有类元数据与 ``Params``。**逃掉的只有动作序列的
声明式表达，元素层一点没逃** —— 定位器仍在 ``elements`` 声明表里，因此手写页面
照样享受多定位器 fallback、照样被平台可视化元素表、照样被 doctor 体检。

不给逃生舱的后果更糟：工程师撞上复杂场景又没有官方出口，就会绕过整个 page_test
直接在 steps 里写裸 locator，定位器于是散落到 ``tests/`` 里去。

**import 安全**：类定义期只自动登记、不抛错（否则一个不合规的页面会拖垮整个
registry 扫描）。校验集中在 :meth:`validate`，由 ``python -m tuner_testkit.page_test
validate`` 与离线单测确定性执行。
"""
from __future__ import annotations

import inspect
from abc import ABC
from typing import Any, ClassVar, Mapping

from pydantic import BaseModel, ConfigDict

from .errors import ElementSpecError
from .locator import ElementSpec, LocatorPolicy, ResolvedLocator
from .model import PageFlow, PageModel, PageResult
from .steps import Step

#: page_id -> BasePage 子类，由 ``__init_subclass__`` 自动登记，供 registry 发现
PAGE_CLASSES: dict[str, type["BasePage"]] = {}


class BasePage(ABC):  # noqa: B024 -- base for hand-written pages; hooks are optional overrides
    """手写页面对象的基类。对齐 ``tuner_testkit.action_words.base.ActionWord`` 的
    「ClassVar 元数据 + 内嵌 pydantic ``Params`` + 平台化 ``describe()``」范式。"""

    # ---- 类元数据（平台目录 / registry 索引） ----
    page_id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    url_path: ClassVar[str] = "/"
    tags: ClassVar[tuple[str, ...]] = ()

    # ---- 契约：与 PageModel 共用同一份声明 ----
    elements: ClassVar[Mapping[str, ElementSpec]] = {}
    inputs_schema: ClassVar[Mapping[str, Any]] = {}
    #: 可选的声明式 flow；复杂逻辑写 Python 方法即可，二者共存
    flows: ClassVar[Mapping[str, PageFlow]] = {}
    ready: ClassVar[tuple[Step, ...]] = ()
    asserts: ClassVar[tuple[Step, ...]] = ()
    extracts: ClassVar[tuple[Step, ...]] = ()
    locator_policy: ClassVar[Mapping[str, Any]] = {}
    auth_policy: ClassVar[Mapping[str, Any]] = {}
    #: 可直接运行的入参样例（CLI ``--example``）
    example_params: ClassVar[dict[str, Any]] = {}

    class Params(BaseModel):
        """入参契约；子类内嵌覆盖。未知键一律拒绝，避免拼写错误静默生效。"""

        model_config = ConfigDict(extra="forbid")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        page_id = cls.__dict__.get("page_id") or getattr(cls, "page_id", "")
        if page_id:
            PAGE_CLASSES[str(page_id)] = cls

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    # -- 运行时 ---------------------------------------------------------

    @property
    def driver(self) -> Any:
        """执行引擎。需要裸 Playwright API 时走 ``self.driver.raw_page``（刺眼命名，便于 review）。"""
        return self._driver

    @classmethod
    def policy(cls) -> LocatorPolicy:
        return LocatorPolicy.from_mapping(cls.locator_policy)

    def el(self, name: str) -> ResolvedLocator:
        """**唯一**的元素访问入口：走多定位器顺序探测，命中备用候选会留痕。"""
        return self._driver.resolve(
            name,
            elements=dict(type(self).elements),
            policy=type(self).policy(),
            page_id=type(self).page_id,
        )

    def goto(self, path: str | None = None) -> None:
        """导航到本页（或本页下的子路径）。host 由 driver 注入。"""
        target = path if path is not None else type(self).url_path
        self._driver.page.goto(f"{self._driver.base_url}{target}")

    def open(self, **inputs: Any) -> PageResult:
        """走声明式路径打开页面：Goto + ready + extracts + asserts。"""
        model = type(self).as_model()
        return model.set_inputs(inputs).open(driver=self._driver)

    def run(self, flow: str, **params: Any) -> PageResult:
        """执行一个**声明式** flow。Python 自定义动作直接当普通方法调用。"""
        model = type(self).as_model()
        return model.run(flow, params=params, driver=self._driver)

    def call(self, action: str, **kwargs: Any) -> Any:
        """按名字调用本页的 Python 自定义动作，给平台/CLI 一个统一入口。"""
        if action.startswith("_") or action in _BASE_MEMBERS:
            raise ElementSpecError(f"{action!r} 不是本页公开的自定义动作")
        method = getattr(self, action, None)
        if not callable(method):
            raise ElementSpecError(f"{action!r} 不是可调用的自定义动作")
        return method(**kwargs)

    # -- 平台化导出 -----------------------------------------------------

    @classmethod
    def as_model(cls) -> PageModel:
        """导出为 ``PageModel``，让 CLI / 平台 / doctor 用同一套代码处理两种范式。"""
        return PageModel(
            id=cls.page_id,
            name=cls.name,
            description=(cls.__doc__ or "").strip(),
            url_path=cls.url_path,
            elements=dict(cls.elements),
            inputs_schema=dict(cls.inputs_schema),
            flows=dict(cls.flows),
            ready=tuple(cls.ready),
            locator_policy=dict(cls.locator_policy),
            auth_policy=dict(cls.auth_policy),
            asserts=tuple(cls.asserts),
            extracts=tuple(cls.extracts),
        )

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """入参 JSON Schema（供平台渲染表单）。"""
        return cls.Params.model_json_schema()

    @classmethod
    def python_actions(cls) -> list[dict[str, Any]]:
        """反射出 Python 自定义动作，供平台在「流程」栏展示（而非步骤图）。"""
        out: list[dict[str, Any]] = []
        for attr in sorted(dir(cls)):
            if attr.startswith("_") or attr in _BASE_MEMBERS:
                continue
            member = inspect.getattr_static(cls, attr, None)
            if isinstance(member, (staticmethod, classmethod)):
                member = member.__func__
            if not inspect.isfunction(member):
                continue
            try:
                signature = str(inspect.signature(member)).replace("(self, ", "(").replace(
                    "(self)", "()"
                )
            except (TypeError, ValueError):  # pragma: no cover
                signature = "(...)"
            out.append(
                {
                    "name": attr,
                    "kind": "assert" if attr.startswith("assert_") else "action",
                    "signature": signature,
                    "doc": (member.__doc__ or "").strip(),
                }
            )
        return out

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """目录条目：元素表 + 声明式 flow + Python 自定义动作 + 入参 schema。"""
        payload = cls.as_model().describe()
        payload.update(
            {
                "kind": "page_class",
                "class": cls.__name__,
                "module": cls.__module__,
                "tags": list(cls.tags),
                "python_actions": cls.python_actions(),
                "params_schema": cls.params_schema(),
                "example_params": dict(cls.example_params),
            }
        )
        return payload

    @classmethod
    def validate(cls) -> list[str]:
        """返回问题清单（空表示通过）。包含 ``PageModel`` 全量校验 + 类模板要求。"""
        problems = list(cls.as_model().validate())
        if not (cls.__doc__ or "").strip():
            problems.append(f"{cls.__name__} 缺少业务 docstring（描述页面用途与前置条件）")
        if not cls.elements:
            problems.append(f"{cls.__name__} 没有声明任何元素")
        if cls.example_params:
            try:
                cls.Params.model_validate(dict(cls.example_params))
            except Exception as exc:  # noqa: BLE001 - pydantic 校验错误原样报出
                problems.append(f"{cls.__name__}.example_params 不满足 Params: {exc}")
        return problems


#: BasePage 自身的公开成员，用于反射时剔除框架方法、只留业务自定义动作
_BASE_MEMBERS = frozenset(name for name in dir(BasePage) if not name.startswith("_"))


__all__ = ["BasePage", "PAGE_CLASSES"]
