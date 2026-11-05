"""CLI: sync / check / bundle tuner-testkit DNA into a project repo."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from tuner_testkit.apps.dna.paths import DNA_PATHS, LEGACY_VERSION_MARKER, SYNC_RECORD
from tuner_testkit.apps.dna.source import (
    DnaSourceError,
    dna_source_root,
    iter_dna_files,
    payload_package_dir,
)
from tuner_testkit.apps.dna.targets import (
    TARGET_LAYOUTS,
    drift_file_map,
    parse_targets,
    render_target,
    sync_file_map,
)
from tuner_testkit.project import ProjectRootError, project_root


def _target_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return project_root()


def _targets(args: argparse.Namespace) -> list[str]:
    return parse_targets(getattr(args, "ide", None))


def read_sync_record(dest: Path) -> dict:
    """``.tuner-dna.json`` written by the last sync (empty dict when absent or unreadable)."""
    path = dest / SYNC_RECORD
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def installed_dna_version(dest: Path) -> str | None:
    record = read_sync_record(dest)
    if record.get("kit_version"):
        return str(record["kit_version"])
    try:
        text = (dest / LEGACY_VERSION_MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _write_sync_record(dest: Path, targets: dict[str, dict[str, str]]) -> None:
    payload = {"kit_version": _kit_version(), "targets": {k: dict(sorted(v.items())) for k, v in sorted(targets.items())}}
    (dest / SYNC_RECORD).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (dest / LEGACY_VERSION_MARKER).write_text(_kit_version() + "\n", encoding="utf-8")


def cmd_sync(args: argparse.Namespace) -> int:
    try:
        source = dna_source_root()
        dest = _target_root(args.target)
        targets = _targets(args)
    except (DnaSourceError, ProjectRootError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    record = read_sync_record(dest)
    recorded_targets: dict[str, dict[str, str]] = dict(record.get("targets") or {})
    kept_local = 0
    for target in targets:
        files = render_target(source, target)
        result = sync_file_map(
            dest,
            files,
            overwrite=bool(getattr(args, "overwrite", False)),
            recorded=recorded_targets.get(target) or {},
            prune=bool(getattr(args, "prune", False)),
        )
        recorded_targets[target] = result.written
        kept_local += len(result.kept_local) + len(result.prune_kept)
        print(f"dna sync[{target}]: {result.summary()} dest={dest}")
    _write_sync_record(dest, recorded_targets)
    if kept_local:
        print(
            f"{kept_local} locally edited DNA file(s) kept. Move local rules to `*.local.mdc` / "
            "`AGENTS.local.md`, then re-run with --overwrite.",
            file=sys.stderr,
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        source = dna_source_root()
        dest = _target_root(args.target)
        targets = _targets(args)
    except (DnaSourceError, ProjectRootError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    record = read_sync_record(dest)
    recorded_targets = record.get("targets") or {}
    report: dict[str, dict[str, list[str]]] = {}
    drifted = False
    for target in targets:
        drift = drift_file_map(dest, render_target(source, target), recorded_targets.get(target) or {})
        report[target] = {
            "missing": drift.missing,
            "outdated": drift.outdated,
            "edited": drift.edited,
            "removed_upstream": drift.removed,
        }
        drifted = drifted or drift.any
    if getattr(args, "json", False):
        payload = {
            "kit_version": _kit_version(),
            "installed_version": installed_dna_version(dest),
            "drifted": drifted,
            "targets": report,
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 1 if drifted else 0
    for target, groups in report.items():
        if not any(groups.values()):
            print(f"DNA[{target}] matches installed kit payload.")
            continue
        for label, rels in groups.items():
            for rel in rels:
                print(f"  [{target}] {label}: {rel}", file=sys.stderr)
    if drifted:
        print(
            "Run `tuner-dna sync --prune` to refresh untouched files and drop removed ones; "
            "edited files need --overwrite after you move local edits to `*.local.*`.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_targets(_args: argparse.Namespace) -> int:
    for name, layout in TARGET_LAYOUTS.items():
        print(f"{name:8s} skills={layout.skills_dir or '-':16s} agents={layout.agents_dir or '-':16s} "
              f"instructions={layout.instructions_file or '-':10s} {layout.note}")
    return 0


def cmd_bundle(_args: argparse.Namespace) -> int:
    """Copy DNA into tuner_testkit/apps/dna/dna_payload for wheel builds."""
    try:
        source = dna_source_root()
    except DnaSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    dest = payload_package_dir()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    count = 0
    for rel, src in iter_dna_files(source):
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        count += 1
    (dest / "MANIFEST.txt").write_text(
        json.dumps({"files": count, "paths": list(DNA_PATHS)}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"bundled {count} DNA files into {dest}")
    return 0


def _kit_version() -> str:
    try:
        from tuner_testkit import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tuner-dna",
        description="Sync AI-IDE / git DNA from tuner-testkit into a project repo (Cursor by default; --ide for others).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    ide_help = "comma-separated IDE targets: cursor (default), claude, agents, codex, all"

    p_sync = sub.add_parser("sync", help="copy / render DNA files into the project")
    p_sync.add_argument("--target", default=None, help="project root (default: cwd project)")
    p_sync.add_argument(
        "--overwrite", action="store_true", help="also overwrite DNA files edited locally (untouched files always refresh)"
    )
    p_sync.add_argument("--prune", action="store_true", help="delete untouched files the kit no longer ships")
    p_sync.add_argument("--ide", default=None, help=ide_help)
    p_sync.set_defaults(func=cmd_sync)

    p_check = sub.add_parser("check", help="report DNA drift vs the kit payload")
    p_check.add_argument("--target", default=None)
    p_check.add_argument("--ide", default=None, help=ide_help)
    p_check.add_argument("--json", action="store_true", help="print the drift report as JSON")
    p_check.set_defaults(func=cmd_check)

    p_targets = sub.add_parser("targets", help="list IDE targets and where each renders")
    p_targets.set_defaults(func=cmd_targets)

    p_bundle = sub.add_parser("bundle", help="copy DNA into the wheel payload directory")
    p_bundle.set_defaults(func=cmd_bundle)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
