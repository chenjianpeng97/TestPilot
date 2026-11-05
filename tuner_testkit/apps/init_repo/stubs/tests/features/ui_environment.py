"""behave stage-mode: ``behave --stage ui`` loads hooks from this file.

Mirrors ``api_environment.py`` (both stages must wire the same logging and
report lifecycle) and adds the failed-step screenshot into
``artifacts/playwright/screenshots/`` when a Playwright page is on ``context``.
"""
from __future__ import annotations

from datetime import datetime

from tuner_testkit import artifacts
from tuner_testkit.logging import hooks as log_hooks
from tuner_testkit.project import artifacts_dir, ensure_project_on_path


def _get_playwright_page(context):
    for attr in ("page", "pw_page", "playwright_page"):
        page = getattr(context, attr, None)
        if page is not None:
            return page
    return None


def before_all(context):
    context.project_root = ensure_project_on_path()
    log_hooks.on_run_begin(context)
    artifacts.report_run_begin(context, root=context.project_root)


def after_all(context):
    artifacts.report_run_end(context)
    log_hooks.on_run_end(context)


def before_feature(context, feature):
    log_hooks.on_feature_begin(context, feature)


def after_feature(context, feature):
    log_hooks.on_feature_end(context, feature)


def before_scenario(context, scenario):
    log_hooks.on_scenario_begin(context, scenario)


def after_scenario(context, scenario):
    artifacts.report_scenario_end(context, scenario)
    log_hooks.on_scenario_end(context, scenario)


def before_step(context, step):
    log_hooks.on_step_begin(context, step)


def after_step(context, step):
    log_hooks.on_step_end(context, step)
    if step.status != "failed":
        return
    page = _get_playwright_page(context)
    if page is None:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_step = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in step.name)[:80]
    out_dir = artifacts_dir("playwright") / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(out_dir / f"ui_failed_step_{ts}_{safe_step}.png"), full_page=True)
    except Exception:  # noqa: BLE001 -- best-effort screenshot; must not mask the step failure
        return
