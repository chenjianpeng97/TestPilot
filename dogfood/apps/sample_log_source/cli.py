"""sample_log_source CLI — reference adapter for the ``log-source`` port.

Reads ``*.log`` files from a local folder instead of SSH / a log platform /
Rancher, so the port contract (docs/spec/ports.md) can be exercised offline.
A real workspace copies this shape and swaps ``read_lines`` for its channel.

    python -m apps.sample_log_source --since 2026-11-04T09:00:00Z --until 2026-11-04T11:00:00Z --json
    python -m apps.sample_log_source --since 30m --until now --service order-service --grep failed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tuner_testkit.logging import log_info

from .core import parse_time, read_lines, select

DEFAULT_DIR = Path("data") / "sample-logs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps.sample_log_source",
        description="Read SUT backend logs for a time window (log-source port; local files in dogfood).",
    )
    parser.add_argument("--since", required=True, help="window start: ISO time, or relative like 15m / 2h (ago)")
    parser.add_argument("--until", required=True, help="window end: ISO time, relative, or now")
    parser.add_argument("--service", default="", help="only lines from this service")
    parser.add_argument("--grep", default="", help="only lines containing this text")
    parser.add_argument("--trace-id", default="", help="only lines carrying trace=<id>")
    parser.add_argument("--limit", type=int, default=500, help="maximum lines to return (1-5000)")
    parser.add_argument("--out", type=Path, default=None, help="also write the redacted lines to this file")
    parser.add_argument("--json", action="store_true", help="print a JSON result envelope to stdout")
    return parser


def _log_dir() -> Path:
    """Channel settings come from config OPS; the dogfood channel is a local folder."""
    try:
        from tuner_testkit.config import load_project_env

        ops = getattr(load_project_env(), "OPS", None) or {}
        folder = (ops.get("local_logs") or {}).get("dir")
        if folder:
            return Path(folder)
    except Exception:  # noqa: BLE001 -- adapter must work without a configured env
        pass
    return DEFAULT_DIR


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ns = build_parser().parse_args(argv)
    if not 1 <= ns.limit <= 5000:
        print("--limit must be between 1 and 5000", file=sys.stderr)
        return 2
    try:
        since, until = parse_time(ns.since), parse_time(ns.until)
    except ValueError as exc:
        print(f"bad time: {exc}", file=sys.stderr)
        return 2
    folder = _log_dir()
    if not folder.is_dir():
        print(f"log channel unavailable: {folder} not found", file=sys.stderr)
        return 3
    picked = select(
        read_lines(folder),
        since=since,
        until=until,
        service=ns.service,
        grep=ns.grep,
        trace_id=ns.trace_id,
        limit=ns.limit,
    )
    log_info("sample_log_source read", lines=len(picked), service=ns.service or "*", since=ns.since, until=ns.until)
    artifacts: list[str] = []
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text("\n".join(line.text for line in picked) + "\n", encoding="utf-8")
        artifacts.append(str(ns.out))
    if ns.json:
        envelope = {
            "status": "succeeded",
            "outputs": [line.to_dict() for line in picked],
            "artifacts": artifacts,
            "log_path": None,
        }
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        for line in picked:
            sys.stdout.write(line.text + "\n")
        sys.stdout.write(f"lines={len(picked)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
