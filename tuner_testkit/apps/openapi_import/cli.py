"""``tuner-openapi-import``: freeze API objects from an OpenAPI / Swagger document.

The second channel for ``packages/api_objects`` besides traffic capture
(``tuner-recorder`` / Playwright MCP). Assets go through the same freezer, so a
route imported here and later recorded merges into one asset.

    tuner-openapi-import knowledge/raw/api/openapi.json --dry-run
    tuner-openapi-import knowledge/raw/api/openapi.json --path-prefix /api/orders --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tuner_testkit.logging import log_info, log_warn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuner-openapi-import",
        description="Freeze packages/api_objects from an OpenAPI 3 / Swagger 2 document (JSON; YAML with PyYAML).",
    )
    parser.add_argument("spec", type=Path, help="OpenAPI document, usually under knowledge/raw/")
    parser.add_argument("--path-prefix", default="", help="only operations whose path starts with this prefix")
    parser.add_argument("--tag", action="append", default=[], help="only operations with this tag (repeatable)")
    parser.add_argument("--out", type=Path, default=None, help="api_objects root (default: project packages/api_objects)")
    parser.add_argument("--write-mocks", action="store_true", help="also write data/mocks samples for each route")
    parser.add_argument("--dry-run", action="store_true", help="list operations without writing assets")
    parser.add_argument("--json", action="store_true", help="print a JSON result envelope")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ns = build_parser().parse_args(argv)
    from tuner_testkit.apps.openapi_import.convert import iter_exchanges, load_spec

    try:
        spec = load_spec(ns.spec)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"tuner-openapi-import: {exc}", file=sys.stderr)
        return 2
    exchanges = iter_exchanges(spec, path_prefix=ns.path_prefix, tags=ns.tag)
    rows: list[dict[str, str]] = []
    touched: list[str] = []
    if ns.dry_run:
        rows = [{"method": ex.method, "path": ex.path, "operation_id": ex.operation_id, "action": "planned"} for ex in exchanges]
    else:
        from tuner_testkit.api_objects.recording.pipeline import ApiCapturePipeline
        from tuner_testkit.apps.api_recorder.cli import write_api_changelog
        from tuner_testkit.project import api_objects_dir, mocks_dir

        outputs = ns.out or api_objects_dir()
        writer = None
        if ns.write_mocks:
            from tuner_testkit.api_objects.recording.mocks import MockSampleWriter

            writer = MockSampleWriter(mocks_dir())
        pipeline = ApiCapturePipeline(outputs_dir=outputs, mock_writer=writer, tool="openapi_import", verbose=False)
        for ex in exchanges:
            result = pipeline.ingest(
                method=ex.method,
                url=ex.url,
                request_headers=ex.request_headers,
                request_content=ex.request_content,
                response_status=ex.response_status,
                response_headers=ex.response_headers,
                response_content=ex.response_content,
            )
            action = result.action if result is not None else "skipped"
            rows.append({"method": ex.method, "path": ex.path, "operation_id": ex.operation_id, "action": action,
                         "asset": str(result.path) if result is not None else ""})
        touched = pipeline.touched_items()
        write_api_changelog(outputs, touched, tool="openapi_import")
    log_info("openapi_import", spec=str(ns.spec), operations=len(exchanges), touched=len(touched), dry_run=ns.dry_run)
    if not exchanges:
        log_warn("openapi_import no operations", spec=str(ns.spec), path_prefix=ns.path_prefix)
    if ns.json:
        envelope = {
            "status": "succeeded",
            "outputs": [{"kind": "operations", "count": len(rows), "touched": len(touched), "dry_run": ns.dry_run}, *rows],
            "artifacts": sorted({row["asset"] for row in rows if row.get("asset")}),
            "log_path": None,
        }
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        for row in rows:
            sys.stdout.write(f"{row['action']:8s} {row['method']:6s} {row['path']}\n")
        sys.stdout.write(f"operations={len(rows)} touched={len(touched)} dry_run={ns.dry_run}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
