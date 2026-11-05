"""Shared session + replay helpers for ``page_objects`` ``__main__`` blocks.

对标 ``tuner_testkit.api_objects.auth``：凭据集中一处管理，资产文件只引用本模块，
因此单个页面资产可以像单个 APIModel 资产那样**直接运行**::

    python packages/page_objects/<app>/<page_slug>.py

Never commit real credentials —— 全部从环境变量读。

Env vars:
  - ``TEST_UI_BASE_URL``  — UI host（缺省回落 ``TEST_BASE_URL``，见 ``tuner_testkit.config``）
  - ``TEST_USERNAME`` / ``TEST_PASSWORD`` — 填充资产里的 ``{{username}}`` / ``{{password}}``
  - ``PAGE_TEST_HEADED``  — 设为 1/true 时显示浏览器窗口（默认无头）
  - ``PAGE_TEST_SLOW_MO`` — 每步放慢毫秒数（调试用）

资产文件末尾的回放块模板见 :data:`MAIN_BLOCK_TEMPLATE`（page recorder 的 codegen 目标）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


def bootstrap_repo_path() -> Path:
    """Ensure the SUT repo root is on ``sys.path`` (never the kit install path)."""
    from tuner_testkit.project import ensure_project_on_path

    return ensure_project_on_path()


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _flag(name: str) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


def username() -> str:
    return _env("TEST_USERNAME")


def password() -> str:
    return _env("TEST_PASSWORD")


def ui_base_url() -> str:
    from tuner_testkit.config import get_ui_base_url

    return get_ui_base_url()


def get_ui_credentials() -> dict[str, str]:
    """返回 ``{"username": ..., "password": ...}``（仅包含已配置的项）。"""
    out: dict[str, str] = {}
    if username():
        out["username"] = username()
    if password():
        out["password"] = password()
    return out


def require_ui_credentials() -> dict[str, str]:
    creds = get_ui_credentials()
    if not creds.get("username") or not creds.get("password"):
        raise SystemExit(
            "缺少 UI 登录凭据：请设置 TEST_USERNAME 与 TEST_PASSWORD"
            "（以及可用的 TEST_UI_BASE_URL / TEST_BASE_URL）"
        )
    return creds


def launch_driver(*, headless: bool | None = None, **kwargs: Any) -> Any:
    """按环境变量决定 headed/slow_mo 启动 :class:`PageDriver`。"""
    from tuner_testkit.page_test.driver import PageDriver

    if headless is None:
        headless = not _flag("PAGE_TEST_HEADED")
    slow_mo = kwargs.pop("slow_mo", None)
    if slow_mo is None:
        raw = _env("PAGE_TEST_SLOW_MO")
        slow_mo = float(raw) if raw else 0
    return PageDriver.launch(headless=headless, slow_mo=slow_mo, **kwargs)


def as_page_model(asset: Any) -> Any:
    """接受 ``PageModel`` 实例或 ``BasePage`` 子类，统一取出 model。"""
    from tuner_testkit.page_test.base import BasePage
    from tuner_testkit.page_test.model import PageModel

    if isinstance(asset, PageModel):
        return asset
    if isinstance(asset, type) and issubclass(asset, BasePage):
        return asset.as_model()
    raise TypeError(f"不支持的资产类型: {type(asset).__name__}")


def replay_flow(
    asset: Any,
    *,
    flow: str | None = None,
    params: Mapping[str, Any] | None = None,
    open_first: bool = True,
    headless: bool | None = None,
    with_credentials: bool = True,
    timeout_ms: int | None = None,
) -> Any:
    """打开页面并（可选）执行一个声明式 flow，返回 :class:`PageResult`。

    环境变量里的凭据会作为默认入参注入，因此资产源码里只写
    ``{{username}}`` / ``{{password}}`` 占位符即可。
    """
    model = as_page_model(asset)
    merged: dict[str, Any] = {}
    if with_credentials:
        merged.update(get_ui_credentials())
    merged.update(dict(params or {}))

    with launch_driver(headless=headless) as driver:
        invocation = model.set_inputs(merged)
        result = (
            invocation.open(driver=driver, timeout_ms=timeout_ms) if open_first else None
        )
        if flow:
            result = invocation.run(flow, driver=driver, timeout_ms=timeout_ms)
    if result is None:
        raise ValueError("open_first=False 时必须提供 flow")
    return result


def report(result: Any) -> None:
    """打印一行回放结论 + 定位器降级提醒（供 ``__main__`` 块用）。"""
    from tuner_testkit.logging import log_info, log_warn

    log_info(
        "page_replay",
        page_id=result.page_id,
        flow=result.flow,
        ok=result.ok,
        url=result.url,
        steps=len(result.steps),
    )
    if result.fallbacks:
        log_warn(
            "page_replay_locator_fallback",
            page_id=result.page_id,
            count=len(result.fallbacks),
            hint=f"python -m tuner_testkit.page_test doctor {result.page_id}",
        )
    print(
        "OK" if result.ok else "FAILED",
        result.page_id,
        result.flow,
        "->",
        result.url,
    )


#: 页面资产文件末尾的回放块模板；``{variable}`` / ``{flow}`` 由 page recorder 填充。
MAIN_BLOCK_TEMPLATE = '''
if __name__ == "__main__":
    # 单文件回放：凭据见 tuner_testkit.page_test.session（从环境变量读，不落盘）。
    import sys
    from pathlib import Path

    for _root in Path(__file__).resolve().parents:
        if (_root / "pyproject.toml").is_file() and (_root / "packages").is_dir():
            if str(_root) not in sys.path:
                sys.path.insert(0, str(_root))
            break

    from tuner_testkit.page_test.session import replay_flow, report

    report(replay_flow({variable}, flow={flow!r}))
'''


__all__ = [
    "MAIN_BLOCK_TEMPLATE",
    "as_page_model",
    "bootstrap_repo_path",
    "get_ui_credentials",
    "launch_driver",
    "password",
    "replay_flow",
    "report",
    "require_ui_credentials",
    "ui_base_url",
    "username",
]
