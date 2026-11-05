"""SUT project root and conventional asset paths.

Library code is imported from the installed kit. Generated assets and
``config/`` always live in the **project repo**, never next to this file
inside site-packages.

Resolution order for the project root:

1. ``TUNER_ROOT``
2. Walk up from cwd looking for ``pyproject.toml`` plus either a
   ``[tool.tuner-testkit]`` table or a ``packages/`` directory
3. Otherwise raise :class:`ProjectRootError` (never fall back to ``__file__``)
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

TUNER_ROOT_VAR = "TUNER_ROOT"


class ProjectRootError(RuntimeError):
    """Project root could not be resolved (never fall back to kit ``__file__``)."""

_DEFAULT_RELATIVE = {
    "page_objects": "packages/page_objects",
    "api_objects": "packages/api_objects",
    "action_words": "packages/action_words",
    "mocks": "data/mocks",
    # knowledge layer — see docs/spec/knowledge-syntax.md
    "knowledge": "knowledge",
    "ddl": "knowledge/ddl",
    "raw": "knowledge/raw",
    "wiki": "knowledge/wiki",
    "requirements": "knowledge/requirements",
    "defects": "knowledge/defects",
    # asset layer (Markdown) — see docs/spec/assets-knowledge-syntax.md
    "assets": "assets",
    "testcases": "assets/testcases",
    "testsheet": "assets/testsheet",
    "testdesign": "assets/testdesign",
    "testreport": "assets/testreport",
    "config": "config",
    # artifacts layout — see docs/spec/artifacts-layout.md
    "artifacts": "artifacts",
    "artifacts_evidence": "artifacts/evidence",
    "artifacts_inbox": "artifacts/inbox",
    "artifacts_runs": "artifacts/runs",
    "artifacts_reports": "artifacts/reports",
    "artifacts_catalogs": "artifacts/catalogs",
    "artifacts_exports": "artifacts/exports",
    "artifacts_playwright": "artifacts/playwright",
    "artifacts_page_test": "artifacts/page_test",
}

_ENV_OVERRIDES = {
    "page_objects": "TUNER_PAGE_OBJECTS_DIR",
    "api_objects": "TUNER_API_OBJECTS_DIR",
    "mocks": "TUNER_MOCKS_DIR",
    "ddl": "TUNER_DDL_DIR",
    "artifacts": "TUNER_ARTIFACTS_DIR",
    "artifacts_page_test": "PAGE_TEST_ARTIFACTS_DIR",
}

# Pre-7.0 workspaces kept SUT knowledge under assets/. Until
# ``tuner-workspace migrate knowledge --apply`` runs, read from the old place.
LEGACY_RELATIVE = {
    "ddl": "assets/ddl",
}


def template_source_root() -> Path | None:
    """Repo that contains kit source **and** DNA (``.cursor/rules``).

    Used by ``init_repo`` / ``dna bundle``. ``None`` when the kit is installed
    from a wheel (no DNA tree beside ``site-packages``).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tuner_testkit" / "project.py").is_file() and (
            parent / ".cursor" / "rules"
        ).is_dir():
            return parent
    return None


def _looks_like_project(root: Path) -> bool:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    if (root / "packages").is_dir():
        return True
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return False
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    return "tuner-testkit" in tool


def project_root(*, environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    """Return the SUT repo root (directory that owns ``config/`` and ``packages/``)."""
    env_map = os.environ if environ is None else environ
    explicit = (env_map.get(TUNER_ROOT_VAR) or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir():
            raise ProjectRootError(f"{TUNER_ROOT_VAR}={explicit!r} is not a directory")
        return path

    start = (cwd or Path.cwd()).resolve()
    for parent in [start, *start.parents]:
        if _looks_like_project(parent):
            return parent
    raise ProjectRootError(
        "cannot find project root: set TUNER_ROOT or run from a repo with "
        "pyproject.toml and packages/ (or [tool.tuner-testkit])"
    )


def ensure_project_on_path(root: Path | None = None) -> Path:
    """Insert the project root at the front of ``sys.path`` so ``config`` and
    ``packages`` (SUT assets) import correctly."""
    found = root or project_root()
    as_str = str(found)
    if as_str not in sys.path:
        sys.path.insert(0, as_str)
    return found


def _tool_table(root: Path) -> dict[str, Any]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    table = tool.get("tuner-testkit")
    return table if isinstance(table, dict) else {}


@lru_cache(maxsize=1)
def _paths_cached(root_str: str) -> dict[str, Path]:
    root = Path(root_str)
    table = _tool_table(root)
    resolved: dict[str, Path] = {}
    for key, default_rel in _DEFAULT_RELATIVE.items():
        env_name = _ENV_OVERRIDES.get(key)
        env_val = (os.environ.get(env_name) or "").strip() if env_name else ""
        if env_val:
            candidate = Path(env_val).expanduser()
            resolved[key] = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            continue
        configured = table.get(key)
        rel = str(configured or default_rel).replace("\\", "/")
        path = (root / rel).resolve()
        legacy = LEGACY_RELATIVE.get(key)
        if not configured and legacy and not path.exists() and (root / legacy).is_dir():
            path = (root / legacy).resolve()
        resolved[key] = path
    return resolved


def reset_path_cache() -> None:
    """Test helper."""
    _paths_cached.cache_clear()


def asset_path(kind: str, *parts: str) -> Path:
    """Absolute path for a conventional asset area (``page_objects``, ``api_objects``, …)."""
    root = project_root()
    mapping = _paths_cached(str(root))
    if kind not in mapping:
        raise KeyError(f"unknown asset kind {kind!r}; known: {sorted(mapping)}")
    base = mapping[kind]
    return base.joinpath(*parts) if parts else base


def page_objects_dir() -> Path:
    return asset_path("page_objects")


def api_objects_dir() -> Path:
    return asset_path("api_objects")


def mocks_dir() -> Path:
    return asset_path("mocks")


def ddl_dir() -> Path:
    return asset_path("ddl")


def knowledge_dir(kind: str | None = None) -> Path:
    """``knowledge/`` (``kind=None``) or one of ``ddl`` / ``raw`` / ``wiki`` / ``requirements`` / ``defects``."""
    return asset_path(kind or "knowledge")


def config_dir() -> Path:
    return asset_path("config")


def artifacts_page_test_dir() -> Path:
    return asset_path("artifacts_page_test")


def artifacts_dir(kind: str | None = None) -> Path:
    """``artifacts/`` (``kind=None``) or one of its conventional sub-areas
    (``evidence`` / ``inbox`` / ``runs`` / ``reports`` / ``catalogs`` / ``exports`` / ``playwright``)."""
    return asset_path("artifacts" if not kind else f"artifacts_{kind}")
