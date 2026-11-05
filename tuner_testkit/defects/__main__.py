"""CLI: ``python -m tuner_testkit.defects check|new|next-id``.

    python -m tuner_testkit.defects check [knowledge/defects]
    python -m tuner_testkit.defects next-id [--date 2026-11-04]
    python -m tuner_testkit.defects new --title "部分退款后库存未回填" --severity 严重 --type 编码 \
        --found-in "assets/testsheet/261104订单/testsheet.md#D1" --round 261104订单 \
        --testcase Order-Refund-partial-amount --requirements REQ-order-refund-partial
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from tuner_testkit.defects.template import create, next_id
from tuner_testkit.defects.validate import SEVERITIES, STATUSES, TYPES, validate_dir

DEFAULT_DIR = "knowledge/defects"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tuner_testkit.defects", description="Defect library: check / new / next-id")
    sub = parser.add_subparsers(dest="cmd")
    check = sub.add_parser("check", help="validate knowledge/defects against docs/spec/defect-syntax.md")
    check.add_argument("path", nargs="?", default=DEFAULT_DIR)
    nid = sub.add_parser("next-id", help="print the next free DEF-<yyyymmdd>-<nnn>")
    nid.add_argument("--date", default=None, help="discovery date YYYY-MM-DD (default: today)")
    nid.add_argument("--dir", default=DEFAULT_DIR)
    new = sub.add_parser("new", help="create a defect file from the fixed template")
    new.add_argument("--title", required=True, help="one-line title, without the id")
    new.add_argument("--severity", required=True, choices=SEVERITIES)
    new.add_argument("--type", required=True, choices=TYPES, dest="defect_type")
    new.add_argument("--status", default="激活", choices=STATUSES)
    new.add_argument("--blocking", action="store_true", help="blocks further testing")
    new.add_argument("--date", default=None, help="discovery date YYYY-MM-DD (default: today)")
    new.add_argument("--found-in", default="/", help="assets/testsheet/<round>/testsheet.md#D<n>, or /")
    new.add_argument("--round", default="/", dest="round_name", help="testsheet round name for the history row")
    new.add_argument("--testcase", default="/", help="case ID, or /")
    new.add_argument("--requirements", default="", help="comma-separated REQ ids")
    new.add_argument("--sut-version", default=None)
    new.add_argument("--env", default=None)
    new.add_argument("--dir", default=DEFAULT_DIR)
    return parser


def _day(raw: str | None) -> date | None:
    return date.fromisoformat(raw) if raw else None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ns = build_parser().parse_args(argv)
    cmd = ns.cmd or "check"
    if cmd == "check":
        target = Path(getattr(ns, "path", DEFAULT_DIR))
        errors = validate_dir(target)
        if errors:
            for item in errors:
                print(item, file=sys.stderr)
            print(f"{len(errors)} error(s)", file=sys.stderr)
            return 1
        print(f"ok {target}")
        return 0
    if cmd == "next-id":
        print(next_id(Path(ns.dir), _day(ns.date)))
        return 0
    path = create(
        Path(ns.dir),
        day=_day(ns.date),
        title=ns.title.strip(),
        severity=ns.severity,
        defect_type=ns.defect_type,
        status=ns.status,
        blocking=ns.blocking,
        found_in=ns.found_in,
        round_name=ns.round_name,
        testcase=ns.testcase,
        requirements=[r.strip() for r in ns.requirements.split(",") if r.strip()],
        sut_version=ns.sut_version,
        env=ns.env,
    )
    print(json.dumps({"id": path.stem, "path": path.as_posix(), "next": "fill every （待填）, then check"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
