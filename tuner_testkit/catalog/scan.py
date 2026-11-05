"""Static workspace scans. No pytest --collect-only, no SUT, no git writes.

Every function takes the workspace ``root`` and returns plain JSON-able rows.
Scans are bounded (``MAX_SCAN_FILES`` / ``MAX_PARSE_BYTES``) so a large repo
cannot stall the catalog.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from tuner_testkit.catalog.front_matter import parse_front_matter

SKIP_DIR_NAMES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
METHOD_RE = re.compile(r"""^\s*method\s*=\s*['\"]([A-Za-z]+)['\"]""", re.M)
PATH_RE = re.compile(r"""^\s*path\s*=\s*['\"]([^'\"]+)['\"]""", re.M)
PAGE_ID_RE = re.compile(r"""^\s*page_id\s*=\s*['\"]([^'\"]+)['\"]""", re.M)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
MAX_SCAN_FILES = 4000
MAX_PARSE_BYTES = 256_000
_SKIP_API_OBJECT_FILES = {"__init__.py", "conftest.py", "auth.py", "registry.py"}
_SKIP_API_OBJECT_DIRS = {"recording", "tests"}
_SKIP_PAGE_OBJECT_FILES = {"__init__.py", "conftest.py", "session.py", "pages.py"}
ASSET_CATEGORIES: tuple[str, ...] = (
    "sql",
    "testdesign",
    "testcases",
    "testsheet",
    "testreport",
)
WIKI_CATEGORIES: tuple[str, ...] = ("domain-notes", "usecases", "explore", "design")
KNOWLEDGE_CATEGORIES: tuple[str, ...] = ("raw", "wiki", "requirements", "defects")
# Pre-7.0 workspaces kept these under assets/ (``tuner-workspace migrate knowledge``).
LEGACY_KNOWLEDGE_IN_ASSETS: tuple[str, ...] = ("ddl", *WIKI_CATEGORIES)
_SKIP_KNOWLEDGE_NAMES = {"CHANGELOG.MD", "LOG.MD", "INDEX.MD", "README.MD"}


# ---------------------------------------------------------------------------
# Knowledge layer
# ---------------------------------------------------------------------------
def ddl_root(root: Path) -> Path:
    """``knowledge/ddl``, or the legacy ``assets/ddl`` while a workspace is unmigrated."""
    current = root / "knowledge" / "ddl"
    legacy = root / "assets" / "ddl"
    return legacy if not current.is_dir() and legacy.is_dir() else current


def scan_ddl(root: Path) -> list[dict[str, Any]]:
    ddl_dir = ddl_root(root)
    ddl: list[dict[str, Any]] = []
    if not ddl_dir.is_dir():
        return ddl
    children = sorted(p for p in ddl_dir.iterdir() if p.name not in SKIP_DIR_NAMES)
    subdirs = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file() and p.suffix.lower() == ".sql"]
    if subdirs:
        for folder in subdirs:
            tables = sorted(p.stem for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".sql")
            ddl.append({"datasource": folder.name, "path": _rel(root, folder), "table_count": len(tables), "tables": tables})
        return ddl
    if files:
        tables = sorted(p.stem for p in files)
        ddl.append({"datasource": "default", "path": _rel(root, ddl_dir), "table_count": len(tables), "tables": tables})
    return ddl


def scan_sql_files(root: Path) -> list[dict[str, str]]:
    sql_dir = root / "assets" / "sql"
    rows: list[dict[str, str]] = []
    if not sql_dir.is_dir():
        return rows
    for path in _iter_files(sql_dir):
        if path.suffix.lower() != ".sql":
            continue
        rows.append({"path": _rel(root, path), "name": path.name})
    return rows


def scan_assets(root: Path) -> list[dict[str, Any]]:
    """Markdown/SQL files of the knowledge layer (``knowledge/``) and the asset layer (``assets/``).

    Each row carries ``layer`` (``knowledge`` / ``assets``) and ``category``
    (``domain-notes`` / ``usecases`` / ``explore`` / ``design`` / ``wiki`` / ``raw`` /
    ``requirements`` / ``defects`` / ``testcases`` / …). DDL tables are listed by
    :func:`scan_ddl`; changelogs and index pages are skipped.
    """
    rows: list[dict[str, Any]] = []
    knowledge = root / "knowledge"
    for path in _iter_files(knowledge):
        if path.suffix.lower() not in {".md", ".sql"} or path.name.upper() in _SKIP_KNOWLEDGE_NAMES:
            continue
        parts = path.relative_to(knowledge).parts
        if parts[0] == "ddl":
            continue
        if parts[0] == "wiki" and len(parts) > 2 and parts[1] in WIKI_CATEGORIES:
            category = parts[1]
        elif parts[0] in KNOWLEDGE_CATEGORIES:
            category = parts[0]
        else:
            category = "other"
        rows.append(_knowledge_row(root, path, layer="knowledge", category=category))
    base = root / "assets"
    for path in _iter_files(base):
        if path.suffix.lower() not in {".md", ".sql"} or path.name.upper() == "CHANGELOG.MD":
            continue
        top = path.relative_to(base).parts[0]
        if top == "ddl":
            continue  # tables are listed by scan_ddl
        if top in LEGACY_KNOWLEDGE_IN_ASSETS:
            rows.append(_knowledge_row(root, path, layer="knowledge", category=top))
            continue
        rows.append(_knowledge_row(root, path, layer="assets", category=top if top in ASSET_CATEGORIES else "other"))
    return rows


def _knowledge_row(root: Path, path: Path, *, layer: str, category: str) -> dict[str, Any]:
    text = _read_text(path)
    meta = parse_front_matter(text) if path.suffix.lower() == ".md" else _sql_header_meta(text)
    title_match = H1_RE.search(text) if path.suffix.lower() == ".md" else None
    return {
        "path": _rel(root, path),
        "layer": layer,
        "category": category,
        "id": meta.get("id"),
        "title": title_match.group(1).strip() if title_match else path.stem,
        "domain": meta.get("domain"),
        "source": meta.get("source"),
        "date": str(meta.get("date")) if meta.get("date") is not None else None,
        "version": str(meta.get("version")) if meta.get("version") is not None else None,
        "confidence": meta.get("confidence"),
        "status": meta.get("status"),
        "author": meta.get("author"),
        "evidence": meta.get("evidence") if isinstance(meta.get("evidence"), list) else [],
    }


def _sql_header_meta(text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if not stripped.startswith("--"):
            if stripped:
                break
            continue
        body = stripped[2:].strip()
        key, sep, value = body.partition(":")
        if sep and key.strip() in {"domain", "source", "date", "version", "confidence", "author"}:
            meta[key.strip()] = value.strip()
    return meta


# ---------------------------------------------------------------------------
# Business assets (packages/)
# ---------------------------------------------------------------------------
def scan_api_objects(root: Path) -> list[dict[str, Any]]:
    base = root / "packages" / "api_objects"
    if not base.is_dir():
        return []
    rows = []
    for path in _iter_files(base):
        if path.suffix != ".py" or path.name.startswith("test_") or path.name in _SKIP_API_OBJECT_FILES:
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in _SKIP_API_OBJECT_DIRS or part.startswith("_") for part in rel_parts[:-1]):
            continue
        text = _read_text(path)
        method_match = METHOD_RE.search(text)
        path_match = PATH_RE.search(text)
        if not method_match and not path_match:
            continue  # helper module, not a frozen APIModel asset
        rows.append(
            {
                "method": (method_match.group(1) if method_match else "GET").upper(),
                "path": path_match.group(1) if path_match else f"/{path.stem}",
                "file": _rel(root, path),
                "name": path.stem,
            }
        )
    return rows


def scan_page_objects(root: Path) -> list[dict[str, Any]]:
    base = root / "packages" / "page_objects"
    if not base.is_dir():
        return []
    rows = []
    for path in _iter_files(base):
        if path.suffix != ".py" or path.name.startswith("test_") or path.name in _SKIP_PAGE_OBJECT_FILES:
            continue
        rel_parts = path.relative_to(base).parts
        if any(part == "tests" or part.startswith("_") for part in rel_parts[:-1]):
            continue
        text = _read_text(path)
        page_match = PAGE_ID_RE.search(text)
        if page_match is None and "PageModel" not in text and "BasePage" not in text:
            continue
        rows.append(
            {
                "page_id": page_match.group(1) if page_match else path.stem,
                "app": rel_parts[0] if len(rel_parts) > 1 else "",
                "path": _rel(root, path),
                "name": path.stem,
            }
        )
    return rows


def scan_action_words(root: Path, *, isolate: bool = True) -> list[dict[str, Any]]:
    """Registered action words with their pydantic params schema.

    Imports ``packages.action_words`` from *root* (the registry needs the real
    classes for ``Params.model_json_schema()``). Failures degrade to ``[]``
    so a broken word module never breaks the whole catalog.

    ``isolate=True`` (default, full catalog / tests) resets the registry and
    evicts ``packages.*``. ``isolate=False`` (workbench directory hot path)
    reuses an already-loaded registry from this root.
    """
    if not (root / "packages" / "action_words").is_dir():
        return []
    import os
    import sys

    from tuner_testkit.action_words import registry

    root = root.resolve()
    root_str = str(root)
    inserted = root_str not in sys.path
    if inserted:
        sys.path.insert(0, root_str)
    old_root = os.environ.get("TUNER_ROOT")
    os.environ["TUNER_ROOT"] = root_str
    try:
        if isolate or not _words_ready_for(root):
            registry.reset_registry_for_tests()
            for name in [m for m in sys.modules if m == "packages" or m.startswith("packages.")]:
                sys.modules.pop(name, None)
        rows = []
        for cls in registry.list_all():
            row = cls.describe()
            category = str(cls.category)
            row["destructive"] = category in {"db_seed", "api_request", "ui_action"}
            row["argv"] = ["python", "-m", "tuner_testkit.action_words", "run", cls.word_id]
            row["module"] = cls.__module__
            rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001 — catalog must survive a broken word module
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    finally:
        if old_root is None:
            os.environ.pop("TUNER_ROOT", None)
        else:
            os.environ["TUNER_ROOT"] = old_root
        if isolate:
            registry.reset_registry_for_tests()
        if inserted:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass


def _words_ready_for(root: Path) -> bool:
    """True when ``packages.action_words`` is already imported from *root* and registered."""
    import sys

    from tuner_testkit.action_words import registry

    if not registry._REGISTRY:  # noqa: SLF001 — cheap emptiness check
        return False
    mod = sys.modules.get("packages.action_words")
    file = getattr(mod, "__file__", None) or ""
    return bool(file and Path(file).resolve().is_relative_to(root))


# ---------------------------------------------------------------------------
# Tests / data / docs
# ---------------------------------------------------------------------------
def scan_features(root: Path) -> list[dict[str, Any]]:
    features = []
    search = root / "tests"
    if not search.is_dir():
        return features
    for path in _iter_files(search):
        if path.suffix != ".feature":
            continue
        rel = _rel(root, path)
        features.append(_parse_feature(rel, _read_text(path)))
    return features


def scan_pytest_nodes(root: Path) -> list[dict[str, str]]:
    base = root / "tests" / "pytest"
    if not base.is_dir():
        return []
    nodes = []
    for path in _iter_files(base):
        if path.suffix != ".py" or path.name in {"conftest.py", "__init__.py"}:
            continue
        rel = _rel(root, path)
        nodes.append({"nodeid": rel, "file": rel, "name": path.stem})
    return nodes


def scan_data_files(root: Path) -> list[dict[str, str]]:
    base = root / "data"
    if not base.is_dir():
        return []
    rows = []
    for path in _iter_files(base):
        if path.name.startswith(".") or ".local." in path.name:
            continue  # never list local credential files
        rows.append({"path": _rel(root, path), "name": path.name})
    return rows


def scan_docs(root: Path) -> dict[str, Any]:
    base = root / "docs"
    rows: list[dict[str, str]] = []
    if base.is_dir():
        for path in _iter_files(base):
            if path.suffix.lower() == ".md" and ".local." not in path.name:
                rows.append({"path": _rel(root, path), "name": path.name})
    return {"count": len(rows), "files": rows}


def scan_apps_readmes(root: Path) -> dict[str, dict[str, Any]]:
    """``apps/<name>/README.md`` front-matter keyed by app dir name (author / created…)."""
    base = root / "apps"
    out: dict[str, dict[str, Any]] = {}
    if not base.is_dir():
        return out
    for child in sorted(base.iterdir()):
        readme = child / "README.md"
        if child.is_dir() and readme.is_file():
            meta = parse_front_matter(_read_text(readme))
            out[child.name] = {"readme_path": _rel(root, readme), **{k: meta.get(k) for k in ("author", "created", "updated", "version", "title")}}
    return out


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------
def scan_inbox(root: Path, *, recent: int = 10) -> dict[str, Any]:
    base = root / "artifacts" / "inbox"
    rows: list[dict[str, Any]] = []
    if base.is_dir():
        for path in sorted(base.glob("*.md")):
            meta = parse_front_matter(_read_text(path))
            title = H1_RE.search(_read_text(path))
            rows.append(
                {
                    "path": _rel(root, path),
                    "agent": meta.get("agent"),
                    "slice": meta.get("slice"),
                    "status": meta.get("status") or "unknown",
                    "started": str(meta.get("started")) if meta.get("started") else None,
                    "ended": str(meta.get("ended")) if meta.get("ended") else None,
                    "author": meta.get("author"),
                    "title": title.group(1).strip() if title else path.stem,
                }
            )
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    rows.sort(key=lambda r: (r.get("started") or "", r["path"]), reverse=True)
    return {"total": len(rows), "by_status": by_status, "recent": rows[:recent]}


def scan_run_manifests(root: Path, kind_dir: str, *, recent: int = 10) -> dict[str, Any]:
    """``artifacts/<kind_dir>/<run_id>/manifest.json`` summaries, newest first."""
    base = root / "artifacts" / kind_dir
    rows: list[dict[str, Any]] = []
    if base.is_dir():
        for child in base.iterdir():
            manifest = child / "manifest.json"
            if not child.is_dir() or not manifest.is_file():
                continue
            try:
                data = json.loads(_read_text(manifest) or "{}")
            except json.JSONDecodeError:
                data = {}
            rows.append(
                {
                    "run_id": data.get("run_id") or child.name,
                    "kind": data.get("kind") or kind_dir,
                    "status": data.get("status") or "unknown",
                    "started": data.get("started"),
                    "ended": data.get("ended"),
                    "producer": data.get("producer") or {},
                    "summary": data.get("summary"),
                    "path": _rel(root, child),
                    "files": len(data.get("files") or []),
                }
            )
    rows.sort(key=lambda r: (r.get("started") or "", r["run_id"]), reverse=True)
    return {"total": len(rows), "recent": rows[:recent]}


# ---------------------------------------------------------------------------
# AI components / git
# ---------------------------------------------------------------------------
def scan_ai_components(root: Path) -> dict[str, int]:
    """Counts of rules / skills / agents / hook events under ``.cursor/`` (root or nearest parent)."""
    cursor = _find_cursor_dir(root)
    if cursor is None:
        return {"rules": 0, "skills": 0, "agents": 0, "hooks": 0, "source": None}
    rules = len(list((cursor / "rules").glob("*.mdc"))) if (cursor / "rules").is_dir() else 0
    skills = len(list((cursor / "skills").glob("*/SKILL.md"))) if (cursor / "skills").is_dir() else 0
    agents = len(list((cursor / "agents").glob("*.md"))) if (cursor / "agents").is_dir() else 0
    hooks = 0
    hooks_file = cursor / "hooks.json"
    if hooks_file.is_file():
        try:
            hooks = sum(len(v) for v in (json.loads(_read_text(hooks_file)).get("hooks") or {}).values())
        except json.JSONDecodeError:
            hooks = 0
    return {"rules": rules, "skills": skills, "agents": agents, "hooks": hooks, "source": str(cursor)}


def _find_cursor_dir(root: Path) -> Path | None:
    for parent in [root, *root.parents]:
        candidate = parent / ".cursor"
        if candidate.is_dir():
            return candidate
    return None


def read_git_meta(root: Path) -> dict[str, str | None]:
    git_dir = _git_dir(root)
    meta: dict[str, str | None] = {"branch": None, "sha": None, "user_email": None, "user_name": None}
    if git_dir is not None:
        head_file = git_dir / "HEAD"
        if head_file.is_file():
            head = head_file.read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(":", 1)[1].strip()
                meta["branch"] = ref.removeprefix("refs/heads/")
                ref_file = git_dir / ref
                sha = ref_file.read_text(encoding="utf-8").strip() if ref_file.is_file() else None
                if not sha:
                    packed = git_dir / "packed-refs"
                    if packed.is_file():
                        needle = f" {ref}"
                        for line in packed.read_text(encoding="utf-8").splitlines():
                            if line.endswith(needle):
                                sha = line.split(" ", 1)[0].strip()
                                break
                meta["sha"] = sha
            else:
                meta["sha"] = head or None
    meta["user_email"] = git_config_value(root, "user.email")
    meta["user_name"] = git_config_value(root, "user.name")
    return meta


def _git_dir(root: Path) -> Path | None:
    for parent in [root, *root.parents]:
        git = parent / ".git"
        if git.is_dir():
            return git
        if git.is_file():
            text = git.read_text(encoding="utf-8").strip()
            if text.lower().startswith("gitdir:"):
                raw = text.split(":", 1)[1].strip()
                candidate = Path(raw)
                return candidate if candidate.is_absolute() else (parent / candidate)
    return None


def git_config_value(root: Path, key: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "config", "--get", key],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return value or None


def git_first_author(root: Path, rel_path: str) -> str | None:
    """Email of the commit that added *rel_path* (``git log --diff-filter=A``), or ``None``."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ae", "--", rel_path],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _parse_feature(rel: str, text: str) -> dict[str, Any]:
    feature_name = Path(rel).stem
    feature_tags: list[str] = []
    pending_tags: list[str] = []
    scenarios: list[dict[str, Any]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("@"):
            pending_tags = [part.lstrip("@") for part in stripped.split() if part.startswith("@")]
            continue
        lower = stripped.lower()
        if lower.startswith("feature:"):
            name = stripped.split(":", 1)[1].strip()
            feature_name = name or feature_name
            feature_tags = pending_tags
            pending_tags = []
            continue
        if lower.startswith("scenario outline:") or lower.startswith("scenario:"):
            kind = "outline" if "outline" in lower else "scenario"
            name = stripped.split(":", 1)[1].strip()
            scenarios.append({"name": name, "tags": pending_tags, "type": kind})
            pending_tags = []
    return {"path": rel, "name": feature_name, "tags": feature_tags, "scenarios": scenarios}


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        count += 1
        if count > MAX_SCAN_FILES:
            return
        yield path


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_PARSE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
