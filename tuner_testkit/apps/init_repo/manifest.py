"""Release manifest: version + content hashes of DNA files (not the Python kit).

The wheel carries runtime code. This manifest tracks Cursor/git DNA so
``tuner-dna check`` / ``init_repo manifest --check`` can detect overlay drift.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from dataclasses import dataclass

from tuner_testkit.apps.dna.paths import DNA_PATHS, is_platform_only

MANIFEST_PATH = pathlib.Path(__file__).resolve().parent / "release_manifest.json"

PLATFORM_PATHS: tuple[str, ...] = DNA_PATHS

_EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
_EXCLUDE_NAMES = {"release_manifest.json", "env_local.py", ".active_env"}


def repo_root() -> pathlib.Path:
    from tuner_testkit.project import project_root, template_source_root

    return template_source_root() or project_root()


# Back-compat alias used by older call sites / tests
REPO_ROOT = None  # resolved lazily via repo_root()


def read_template_version(root: pathlib.Path | None = None) -> str:
    """Read ``[project] version`` from pyproject.toml (stdlib tomllib)."""
    pyproject = (root or repo_root()) / "pyproject.toml"
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("version", "0.0.0"))
    except Exception:  # noqa: BLE001 -- fall back to regex
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else "0.0.0"


def _iter_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Files that ship as DNA: platform-only paths (e.g. FRAMEWORK.md) are not hashed."""
    files: list[pathlib.Path] = []
    for rel in PLATFORM_PATHS:
        target = root / rel
        if target.is_file():
            if not is_platform_only(rel):
                files.append(target)
        elif target.is_dir():
            for path in target.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in _EXCLUDE_PARTS for part in path.parts):
                    continue
                if path.suffix in _EXCLUDE_SUFFIXES or path.name in _EXCLUDE_NAMES:
                    continue
                if is_platform_only(path.relative_to(root).as_posix()):
                    continue
                files.append(path)
    return sorted(set(files))


def compute_hashes(root: pathlib.Path | None = None) -> dict[str, str]:
    base = root or repo_root()
    hashes: dict[str, str] = {}
    for path in _iter_files(base):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = str(path.relative_to(base)).replace("\\", "/")
        hashes[rel] = digest
    return hashes


def build_manifest(root: pathlib.Path | None = None, version: str | None = None) -> dict:
    import datetime as _dt

    base = root or repo_root()
    return {
        "template_version": version or read_template_version(base),
        "generated_at": _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tracked_paths": list(PLATFORM_PATHS),
        "files": compute_hashes(base),
    }


def write_manifest(root: pathlib.Path | None = None, version: str | None = None) -> pathlib.Path:
    base = root or repo_root()
    manifest = build_manifest(base, version)
    path = MANIFEST_PATH
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_manifest() -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


@dataclass
class Drift:
    added: list[str]
    removed: list[str]
    changed: list[str]

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def check_drift(root: pathlib.Path | None = None) -> Drift | None:
    manifest = load_manifest()
    if manifest is None:
        return None
    stored: dict[str, str] = manifest.get("files", {})
    current = compute_hashes(root or repo_root())
    stored_keys = set(stored)
    current_keys = set(current)
    added = sorted(current_keys - stored_keys)
    removed = sorted(stored_keys - current_keys)
    changed = sorted(
        k for k in (stored_keys & current_keys) if stored[k] != current[k]
    )
    return Drift(added=added, removed=removed, changed=changed)
