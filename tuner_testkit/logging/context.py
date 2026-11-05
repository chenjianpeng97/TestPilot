"""Context propagation for the portable logging kit.

Every log record carries five context fields that the formatter prints:

- ``log_stage``  — run stage (``ui`` / ``api`` / ``run`` for out-of-scenario /
                   non-behave tools)
- ``log_scope``  — ``feature::scenario`` (or ``feature`` / ``-`` when narrower
                   context is unavailable)
- ``log_kind``   — short event category (``DATA`` / ``API`` / ``ASSERT`` / ...)
- ``log_feature`` / ``log_scenario`` / ``log_step`` — individual pieces
                   available to consumers that want custom formatting

Context is stored in ``contextvars`` so it is both thread-safe and immune to
re-entrancy inside nested calls. A ``logging.Filter`` reads the context-vars
at record time and copies the values onto the ``LogRecord`` so the formatter
string ``%(log_kind)s`` etc. work without any per-call ``extra=`` kwargs.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator

# ---------------------------------------------------------------------------
# Context data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LogContext:
    """Snapshot of the execution context visible to the logger."""

    stage: str = "run"
    feature: str = ""
    scenario: str = ""
    step: str = ""

    def scope(self) -> str:
        if self.feature and self.scenario:
            return f"{self.feature}::{self.scenario}"
        if self.feature:
            return self.feature
        return "-"


_current: contextvars.ContextVar[LogContext] = contextvars.ContextVar(
    "log_context", default=LogContext()  # noqa: B039 -- LogContext is a frozen dataclass
)


def current() -> LogContext:
    return _current.get()


def set_stage(stage: str) -> None:
    _current.set(replace(_current.get(), stage=stage or "run"))


def set_feature(name: str) -> None:
    _current.set(replace(_current.get(), feature=name or ""))


def clear_feature() -> None:
    _current.set(replace(_current.get(), feature="", scenario="", step=""))


def set_scenario(name: str) -> None:
    _current.set(replace(_current.get(), scenario=name or "", step=""))


def clear_scenario() -> None:
    _current.set(replace(_current.get(), scenario="", step=""))


def set_step(text: str) -> None:
    _current.set(replace(_current.get(), step=text or ""))


def clear_step() -> None:
    _current.set(replace(_current.get(), step=""))


# ---------------------------------------------------------------------------
# Per-record "kind" override (ASSERT / DATA / API / UI / STP-BGN / ...)
# ---------------------------------------------------------------------------
_kind: contextvars.ContextVar[str] = contextvars.ContextVar("log_kind", default="INFO")


@contextmanager
def use_kind(kind: str) -> Iterator[None]:
    """Temporarily override the ``kind`` tag emitted for log calls made inside."""
    token = _kind.set(kind)
    try:
        yield
    finally:
        _kind.reset(token)


def current_kind() -> str:
    return _kind.get()


# ---------------------------------------------------------------------------
# Logging filter -- copies contextvars onto each record
# ---------------------------------------------------------------------------
_LEVELNAME_ALIAS = {"WARNING": "WARN", "CRITICAL": "CRIT"}


class ContextFilter(logging.Filter):
    """Inject ``log_*`` fields onto every record consumed by our handlers."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - logging API
        ctx = _current.get()

        # Respect an explicit kind passed via ``extra={"log_kind": "DATA"}``
        # (that path wins) -- otherwise use the context-var kind.
        kind = getattr(record, "log_kind", None) or _kind.get() or "INFO"

        # Normalise levelname so log columns stay aligned regardless of severity.
        # Applied here (via filter) instead of ``addLevelName`` so we do not
        # mutate stdlib-global state that other loggers share.
        record.levelname = _LEVELNAME_ALIAS.get(record.levelname, record.levelname)

        record.log_stage = (ctx.stage or "run")[:3].ljust(3)
        record.log_feature = ctx.feature
        record.log_scenario = ctx.scenario
        record.log_step = ctx.step
        record.log_scope = ctx.scope()
        record.log_kind = kind
        return True
