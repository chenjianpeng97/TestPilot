"""CLI: ``tuner-workbench`` — serve 127.0.0.1, open browser; catalog refresh runs in the background."""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuner-workbench",
        description="Local workbench over this workspace (127.0.0.1 only; no database).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1; do not expose)")
    parser.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    parser.add_argument("--root", default=None, help="workspace root (default: tuner project_root())")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    parser.add_argument("--reload", action="store_true", help="dev reload (uvicorn)")
    return parser


def _write_catalog(root: Path) -> None:
    """Refresh ``artifacts/catalogs/workspace.json`` off the request path (it runs git log per asset)."""
    from tuner_testkit.catalog.build import build_catalog, write_catalog
    from tuner_testkit.logging import log_warn

    try:
        write_catalog(build_catalog(root), root / "artifacts" / "catalogs" / "workspace.json")
    except Exception as exc:  # noqa: BLE001 -- the server must keep running without the catalog file
        log_warn("workbench_catalog_failed", error=f"{type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    if ns.host not in {"127.0.0.1", "localhost", "::1"}:
        sys.stderr.write("tuner-workbench refuses to bind outside the loopback interface.\n")
        return 2
    from tuner_testkit.project import project_root
    from tuner_testkit.workbench.app import create_app

    root = Path(ns.root).resolve() if ns.root else project_root()
    threading.Thread(target=_write_catalog, args=(root,), name="workspace-catalog", daemon=True).start()
    app = create_app(root=root)
    url = f"http://{ns.host}:{ns.port}/"
    sys.stdout.write(f"tuner-workbench serving {url}  root={root}\n")
    if not ns.no_browser:
        webbrowser.open(url)
    try:
        import uvicorn
    except ImportError:
        sys.stderr.write("uvicorn is required: uv add 'tuner-testkit[workbench]' (or [mock])\n")
        return 2
    uvicorn.run(app, host=ns.host, port=ns.port, reload=ns.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
