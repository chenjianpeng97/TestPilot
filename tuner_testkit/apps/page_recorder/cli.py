"""CLI for the Page Object recorder (headed browser, live-freeze)."""
from __future__ import annotations

import argparse
import pathlib

from tuner_testkit.logging import log_info, log_warn
from tuner_testkit.project import ensure_project_on_path, page_objects_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tuner_testkit.apps.page_recorder",
        description=(
            "Launch a headed Playwright browser and freeze PageModel assets into "
            "packages/page_objects/ as you click, fill, and browse "
            "(see docs/spec/page-objects-syntax.md)."
        ),
    )
    parser.add_argument(
        "--app",
        required=True,
        help="应用名，写入 id '<app>.<page_slug>@v1' 与目录 packages/page_objects/<app>/",
    )
    parser.add_argument(
        "--flow",
        default="recorded",
        help="写入的 flow 名（默认 recorded）",
    )
    parser.add_argument(
        "--url",
        default="",
        help="起始 URL；相对路径拼到 TEST_UI_BASE_URL / TEST_BASE_URL",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="进入每个新 URL 后扫描可见的 button/link/textbox 等，只扩元素表",
    )
    parser.add_argument(
        "--outputs_dir",
        type=pathlib.Path,
        default=None,
        help="Page Objects 根目录（默认: <project>/packages/page_objects）",
    )
    parser.add_argument(
        "--storage-state",
        default="",
        help="可选 Playwright storage_state JSON（已登录会话；凭据不进资产）",
    )
    parser.add_argument(
        "--include_host",
        default="",
        help="只冻结 host 包含该子串的页面（可选）",
    )
    return parser


def _validate_app(app: str) -> str:
    name = (app or "").strip()
    if not name or not name.replace("_", "").replace("-", "").isalnum() or not name[0].isalpha():
        raise SystemExit("--app 必须是字母开头的标识（如 plane）")
    return name.replace("-", "_")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = _validate_app(args.app)
    flow = (args.flow or "recorded").strip() or "recorded"
    ensure_project_on_path()
    outputs_dir = (
        args.outputs_dir.expanduser().resolve()
        if args.outputs_dir is not None
        else page_objects_dir()
    )
    outputs_dir.mkdir(parents=True, exist_ok=True)

    from .session import PageRecorderSession, resolve_start_url

    try:
        start_url = resolve_start_url(args.url or None)
    except SystemExit:
        raise

    storage_state = (args.storage_state or "").strip() or None
    session = PageRecorderSession(
        app=app,
        flow=flow,
        outputs_dir=outputs_dir,
        start_url=start_url,
        scan=bool(args.scan),
        include_host=args.include_host or None,
        storage_state=storage_state,
    )
    try:
        session.run()
    except KeyboardInterrupt:
        log_info("page_recorder stopped (Ctrl+C)")
    except Exception as exc:  # noqa: BLE001
        log_warn("page_recorder aborted", error=str(exc))
        from tuner_testkit.page_test.errors import DriverError

        if isinstance(exc, DriverError):
            raise SystemExit(str(exc)) from exc
        raise SystemExit(f"page_recorder failed: {exc}") from exc
    finally:
        _write_changelog(outputs_dir, app=app, items=session.freezer.touched_ids)

    return 0


def _write_changelog(outputs_dir: pathlib.Path, *, app: str, items: list[str]) -> None:
    try:
        from tuner_testkit.apps._shared.changelog import append_entry
    except Exception as exc:  # noqa: BLE001
        log_warn("page_recorder changelog skipped", error=str(exc))
        return
    if not items:
        return
    append_entry(
        outputs_dir / "CHANGELOG.md",
        tool="page_recorder",
        action="record-pages",
        items=items,
        app=app,
        count=len(items),
    )
    log_info("page_recorder changelog appended", count=len(items), app=app)


if __name__ == "__main__":
    raise SystemExit(main())
