"""Optional behave lifecycle hooks for the portable logging kit.

Call these from ``tests/features/<stage>_environment.py`` when running behave.
Non-behave tools (pytest, CLI scripts) should skip this module and just use
``get_logger`` / the helpers.

.. code-block:: python

    from tuner_testkit.logging import hooks as log_hooks

    def before_all(context):
        log_hooks.on_run_begin(context)

    def after_all(context):
        log_hooks.on_run_end(context)

    def before_feature(context, feature):
        log_hooks.on_feature_begin(context, feature)

    def after_feature(context, feature):
        log_hooks.on_feature_end(context, feature)

    def before_scenario(context, scenario):
        log_hooks.on_scenario_begin(context, scenario)

    def after_scenario(context, scenario):
        log_hooks.on_scenario_end(context, scenario)

    def before_step(context, step):
        log_hooks.on_step_begin(context, step)

    def after_step(context, step):
        log_hooks.on_step_end(context, step)

The hooks are ``behave``-agnostic at import time -- they only read
attributes off the objects passed in, so the package stays portable.
"""
from __future__ import annotations

import sys
from typing import Any

from .context import (
    clear_feature,
    clear_scenario,
    clear_step,
    set_feature,
    set_scenario,
    set_stage,
    set_step,
    use_kind,
)
from .core import (
    capture_root_enabled,
    get_log_file_path,
    get_logger,
    per_scenario_enabled,
)
from .scenario_file import begin_scenario_file, end_scenario_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stage_of(context: Any) -> str:
    """Resolve behave's ``--stage=<name>`` flag from the context config."""
    cfg = getattr(context, "config", None)
    stage = getattr(cfg, "stage", None)
    return (stage or "").strip() or ""


def _status_name(obj: Any) -> str:
    """Return a lowercase status name from step/scenario/feature-like objects."""
    status = getattr(obj, "status", None)
    if status is None:
        return "unknown"
    # behave >=1.2.7 uses Status enum; fall back to ``name`` or str.
    name = getattr(status, "name", None)
    return str(name or status).lower()


def _duration_of(obj: Any) -> float:
    return float(getattr(obj, "duration", 0.0) or 0.0)


def _error_text(obj: Any) -> str:
    """Best-effort extraction of a step/scenario error message."""
    exc = getattr(obj, "exception", None)
    if exc is not None:
        return f"{type(exc).__name__}: {exc}"
    msg = getattr(obj, "error_message", None)
    return str(msg or "").strip()


# ---------------------------------------------------------------------------
# Lifecycle callbacks
# ---------------------------------------------------------------------------
def on_run_begin(context: Any) -> None:
    """Initialise the run-scope logger and emit a start marker."""
    stage = _stage_of(context) or "run"
    set_stage(stage)

    logger = get_logger()
    with use_kind("RUN-BGN"):
        logger.info(
            "run started stage=%s log_file=%s argv=%s per_scenario=%s capture_root=%s",
            stage,
            get_log_file_path(),
            " ".join(sys.argv),
            per_scenario_enabled(),
            capture_root_enabled(),
        )


def on_run_end(context: Any) -> None:
    logger = get_logger()
    with use_kind("RUN-END"):
        logger.info("run finished")
    for handler in list(logger.handlers):
        try:
            handler.flush()
        except Exception:  # noqa: BLE001 -- a broken handler must not fail the test run
            pass


def on_feature_begin(context: Any, feature: Any) -> None:
    name = getattr(feature, "name", "") or "<feature>"
    set_feature(name)
    set_stage(_stage_of(context) or "run")
    logger = get_logger()
    with use_kind("FEA-BGN"):
        tags = ",".join(getattr(feature, "tags", []) or []) or "-"
        logger.info("feature begin tags=%s", tags)


def on_feature_end(context: Any, feature: Any) -> None:
    status = _status_name(feature)
    duration = _duration_of(feature)
    logger = get_logger()
    with use_kind("FEA-END"):
        logger.info("feature end status=%s duration=%.3fs", status, duration)
    clear_feature()


def on_scenario_begin(context: Any, scenario: Any) -> None:
    name = getattr(scenario, "name", "") or "<scenario>"
    set_scenario(name)
    set_stage(_stage_of(context) or "run")

    feature = getattr(scenario, "feature", None)
    feature_name = getattr(feature, "name", "") if feature else ""
    if per_scenario_enabled():
        begin_scenario_file(feature_name, name)

    logger = get_logger()
    with use_kind("SCE-BGN"):
        tags = ",".join(getattr(scenario, "tags", []) or []) or "-"
        logger.info("scenario begin tags=%s", tags)


def on_scenario_end(context: Any, scenario: Any) -> None:
    status = _status_name(scenario)
    duration = _duration_of(scenario)
    err = _error_text(scenario)
    logger = get_logger()
    with use_kind("SCE-END"):
        if err:
            logger.info("scenario end status=%s duration=%.3fs error=%s", status, duration, err)
        else:
            logger.info("scenario end status=%s duration=%.3fs", status, duration)

    if per_scenario_enabled():
        end_scenario_file()
    clear_scenario()


def on_step_begin(context: Any, step: Any) -> None:
    keyword = getattr(step, "keyword", "") or ""
    step_name = getattr(step, "name", "") or ""
    set_step(step_name)
    logger = get_logger()
    with use_kind("STP-BGN"):
        logger.info("%s %s", keyword.strip() or "-", step_name)


def on_step_end(context: Any, step: Any) -> None:
    status = _status_name(step)
    duration = _duration_of(step)
    err = _error_text(step)
    logger = get_logger()
    with use_kind("STP-END"):
        if status == "failed" and err:
            logger.error("status=%s duration=%.3fs error=%s", status, duration, err)
        else:
            logger.info("status=%s duration=%.3fs", status, duration)
    clear_step()
