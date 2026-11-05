"""Per-scenario file handlers (opt-in).

When ``TEST_LOG_PER_SCENARIO=1`` is set, the hooks module attaches a fresh
``FileHandler`` to the shared logger at the start of each scenario and
detaches it at the end. The result is a dedicated ``logs/scenarios/...`` log
per scenario, convenient for forwarding a single failing test to whoever owns
the bug without sharing the whole run's noise.

The handler is installed alongside the main run-scope handler, so every
record still reaches both destinations. All lifecycle is owned by
``hooks.py``; consumers do not call into this module directly.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .core import (
    _make_file_handler,  # type: ignore[attr-defined]
    get_logger,
    log_dir,
    log_level,
    run_started_at,
)
from .context import ContextFilter

_SLUG_UNSAFE = re.compile(r"[\\/:*?\"<>|\s]+")
_MAX_SLUG = 60


def _slugify(text: str) -> str:
    s = _SLUG_UNSAFE.sub("_", (text or "").strip()).strip("_")
    if len(s) > _MAX_SLUG:
        s = s[:_MAX_SLUG].rstrip("_")
    return s or "unnamed"


def scenario_log_path(feature_name: str, scenario_name: str) -> Path:
    """Return the per-scenario log path; the parent folder is created lazily."""
    folder = log_dir() / "scenarios"
    folder.mkdir(parents=True, exist_ok=True)
    ts = run_started_at().strftime("%Y%m%d-%H%M%S")
    fname = f"{ts}__{_slugify(feature_name)}__{_slugify(scenario_name)}.log"
    return folder / fname


class _ScenarioHandlerRegistry:
    """Tracks the handler attached to the shared logger for the current scenario."""

    def __init__(self) -> None:
        self._handler: logging.FileHandler | None = None
        self._path: Path | None = None

    def attach(self, feature_name: str, scenario_name: str) -> Path:
        self.detach()  # defensive: close any stale handler first
        path = scenario_log_path(feature_name, scenario_name)
        handler = _make_file_handler(path, log_level())
        handler.addFilter(ContextFilter())
        get_logger().addHandler(handler)
        self._handler = handler
        self._path = path
        return path

    def detach(self) -> None:
        if self._handler is None:
            return
        logger = get_logger()
        try:
            self._handler.flush()
        except Exception:  # noqa: BLE001 -- best-effort flush before detaching
            pass
        logger.removeHandler(self._handler)
        try:
            self._handler.close()
        except Exception:  # noqa: BLE001 -- best-effort close before detaching
            pass
        self._handler = None
        self._path = None

    def active_path(self) -> Path | None:
        return self._path


_registry = _ScenarioHandlerRegistry()


def begin_scenario_file(feature_name: str, scenario_name: str) -> Path:
    return _registry.attach(feature_name, scenario_name)


def end_scenario_file() -> None:
    _registry.detach()


def current_scenario_path() -> Path | None:
    return _registry.active_path()
