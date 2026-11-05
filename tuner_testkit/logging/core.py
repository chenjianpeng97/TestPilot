"""Core logger construction for the portable logging kit.

Responsibilities:
- Build a single, run-scoped logger detached from the stdlib ``root`` logger
  (so behave's ``--logcapture`` / third-party loggers never interfere).
- Resolve the output directory (default ``logs``) and the main log-file path
  (one file per process / one file per run).
- Provide the public accessors used by the rest of the package
  (``get_logger`` / ``get_log_file_path``).

This module is intentionally free of any ``behave`` / ``playwright`` /
``requests`` imports so the package is drop-in portable into other projects
and CLI tools (pytest, dump scripts, etc.).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

_LOGGER_NAME = "packages.logging"
_DEFAULT_FMT = (
    "%(asctime)s.%(msecs)03d %(levelname)-5s "
    "[%(log_stage)-3s] [%(log_scope)s] [%(log_kind)-7s] %(message)s"
)
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

_logger: logging.Logger | None = None
_log_file_path: Path | None = None
_run_started_at: datetime | None = None


# ---------------------------------------------------------------------------
# Environment-driven configuration helpers
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def log_dir() -> Path:
    """Return the resolved output directory (created on demand)."""
    override = _env("TEST_LOG_DIR", "logs")
    d = Path(override).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_name_stem() -> str:
    """Return the main-log filename stem.

    Preference order:
    1. ``TEST_LOG_NAME`` env override
    2. entry-point script stem (``behave``, ``dump_ddl``, ``pytest``, ...)
    3. ``"run"`` fallback
    """
    override = _env("TEST_LOG_NAME", "")
    if override:
        return override
    try:
        stem = Path(sys.argv[0]).stem if sys.argv and sys.argv[0] else ""
    except (TypeError, ValueError):
        stem = ""
    # Normalise common launcher noise (``__main__``, ``-c``, empty).
    if not stem or stem in {"__main__", "-c"}:
        return "run"
    return stem


def log_level() -> int:
    name = _env("TEST_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def per_scenario_enabled() -> bool:
    return _truthy(_env("TEST_LOG_PER_SCENARIO", "0"))


def echo_errors_enabled() -> bool:
    return _truthy(_env("TEST_LOG_ECHO_ERRORS", "1"))


def capture_root_enabled() -> bool:
    return _truthy(_env("TEST_LOG_CAPTURE_ROOT", "0"))


def run_started_at() -> datetime:
    """Return the timestamp the logger was first initialised (stable for the run)."""
    global _run_started_at
    if _run_started_at is None:
        _run_started_at = datetime.now()
    return _run_started_at


# ---------------------------------------------------------------------------
# Handler / formatter factories
# ---------------------------------------------------------------------------
def _make_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT)


def _make_file_handler(path: Path, level: int) -> logging.FileHandler:
    """Create a UTF-8 FileHandler that flushes on every record.

    ``logging.FileHandler`` already calls ``stream.flush()`` inside ``emit``,
    so records reach disk as soon as they are written -- this is important
    because host processes are sometimes killed mid-run and we want the
    last lines to survive.
    """
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(_make_formatter())
    return handler


def _make_stderr_handler(level: int) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(_make_formatter())
    return handler


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------
def get_log_file_path() -> Path | None:
    """Return the active main-log path, or ``None`` if uninitialised."""
    return _log_file_path


def get_logger() -> logging.Logger:
    """Return the run-scoped logger, initialising the main log file on first use.

    The logger is detached from ``logging.root`` (``propagate=False``), so
    host frameworks' built-in log capture never competes with us. A
    context-aware filter is attached so every record carries
    ``log_stage / log_scope / log_kind`` fields that the formatter uses.
    """
    global _logger, _log_file_path
    if _logger is not None:
        return _logger

    # Lazy import to avoid a circular dependency during package import.
    from .context import ContextFilter

    directory = log_dir()
    ts = run_started_at().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{log_name_stem()}-{ts}.log"

    level = log_level()
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    context_filter = ContextFilter()
    logger.addFilter(context_filter)

    file_handler = _make_file_handler(path, level)
    file_handler.addFilter(context_filter)
    logger.addHandler(file_handler)

    if echo_errors_enabled():
        stderr_handler = _make_stderr_handler(logging.ERROR)
        stderr_handler.addFilter(context_filter)
        logger.addHandler(stderr_handler)

    if capture_root_enabled():
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(file_handler)

    # Breadcrumb to stderr so interactive users immediately see where logs go.
    sys.stderr.write(f"[logging] run log -> {path}\n")
    sys.stderr.flush()

    _logger = logger
    _log_file_path = path
    return logger


def reset_for_tests() -> None:
    """Testing hook: forget cached state so the next ``get_logger`` reinitialises."""
    global _logger, _log_file_path, _run_started_at
    if _logger is not None:
        for h in list(_logger.handlers):
            _logger.removeHandler(h)
            try:
                h.close()
            except Exception:  # noqa: BLE001 -- a broken handler must not stop reconfiguration
                pass
        for f in list(_logger.filters):
            _logger.removeFilter(f)
    _logger = None
    _log_file_path = None
    _run_started_at = None
