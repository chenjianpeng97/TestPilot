"""sample_tool CLI — generates ``count`` labelled sample lines.

Exists so the workbench and the QA-day journeys have a fully offline tool with
several argparse parameter kinds (required int option, free-text option, enum
choice, boolean flag, ``--json`` envelope). It writes nothing outside
``artifacts/runs/<run_id>/`` when ``--out`` is given.

    python -m apps.sample_tool --count 3 --label demo
    python -m apps.sample_tool --count 3 --label demo --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tuner_testkit.logging import log_info

from .core import build_lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps.sample_tool",
        description="Generate labelled sample lines (offline fixture tool).",
    )
    parser.add_argument("--count", type=int, required=True, help="how many sample lines to generate (1-100)")
    parser.add_argument("--label", default="sample", help="label prefix written into every line")
    parser.add_argument(
        "--style",
        choices=("plain", "upper"),
        default="plain",
        help="text style of the generated lines",
    )
    parser.add_argument("--dry-run", action="store_true", help="only report what would be generated")
    parser.add_argument("--out", type=Path, default=None, help="optional file to write the lines into")
    parser.add_argument("--json", action="store_true", help="print a JSON result envelope to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ns = build_parser().parse_args(argv)
    if not 1 <= ns.count <= 100:
        print("--count must be between 1 and 100", file=sys.stderr)
        return 2

    lines = build_lines(ns.count, ns.label, ns.style)
    log_info("sample_tool run", count=ns.count, label=ns.label, style=ns.style, dry_run=ns.dry_run)

    outputs: list[str] = []
    if ns.out is not None and not ns.dry_run:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        outputs.append(str(ns.out))

    if ns.json:
        envelope = {
            "status": "succeeded",
            "outputs": [{"kind": "lines", "count": len(lines), "label": ns.label, "dry_run": ns.dry_run}],
            "artifacts": outputs,
            "log_path": None,
        }
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        for line in lines:
            sys.stdout.write(line + "\n")
        sys.stdout.write(f"label={ns.label} count={len(lines)} dry_run={ns.dry_run}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
