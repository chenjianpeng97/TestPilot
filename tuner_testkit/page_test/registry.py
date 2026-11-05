"""页面资产发现与目录导出 —— 对齐 ``tuner_testkit.action_words.registry``。

扫描 ``packages/page_objects/**``，同时收集两种范式：模块级 :class:`PageModel`
实例（声明式资产，page recorder 的生成目标）与 :class:`BasePage` 子类（逃生舱）。
两者用 :class:`PageAsset` 统一封装，因此 CLI、平台与 doctor 只需处理一种接口。

扫描**容错**：单个模块 import 失败只记录问题、不中断整体发现，与
``tuner_testkit.catalog`` 跳过坏模块的行为一致。
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .base import PAGE_CLASSES, BasePage
from .errors import PageTestError
from .model import PageModel

#: page_objects 下的辅助模块，不含页面资产
_SKIP_STEMS = frozenset({"__init__", "session", "pages"})

_REGISTRY: dict[str, "PageAsset"] = {}
_IMPORT_PROBLEMS: list[str] = []
_discovered = False


@dataclass(frozen=True)
class PageAsset:
    """统一封装：声明式 ``PageModel`` 与 ``BasePage`` 子类对外长一样。"""

    page_id: str
    kind: str
    module: str
    model: PageModel
    page_class: type[BasePage] | None = None
    #: 声明式资产的模块级变量名（供 recorder 定位并合并）
    variable: str = ""

    def describe(self) -> dict[str, Any]:
        if self.page_class is not None:
            return self.page_class.describe()
        payload = self.model.describe()
        payload.update({"module": self.module, "variable": self.variable})
        return payload

    def validate(self) -> list[str]:
        if self.page_class is not None:
            return self.page_class.validate()
        return self.model.validate()

    def bind(self, driver: Any) -> Any:
        """返回可直接操作的对象：类范式给实例，声明式给绑定了 driver 的 model。"""
        if self.page_class is not None:
            return self.page_class(driver)
        return self.model.bind(driver)


def page_objects_root() -> Path:
    from tuner_testkit.project import page_objects_dir

    return page_objects_dir()


#: 资产模块必须位于此包下；其它模块里的 BasePage 子类（测试夹具、临时试验）不入目录
ASSET_PACKAGE = "packages.page_objects"


def _module_name_for(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return ".".join([ASSET_PACKAGE, *relative.with_suffix("").parts])


def _import_module(path: Path, root: Path) -> Any:
    module_name = _module_name_for(path, root)
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        # 中间目录缺 __init__.py 时按文件路径直接加载
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _register_from_module(module: Any) -> None:
    for variable, value in vars(module).items():
        if variable.startswith("_"):
            continue
        if isinstance(value, PageModel):
            _put(
                PageAsset(
                    page_id=value.id,
                    kind="page_model",
                    module=getattr(module, "__name__", ""),
                    model=value,
                    variable=variable,
                )
            )


def _put(asset: PageAsset) -> None:
    existing = _REGISTRY.get(asset.page_id)
    if existing is not None and (existing.module, existing.variable) != (
        asset.module,
        asset.variable,
    ):
        _IMPORT_PROBLEMS.append(
            f"page_id 重复: {asset.page_id!r} 同时出现在 {existing.module} 与 {asset.module}"
        )
        return
    _REGISTRY[asset.page_id] = asset


def discover(*, force: bool = False) -> list[str]:
    """导入 page_objects 下全部资产模块。幂等；返回 import 期问题清单。"""
    global _discovered
    if _discovered and not force:
        return list(_IMPORT_PROBLEMS)
    _discovered = True
    _REGISTRY.clear()
    _IMPORT_PROBLEMS.clear()

    from tuner_testkit.project import ensure_project_on_path

    ensure_project_on_path()
    root = page_objects_root()
    if not root.is_dir():
        return []

    scanned: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if path.stem in _SKIP_STEMS or "__pycache__" in path.parts:
            continue
        try:
            module = _import_module(path, root)
        except Exception as exc:  # noqa: BLE001 - 坏模块不应拖垮整体扫描
            _IMPORT_PROBLEMS.append(
                f"import 失败 {path.relative_to(root)}: {type(exc).__name__}: {exc}"
            )
            continue
        scanned.add(str(getattr(module, "__name__", "")))
        _register_from_module(module)

    # BasePage 子类由 __init_subclass__ 在 import 期自动登记，但 PAGE_CLASSES 是
    # 进程级的：单测夹具、临时试验、以及已被删除的资产都可能残留在里面。只认
    # 本次扫描真正 import 到的模块，目录才与磁盘状态一致。
    for page_id, page_class in PAGE_CLASSES.items():
        if not page_id or page_class.__module__ not in scanned:
            continue
        _put(
            PageAsset(
                page_id=page_id,
                kind="page_class",
                module=page_class.__module__,
                model=page_class.as_model(),
                page_class=page_class,
            )
        )

    return list(_IMPORT_PROBLEMS)


def list_all() -> list[PageAsset]:
    discover()
    return [_REGISTRY[key] for key in sorted(_REGISTRY)]


def get(page_id: str) -> PageAsset:
    discover()
    asset = _REGISTRY.get(page_id)
    if asset is None:
        raise PageTestError(
            f"未注册的页面资产 {page_id!r}；已注册: {sorted(_REGISTRY)}"
        )
    return asset


def iter_ids() -> Iterable[str]:
    discover()
    return sorted(_REGISTRY)


def import_problems() -> list[str]:
    discover()
    return list(_IMPORT_PROBLEMS)


def export_catalog() -> list[dict[str, Any]]:
    """全量目录（元素表 + 流程 + 策略 + 入参 schema），平台化数据源。"""
    return [asset.describe() for asset in list_all()]


def validate_all() -> dict[str, list[str]]:
    """全量静态校验，返回 ``page_id -> 问题清单``（只含有问题的条目）。"""
    problems: dict[str, list[str]] = {}
    leftovers = import_problems()
    if leftovers:
        problems["<import>"] = leftovers
    for asset in list_all():
        found = asset.validate()
        if found:
            problems[asset.page_id] = found
    return problems


def register(asset: PageAsset) -> PageAsset:
    """手工登记（测试与动态生成场景用）。"""
    _put(asset)
    return asset


def reset_registry_for_tests() -> None:
    global _discovered
    _REGISTRY.clear()
    _IMPORT_PROBLEMS.clear()
    _discovered = False


__all__ = [
    "ASSET_PACKAGE",
    "PageAsset",
    "discover",
    "export_catalog",
    "get",
    "import_problems",
    "iter_ids",
    "list_all",
    "page_objects_root",
    "register",
    "reset_registry_for_tests",
    "validate_all",
]
