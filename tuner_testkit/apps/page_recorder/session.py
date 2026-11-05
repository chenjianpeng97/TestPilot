"""Headed Playwright session: hook DOM events and live-freeze PageModel assets."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from tuner_testkit.logging import log_info, log_warn
from tuner_testkit.page_test.errors import DriverError
from tuner_testkit.page_test.steps import WaitForUrl

from .capture import Capture, build_capture, page_slug_from_path, url_path_from_url
from .freeze import PageObjectFreezer
from .inject import INIT_SCRIPT

BINDING_NAME = "pageRecorderCapture"


def resolve_start_url(url: str | None) -> str:
    """``--url`` 缺省用 ``get_ui_base_url()``；相对路径拼到该 host。"""
    raw = (url or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    from tuner_testkit.config import get_ui_base_url

    try:
        base = (get_ui_base_url() or "").rstrip("/")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"无法解析 UI base URL（设置 TEST_UI_BASE_URL / TEST_BASE_URL，或传绝对 --url）: {exc}"
        ) from exc
    if not base:
        raise SystemExit("需要 --url 或 TEST_UI_BASE_URL / TEST_BASE_URL")
    if not raw:
        return base
    if not raw.startswith("/"):
        raw = "/" + raw
    return base + raw


def _host_ok(page_url: str, include_host: str | None) -> bool:
    if not include_host:
        return True
    host = (urlsplit(page_url).netloc or "").lower()
    return include_host.lower() in host


class PageRecorderSession:
    """人工点填浏览 → harvest → live merge。不走 ``PageDriver.execute`` / ``resolve_element``。"""

    def __init__(
        self,
        *,
        app: str,
        flow: str,
        outputs_dir: Path,
        start_url: str,
        scan: bool = False,
        include_host: str | None = None,
        storage_state: Any = None,
        freeze_pages: bool = True,
        on_page_ready: Callable[[Any], None] | None = None,
    ) -> None:
        self.app = app
        self.flow = flow
        self.outputs_dir = outputs_dir
        self.start_url = start_url
        self.scan = scan
        self.include_host = (include_host or "").strip() or None
        self.storage_state = storage_state
        self.freeze_pages = freeze_pages
        self.on_page_ready = on_page_ready
        self.freezer = PageObjectFreezer(outputs_dir, app=app, flow=flow)
        self.current_url = start_url
        self.current_path = url_path_from_url(start_url)
        self._page: Any = None
        self._driver: Any = None
        self._scan_pending = False

    def _existing(self) -> dict:
        return self.freezer.current_elements(self.current_path)

    def _freeze_navigate(self, new_url: str) -> None:
        new_path = url_path_from_url(new_url)
        if new_path == self.current_path:
            self.current_url = new_url
            return
        if self.freeze_pages and self.current_path:
            nav = Capture(
                url_path=self.current_path,
                host=urlsplit(self.current_url).netloc.lower(),
                event="navigate",
                page_slug=page_slug_from_path(self.current_path),
                step=WaitForUrl(new_path),
            )
            self.freezer.freeze(nav)
        self.current_url = new_url
        self.current_path = new_path
        log_info("page_recorder page switch", url_path=new_path)
        if self.scan and self.freeze_pages:
            # 不在 expose_binding 回调里 page.evaluate，否则会和 JS 互相等待而死锁
            self._scan_pending = True

    def _on_binding(self, source: Any, payload: Any) -> None:
        """JS → Python。此回调内禁止任何 Playwright API（含 ``page.url``）。"""
        if not self.freeze_pages:
            return
        try:
            if not isinstance(payload, dict):
                return
            page_url = str(payload.get("url") or self.current_url)
            if not _host_ok(page_url, self.include_host):
                return
            kind = str(payload.get("kind") or "")
            if kind == "navigate":
                self._freeze_navigate(page_url)
                return
            if url_path_from_url(page_url) != self.current_path:
                self._freeze_navigate(page_url)
            existing = self._existing()
            capture = build_capture(
                payload,
                existing=existing,
                used_names=set(existing),
                url=page_url,
            )
            if capture is None:
                return
            self.freezer.freeze(capture)
        except Exception as exc:  # noqa: BLE001 — 回调里绝不能把浏览器打挂
            log_warn("page_recorder capture failed", error=str(exc))

    def run_scan(self, page: Any | None = None) -> int:
        target = page or self._page
        if target is None:
            return 0
        try:
            snapshots = target.evaluate(
                "() => window.__pageRecorderScan ? window.__pageRecorderScan() : []"
            )
        except Exception as exc:  # noqa: BLE001
            log_warn("page_recorder scan failed", error=str(exc))
            return 0
        count = 0
        existing = self._existing()
        used = set(existing)
        for snap in snapshots or []:
            if not isinstance(snap, dict):
                continue
            capture = build_capture(
                {"kind": "scan", "url": target.url, "snapshot": snap},
                existing=existing,
                used_names=used,
            )
            if capture is None:
                continue
            self.freezer.freeze(capture)
            if capture.element is not None:
                used.add(capture.element.name)
                existing = self._existing()
            count += 1
        if count:
            log_info("page_recorder scan", count=count, url_path=self.current_path)
        return count

    def _attach_hooks(self, page: Any) -> None:
        if self.freeze_pages:
            context = page.context
            context.expose_binding(BINDING_NAME, self._on_binding)
            context.add_init_script(INIT_SCRIPT)
            page.on("framenavigated", self._on_frame_navigated)
        if self.on_page_ready is not None:
            self.on_page_ready(page)

    def _on_frame_navigated(self, frame: Any) -> None:
        try:
            page = frame.page
            if frame != page.main_frame:
                return
            url = page.url
            if not url or url.startswith("about:"):
                return
            if not _host_ok(url, self.include_host):
                return
            if url_path_from_url(url) != self.current_path:
                self._freeze_navigate(url)
        except Exception as exc:  # noqa: BLE001
            log_warn("page_recorder navigate hook failed", error=str(exc))

    def _launch(self) -> Any:
        from tuner_testkit.page_test.driver import PageDriver

        parts = urlsplit(self.start_url)
        origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else self.start_url
        try:
            driver = PageDriver.launch(
                headless=False,
                base_url=origin,
                storage_state=self.storage_state,
            )
        except DriverError:
            raise
        driver.persist_health = False
        return driver

    def run(self) -> int:
        """阻塞直到浏览器关闭或 Ctrl+C。返回冻结条数。"""
        driver = self._launch()
        self._driver = driver
        page = driver.page
        self._page = page
        try:
            self._attach_hooks(page)
            log_info(
                "page_recorder started",
                url=self.start_url,
                outputs=str(self.outputs_dir),
                app=self.app,
                flow=self.flow,
            )
            page.goto(self.start_url, wait_until="domcontentloaded")
            self.current_url = page.url
            self.current_path = url_path_from_url(page.url)
            if self.scan and self.freeze_pages:
                # init script 在这次 goto 已注入
                self.run_scan(page)
            self._wait_until_done(page)
        finally:
            try:
                driver.close()
            except Exception:  # noqa: BLE001 -- cleanup must not mask the session result
                pass
        return len(self.freezer.results)

    def _wait_until_done(self, page: Any) -> None:
        try:
            while True:
                if page.is_closed():
                    return
                try:
                    url = page.url
                except Exception:  # noqa: BLE001 -- page closed or navigating; skip this tick
                    return
                if url and not url.startswith("about:") and _host_ok(url, self.include_host):
                    if url_path_from_url(url) != self.current_path:
                        self._freeze_navigate(url)
                if self._scan_pending:
                    self._scan_pending = False
                    self.run_scan(page)
                time.sleep(0.4)
        except KeyboardInterrupt:
            log_info("page_recorder stopped (Ctrl+C)")
