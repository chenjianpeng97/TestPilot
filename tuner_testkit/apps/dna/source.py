"""Resolve the DNA file tree (editable template vs bundled payload)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tuner_testkit.apps.dna.paths import DNA_PATHS, is_local_override, is_platform_only
from tuner_testkit.project import template_source_root

TUNER_DNA_ROOT_VAR = "TUNER_DNA_ROOT"
_PAYLOAD_DIRNAME = "dna_payload"


class DnaSourceError(RuntimeError):
    """DNA files cannot be located."""


def payload_package_dir() -> Path:
    return Path(__file__).resolve().parent / _PAYLOAD_DIRNAME


def dna_source_root() -> Path:
    """Directory that contains ``.cursor/rules`` (template or bundled payload)."""
    explicit = (os.environ.get(TUNER_DNA_ROOT_VAR) or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / ".cursor" / "rules").is_dir():
            raise DnaSourceError(f"{TUNER_DNA_ROOT_VAR} has no .cursor/rules: {path}")
        return path
    editable = template_source_root()
    if editable is not None:
        return editable
    bundled = payload_package_dir()
    if (bundled / ".cursor" / "rules").is_dir():
        return bundled
    raise DnaSourceError(
        "cannot find DNA source: develop this repo, set TUNER_DNA_ROOT, "
        "or run `tuner-dna bundle` before building a wheel"
    )


def iter_dna_files(source: Path | None = None, *, include_platform_only: bool = False) -> list[tuple[str, Path]]:
    """Return (relative posix path, absolute file path) for every workspace DNA file.

    Platform-only paths and local-override files are skipped unless
    ``include_platform_only`` is set (the release manifest hashes the full tree).
    """
    root = source or dna_source_root()
    skip = {"__pycache__", ".pytest_cache"}
    found: list[tuple[str, Path]] = []

    def _keep(rel_path: str) -> bool:
        if is_local_override(rel_path):
            return False
        return include_platform_only or not is_platform_only(rel_path)

    for rel in DNA_PATHS:
        target = root / rel
        if target.is_file():
            rel_path = rel.replace("\\", "/")
            if _keep(rel_path):
                found.append((rel_path, target))
            continue
        if not target.is_dir():
            continue
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            rel_path = path.relative_to(root).as_posix()
            if _keep(rel_path):
                found.append((rel_path, path))
    found.sort(key=lambda item: item[0])
    return found


def copy_tree(src: Path, dst: Path) -> int:
    """Copy ``src`` into ``dst`` (file or directory). Returns files written."""
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    count = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        rel = path.relative_to(src)
        dest = dst / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        count += 1
    return count
