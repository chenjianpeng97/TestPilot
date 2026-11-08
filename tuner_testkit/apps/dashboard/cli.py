"""``tuner-dashboard refresh|status``."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from tuner_testkit.logging import log_info, log_warn
from tuner_testkit.project import project_root, reset_path_cache

from .collect import SECTIONS, collect
from .render import JSON_REL, MARKDOWN_NAME, read_markdown, write_outputs


def _emit(payload: dict[str, Any]) -> None:
    """Structured JSON for the Shell / AI (not a diagnostic print)."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _root(raw: str | None) -> Path:
    if not raw:
        return project_root()
    root = Path(raw).resolve()
    os.environ["TUNER_ROOT"] = str(root)
    reset_path_cache()
    return root


def cmd_refresh(args: argparse.Namespace) -> int:
    root = _root(args.root)
    sections = [s for s in SECTIONS if not (args.no_doctor and s == "doctor")]
    started = time.perf_counter()
    result = collect(root, sections=sections)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    summary = write_outputs(result, root=root, out_dir=out_dir)
    summary["timings"] = {**result["timings"], "total": int((time.perf_counter() - started) * 1000)}
    doctor = result["sections"].get("doctor") or {}
    if doctor and "error" not in doctor:
        summary["doctor"] = {
            "ok": doctor["ok"],
            "core": doctor["summary_core"],
            "feature": doctor["summary_feature"],
            "not_ok": [
                {"id": c["id"], "status": c["status"], "fix": c.get("fix", "")}
                for c in doctor["checks"]
                if c["status"] in {"warn", "missing", "error"}
            ],
        }
    (log_warn if summary["errors"] else log_info)(
        "dashboard_refreshed", changed=summary["changed"], errors=len(summary["errors"]), ms=summary["timings"]["total"]
    )
    _emit(summary)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = _root(args.root)
    json_path = root / JSON_REL
    if json_path.is_file():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        _emit({"source": str(json_path), "checked_at": data.get("checked_at"), "updated": data.get("updated"),
               "counts": data.get("counts", {})})
        return 0
    front = read_markdown(root / MARKDOWN_NAME)
    if front:
        _emit({"source": str(root / MARKDOWN_NAME), "checked_at": None, "updated": front.get("updated"),
               "counts": {k: v for k, v in front.items() if isinstance(v, int)}})
        return 0
    _emit({"source": None, "hint": "尚未统计：运行 uv run tuner-dashboard refresh"})
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tuner-dashboard", description="统计工作台看板数字（离线），工作台只读结果")
    sub = parser.add_subparsers(dest="cmd", required=True)
    refresh = sub.add_parser("refresh", help="统计并写 DASHBOARD.md 与 artifacts/catalogs/dashboard.json")
    refresh.add_argument("--root", default="", help="workspace 根目录（默认当前仓）")
    refresh.add_argument("--no-doctor", action="store_true", help="跳过 doctor 自检段")
    refresh.add_argument("--out-dir", default="", help="两份输出改写到这个目录（实测用，不动仓库）")
    refresh.set_defaults(func=cmd_refresh)
    status = sub.add_parser("status", help="只读已有结果，不统计")
    status.add_argument("--root", default="", help="workspace 根目录（默认当前仓）")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
