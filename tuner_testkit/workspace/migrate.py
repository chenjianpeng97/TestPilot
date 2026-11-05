"""``tuner-workspace migrate knowledge``: move pre-7.0 SUT knowledge from ``assets/`` to ``knowledge/``.

Dry-run by default: prints the plan (moves, reference rewrites, new folders).
``--apply`` performs it. DNA files (``.cursor/``, ``docs/spec``, ``docs/changelog``,
``tools/git-hooks``, ``AGENTS.md``) are left alone: ``tuner-dna sync`` refreshes them.
Local secrets (``config/env_local.py``, ``data/*.local.yaml``) are never read.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

# Order matters: the testreport profile leaves domain-notes before the rest moves.
DIR_MOVES: tuple[tuple[str, str], ...] = (
    ("assets/ddl", "knowledge/ddl"),
    ("assets/domain-notes/testreport", "assets/testreport/profiles"),
    ("assets/domain-notes", "knowledge/wiki/domain-notes"),
    ("assets/usecases", "knowledge/wiki/usecases"),
    ("assets/explore", "knowledge/wiki/explore"),
    ("assets/design", "knowledge/wiki/design"),
)
FILE_MOVES: tuple[tuple[str, str], ...] = (("assets/CHANGELOG.md", "knowledge/ddl/CHANGELOG.md"),)
NEW_DIRS: tuple[str, ...] = (
    "knowledge/raw",
    "knowledge/wiki/domain-notes",
    "knowledge/wiki/usecases",
    "knowledge/wiki/explore",
    "knowledge/wiki/design",
    "knowledge/requirements",
    "knowledge/defects",
    "assets/sql",
    "assets/testdesign",
    "assets/testcases",
    "assets/testsheet",
    "assets/testreport",
    "work/tasks",
)
_REWRITE_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".feature", ".json", ".txt", ".toml", ".ini"}
_SKIP_TOP = {".git", ".venv", "venv", "node_modules", "artifacts", "logs", ".cursor", ".claude", ".agents", "tools"}
_SKIP_PREFIXES = ("docs/spec/", "docs/changelog/")
_SKIP_FILES = {"AGENTS.md", "CLAUDE.md", ".tuner-dna.json"}
_REF_RE = re.compile(
    r"(?<![\w./-])assets/(ddl|domain-notes/testreport|domain-notes|usecases|explore|design)(?=[/\s`'\")\]>,;:|#]|$)",
    re.M,
)
_REF_TARGET = {
    "ddl": "knowledge/ddl",
    "domain-notes/testreport": "assets/testreport/profiles",
    "domain-notes": "knowledge/wiki/domain-notes",
    "usecases": "knowledge/wiki/usecases",
    "explore": "knowledge/wiki/explore",
    "design": "knowledge/wiki/design",
}
_KNOWLEDGE_ZONE = (
    "\n### knowledge/：wiki / 需求 / 缺陷（自动区：路径与元数据）\n\n"
    "<!-- auto:begin:knowledge -->\n<!-- auto:end:knowledge -->\n"
)
_PORTS_ZONE = (
    "\n### 端口适配器（自动区；绑定写在 config `PORTS`，见 `docs/spec/ports.md`）\n\n"
    "<!-- auto:begin:ports -->\n<!-- auto:end:ports -->\n"
)


def rewrite_refs(text: str) -> tuple[str, int]:
    count = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return _REF_TARGET[match.group(1)]

    return _REF_RE.sub(_sub, text), count


def _iter_rewrite_candidates(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _REWRITE_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        top = rel.split("/", 1)[0]
        if top in _SKIP_TOP or rel.startswith(_SKIP_PREFIXES) or rel in _SKIP_FILES:
            continue
        if ".local." in path.name or path.name == "env_local.py":
            continue
        found.append(path)
    return found


def plan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    moves: list[dict[str, str]] = []
    conflicts: list[str] = []
    claimed: set[str] = set()
    for src_rel, dst_rel in DIR_MOVES:
        src = root / src_rel
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel in claimed:
                continue
            claimed.add(rel)
            target = dst_rel + "/" + path.relative_to(src).as_posix()
            dst = root / target
            if path.name == ".gitkeep" and dst.parent.is_dir():
                moves.append({"from": rel, "to": target, "action": "drop-gitkeep"})
                continue
            if dst.exists() and dst.read_bytes() != path.read_bytes():
                conflicts.append(f"{rel} -> {target} (target exists with different content)")
                continue
            moves.append({"from": rel, "to": target, "action": "move"})
    for src_rel, dst_rel in FILE_MOVES:
        src = root / src_rel
        if src.is_file():
            dst = root / dst_rel
            if dst.exists():
                moves.append({"from": src_rel, "to": dst_rel, "action": "append"})
            else:
                moves.append({"from": src_rel, "to": dst_rel, "action": "move"})
    rewrites: list[dict[str, Any]] = []
    for path in _iter_rewrite_candidates(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        _, count = rewrite_refs(text)
        if count:
            rewrites.append({"path": path.relative_to(root).as_posix(), "refs": count})
    index = root / "INDEX.project.md"
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    index_zones = [
        zone
        for zone, marker in (("knowledge", "auto:begin:knowledge"), ("ports", "auto:begin:ports"))
        if index_text and marker not in index_text
    ]
    new_dirs = [rel for rel in NEW_DIRS if not (root / rel).is_dir()]
    stubs = [rel for rel in ("knowledge/wiki/index.md", "knowledge/wiki/log.md") if not (root / rel).is_file()]
    return {
        "root": str(root),
        "needed": bool(moves or rewrites or index_zones or new_dirs or stubs),
        "moves": moves,
        "conflicts": conflicts,
        "rewrites": rewrites,
        "index_zones": index_zones,
        "new_dirs": new_dirs,
        "stubs": stubs,
    }


def apply(root: Path) -> dict[str, Any]:
    result = plan(root)
    if result["conflicts"]:
        result["applied"] = False
        result["error"] = "conflicts; resolve them by hand, then re-run"
        return result
    root = Path(result["root"])
    # Rewrite references in place first: the planned paths are pre-move paths.
    for row in result["rewrites"]:
        path = root / row["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(rewrite_refs(text)[0], encoding="utf-8", newline="\n")
    for move in result["moves"]:
        src = root / move["from"]
        dst = root / move["to"]
        if move["action"] == "drop-gitkeep":
            src.unlink()
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if move["action"] == "append":
            old = src.read_text(encoding="utf-8")
            body = "\n".join(line for line in old.splitlines() if line.startswith("- ")) + "\n"
            with dst.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
            src.unlink()
            continue
        if dst.exists():
            src.unlink()  # identical content (conflicts were excluded)
        else:
            shutil.move(str(src), str(dst))
    for src_rel, _ in DIR_MOVES:
        _remove_empty_tree(root / src_rel)
    for rel in NEW_DIRS:
        folder = root / rel
        folder.mkdir(parents=True, exist_ok=True)
        if not any(folder.iterdir()):
            (folder / ".gitkeep").write_text("", encoding="utf-8")
    stub_root = Path(__file__).resolve().parents[1] / "apps" / "init_repo" / "stubs"
    for rel in result["stubs"]:
        src = stub_root / rel
        if src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    if result["index_zones"]:
        _add_index_zones(root / "INDEX.project.md", result["index_zones"])
    result["applied"] = True
    return result


def _remove_empty_tree(folder: Path) -> None:
    if not folder.is_dir():
        return
    for child in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    try:
        folder.rmdir()
    except OSError:
        pass


def _add_index_zones(index: Path, zones: list[str]) -> None:
    text = index.read_text(encoding="utf-8")
    if "knowledge" in zones:
        anchor = "<!-- auto:end:ddl -->"
        text = text.replace(anchor, anchor + "\n" + _KNOWLEDGE_ZONE, 1) if anchor in text else text + _KNOWLEDGE_ZONE
    if "ports" in zones:
        anchor = "<!-- auto:end:apps -->"
        text = text.replace(anchor, anchor + "\n" + _PORTS_ZONE, 1) if anchor in text else text + _PORTS_ZONE
    index.write_text(text, encoding="utf-8", newline="\n")
