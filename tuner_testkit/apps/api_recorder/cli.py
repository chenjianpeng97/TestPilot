"""CLI for the API Object HTTP(S) proxy recorder (mitmproxy)."""

from __future__ import annotations

import argparse
import asyncio
import pathlib

from tuner_testkit.project import (
    api_objects_dir,
    ensure_project_on_path,
    mocks_dir as default_mocks_dir,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tuner_testkit.apps.api_recorder",
        description=(
            "Start an HTTP(S) proxy that captures non-static API traffic and "
            "auto-maintains route-aligned API Objects under packages/api_objects "
            "(see docs/spec/api-objects-syntax.md). Does not freeze UI elements; "
            "for headed page+API 合录 use python -m tuner_testkit.apps.recorder."
        ),
    )
    p.add_argument(
        "--outputs_dir",
        type=pathlib.Path,
        default=None,
        help="API Objects root directory (default: <project>/packages/api_objects)",
    )
    p.add_argument(
        "--listen_host",
        default="127.0.0.1",
        help="Proxy bind address (default: 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Proxy listen port (default: 8080)",
    )
    p.add_argument(
        "--include_host",
        default="",
        help="Only freeze flows whose host contains this substring (optional)",
    )
    p.add_argument(
        "--ssl-insecure",
        action="store_true",
        help="Do not verify upstream TLS certificates (useful for lab envs)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Less console output",
    )
    p.add_argument(
        "--write-mocks",
        action="store_true",
        help=(
            "Also save the FULL (untruncated) response sample as a mock definition "
            "for apps.mock_server. The asset's _RECORDED_RESPONSE stays truncated "
            "for readability; this side-car keeps every row."
        ),
    )
    p.add_argument(
        "--mocks-dir",
        type=pathlib.Path,
        default=None,
        help="Where --write-mocks saves definitions (default: <project>/data/mocks)",
    )
    p.add_argument(
        "--mock-scenario",
        default="success",
        help=(
            "Scenario name the recorder writes/refreshes (default: success). "
            "Other scenarios in the file are preserved. Use a distinct name "
            "(e.g. recorded) to keep a hand-tuned 'success' untouched."
        ),
    )
    p.add_argument(
        "--mock-max-bytes",
        type=int,
        default=1_048_576,
        help="Skip mock writes whose JSON body exceeds this size (default: 1 MiB; 0 disables)",
    )
    return p


def _require_mitmproxy() -> None:
    try:
        import mitmproxy  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "mitmproxy is required for apps.api_recorder.\n"
            "Install with:  pip install 'mitmproxy>=10'\n"
            "Or:            pip install -e '.[recorder]'"
        ) from exc


def write_api_changelog(outputs_dir: pathlib.Path, items: list[str], *, tool: str = "api_recorder") -> None:
    """Append packages/api_objects/CHANGELOG.md when freeze touched routes."""
    if not items:
        return
    try:
        from tuner_testkit.apps._shared.changelog import append_entry
        from tuner_testkit.logging import log_info, log_warn
    except Exception as exc:  # noqa: BLE001
        print(f"api changelog skipped: {exc}")
        return
    try:
        append_entry(
            outputs_dir / "CHANGELOG.md",
            tool=tool,
            action="record-apis",
            items=items,
            count=len(items),
        )
        log_info("api changelog appended", count=len(items), tool=tool)
    except Exception as exc:  # noqa: BLE001
        log_warn("api changelog failed", error=str(exc))


async def _run_proxy(args: argparse.Namespace) -> None:
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    from tuner_testkit.api_objects.recording import MockSampleWriter

    from tuner_testkit.apps.api_recorder.addon import ApiObjectRecorderAddon

    ensure_project_on_path()
    outputs_dir = (
        args.outputs_dir.expanduser().resolve()
        if args.outputs_dir is not None
        else api_objects_dir()
    )
    outputs_dir.mkdir(parents=True, exist_ok=True)

    mock_writer = None
    mocks_dir = None
    if args.write_mocks:
        mocks_dir = (
            args.mocks_dir.expanduser().resolve()
            if args.mocks_dir is not None
            else default_mocks_dir()
        )
        mock_writer = MockSampleWriter(
            mocks_dir,
            scenario=args.mock_scenario,
            max_bytes=args.mock_max_bytes,
            tool="api_recorder",
        )

    addon = ApiObjectRecorderAddon(
        outputs_dir=outputs_dir,
        include_host=args.include_host or None,
        verbose=not args.quiet,
        mock_writer=mock_writer,
    )

    opts = Options(
        listen_host=args.listen_host,
        listen_port=args.port,
        ssl_insecure=bool(args.ssl_insecure),
    )
    master = DumpMaster(opts, with_termlog=not args.quiet, with_dumper=False)
    master.addons.add(addon)

    print(f"API Object recorder proxy listening on {args.listen_host}:{args.port}")
    print(f"Writing assets to: {outputs_dir}")
    if mocks_dir is not None:
        print(f"Writing full response samples to: {mocks_dir} (scenario '{args.mock_scenario}')")
    print("Point the browser / system HTTP(S) proxy here.")
    print("Static .js/.css (and similar assets) are ignored. UI elements are not captured.")
    print("For HTTPS, trust the mitmproxy CA (mitmproxy docs: about:certificates / certutil).")
    print("Ctrl+C to stop.\n")

    try:
        await master.run()
    finally:
        addon.done()
        write_api_changelog(outputs_dir, addon.pipeline.touched_items(), tool="api_recorder")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _require_mitmproxy()
    try:
        asyncio.run(_run_proxy(args))
    except KeyboardInterrupt:
        print("\nAPI recorder stopped.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
