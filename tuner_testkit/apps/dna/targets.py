"""Render the (Cursor-shaped) DNA source into other AI-IDE layouts.

The canonical DNA lives in ``.cursor/**`` + ``AGENTS.md`` + ``docs/spec`` +
``tools/git-hooks``. Other tools read different paths, so ``tuner-dna sync
--target <name>`` renders a *file map* (relative path → bytes) per target:

* ``cursor``  — verbatim DNA (the historical behaviour).
* ``claude``  — ``.claude/skills/<name>/**`` (SKILL.md is the open Agent Skills
  format), ``.claude/agents/<name>.md``, and a generated ``CLAUDE.md`` that
  imports ``AGENTS.md`` and inlines always-on rules / lists glob rules.
* ``agents``  — ``.agents/skills/<name>/**`` (cross-tool Agent Skills location).
* ``codex``   — alias of ``agents`` (Codex reads ``AGENTS.md`` natively).

Directory names are data (``TARGET_LAYOUTS``) so they can be adjusted per tool
release without touching the renderer. Cursor-specific ``hooks.json`` is never
translated: hook schemas differ between tools.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tuner_testkit.apps.dna.paths import PLATFORM_ONLY_BEGIN, PLATFORM_ONLY_END, is_local_override
from tuner_testkit.apps.dna.source import iter_dna_files

FileMap = dict[str, bytes]
_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
_TEXT_SUFFIXES = (".md", ".mdc")
_PLATFORM_BLOCK_RE = re.compile(
    r"[ \t]*" + re.escape(PLATFORM_ONLY_BEGIN) + r".*?" + re.escape(PLATFORM_ONLY_END) + r"[ \t]*\r?\n?",
    re.S,
)


def strip_platform_only(text: str) -> str:
    """Drop ``<!-- platform-only:begin -->…<!-- platform-only:end -->`` blocks."""
    if PLATFORM_ONLY_BEGIN not in text:
        return text
    return _PLATFORM_BLOCK_RE.sub("", text)


def _workspace_bytes(rel: str, path: Path) -> bytes:
    data = path.read_bytes()
    if not rel.endswith(_TEXT_SUFFIXES):
        return data
    text = data.decode("utf-8")
    stripped = strip_platform_only(text)
    return data if stripped == text else stripped.encode("utf-8")


@dataclass(frozen=True)
class TargetLayout:
    name: str
    skills_dir: str | None  # where SKILL.md folders go
    agents_dir: str | None  # where subagent .md files go
    instructions_file: str | None  # generated always-on instructions file (imports AGENTS.md)
    note: str


TARGET_LAYOUTS: dict[str, TargetLayout] = {
    "cursor": TargetLayout("cursor", None, None, None, "verbatim DNA (.cursor/**, AGENTS.md, docs/spec, tools/git-hooks)"),
    "claude": TargetLayout("claude", ".claude/skills", ".claude/agents", "CLAUDE.md", "Claude Code: skills + subagents + CLAUDE.md (imports AGENTS.md)"),
    "agents": TargetLayout("agents", ".agents/skills", None, None, "cross-tool Agent Skills folder; AGENTS.md already shared"),
    "codex": TargetLayout("codex", ".agents/skills", None, None, "alias of `agents` (Codex reads AGENTS.md natively)"),
}
ALL_TARGETS: tuple[str, ...] = tuple(TARGET_LAYOUTS)


def parse_targets(raw: str | None) -> list[str]:
    if not raw:
        return ["cursor"]
    names: list[str] = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part == "all":
            names.extend(ALL_TARGETS)
            continue
        if part not in TARGET_LAYOUTS:
            raise ValueError(f"unknown DNA target {part!r}; known: {', '.join(ALL_TARGETS)} or all")
        names.append(part)
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen or ["cursor"]


def render_target(source: Path, target: str) -> FileMap:
    layout = TARGET_LAYOUTS[target]
    files = iter_dna_files(source)
    if target == "cursor":
        return {rel: _workspace_bytes(rel, path) for rel, path in files}
    out: FileMap = {}
    for rel, path in files:
        parts = rel.split("/")
        if layout.skills_dir and parts[:2] == [".cursor", "skills"] and len(parts) >= 4:
            out["/".join([layout.skills_dir, *parts[2:]])] = _workspace_bytes(rel, path)
        elif layout.agents_dir and parts[:2] == [".cursor", "agents"] and len(parts) == 3:
            text = strip_platform_only(path.read_text(encoding="utf-8"))
            out["/".join([layout.agents_dir, parts[2]])] = _strip_cursor_only_fields(text).encode("utf-8")
    if layout.instructions_file:
        out[layout.instructions_file] = render_instructions(source, layout).encode("utf-8")
    return out


def _strip_cursor_only_fields(text: str) -> str:
    """Drop front-matter keys other tools reject (keep name / description / model)."""
    match = _FM_RE.match(text)
    if not match:
        return text
    kept: list[str] = []
    for line in match.group(1).splitlines():
        key = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if key in {"name", "description", "model", "tools"} or line.startswith((" ", "\t", "-")):
            kept.append(line)
    return "---\n" + "\n".join(kept) + "\n---\n" + text[match.end():]


def render_instructions(source: Path, layout: TargetLayout) -> str:
    """Generated always-on instructions: import AGENTS.md, inline always-apply rules, list glob rules."""
    rules_dir = source / ".cursor" / "rules"
    always: list[tuple[str, str, str]] = []
    scoped: list[tuple[str, str, str]] = []
    for path in sorted(rules_dir.glob("*.mdc")) if rules_dir.is_dir() else []:
        if is_local_override(path.name):
            continue
        text = strip_platform_only(path.read_text(encoding="utf-8"))
        meta = _front_matter(text)
        body = _FM_RE.sub("", text, count=1).strip()
        entry = (path.stem, meta.get("description", ""), body if meta.get("alwaysapply") == "true" else meta.get("globs", ""))
        (always if meta.get("alwaysapply") == "true" else scoped).append(entry)
    lines = [
        f"<!-- GENERATED by `tuner-dna sync --target {layout.name}` from .cursor/rules — do not edit by hand -->",
        "# Project instructions",
        "",
        "@AGENTS.md",
        "",
        "The repository's stable world-view is `AGENTS.md` (plus `AGENTS.local.md` when present);",
        "the asset map is `INDEX.project.md`. Skills live under "
        f"`{layout.skills_dir or '.cursor/skills'}/<name>/SKILL.md`; read a skill before following it.",
        "",
        "## Always-on rules",
        "",
    ]
    for name, description, body in always:
        lines.append(f"### {name}")
        if description:
            lines.append(f"_{description}_")
        lines.append("")
        lines.append(body)
        lines.append("")
    lines.append("## Path-scoped rules (read the file when you touch matching paths)")
    lines.append("")
    lines.append("| rule | applies to | file |")
    lines.append("| --- | --- | --- |")
    for name, description, globs in scoped:
        lines.append(f"| `{name}` | `{globs}` | `.cursor/rules/{name}.mdc` — {description} |")
    lines.append("")
    return "\n".join(lines)


def _front_matter(text: str) -> dict[str, str]:
    match = _FM_RE.match(text)
    if not match:
        return {}
    out: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        out[key.strip().lower()] = value.strip().strip("\"'")
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class SyncResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    kept_local: list[str] = field(default_factory=list)
    unchanged: int = 0
    pruned: list[str] = field(default_factory=list)
    prune_kept: list[str] = field(default_factory=list)
    written: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"added={len(self.added)} updated={len(self.updated)} overwritten={len(self.overwritten)} "
            f"kept_local={len(self.kept_local)} unchanged={self.unchanged} "
            f"pruned={len(self.pruned)} prune_kept={len(self.prune_kept)}"
        )


def sync_file_map(
    dest: Path,
    files: FileMap,
    *,
    overwrite: bool,
    recorded: dict[str, str] | None = None,
    prune: bool = False,
    log: Callable[[str], None] = print,
) -> SyncResult:
    """Write ``files`` into ``dest``.

    ``recorded`` maps each path written by the previous sync to its hash. A file
    whose current hash still equals the recorded one was not edited locally, so
    it is refreshed without ``--overwrite``. Locally edited files are kept unless
    ``overwrite`` is set. With ``prune``, files written by the previous sync that
    the kit no longer ships are deleted when untouched, kept when edited.
    Local-override files (``*.local.*``, ``AGENTS.local.md``) are never touched.
    """
    recorded = recorded or {}
    result = SyncResult()
    for rel, data in sorted(files.items()):
        if is_local_override(rel):
            continue
        dst = dest / rel
        digest = sha256(data)
        if dst.is_file():
            current = dst.read_bytes()
            if current == data:
                result.unchanged += 1
                result.written[rel] = digest
                continue
            untouched = recorded.get(rel) == sha256(current)
            if not untouched and not overwrite:
                result.kept_local.append(rel)
                if rel in recorded:
                    result.written[rel] = recorded[rel]
                log(f"keep {rel} (edited locally; move edits to a *.local.* file, or pass --overwrite)")
                continue
            dst.write_bytes(data)
            (result.updated if untouched else result.overwritten).append(rel)
            log(f"{'update' if untouched else 'overwrite'} {rel}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            result.added.append(rel)
            log(f"add {rel}")
        result.written[rel] = digest
    if prune:
        for rel, old_digest in sorted(recorded.items()):
            if rel in files or is_local_override(rel):
                continue
            dst = dest / rel
            if not dst.is_file():
                continue
            if sha256(dst.read_bytes()) == old_digest:
                dst.unlink()
                _remove_empty_parents(dst.parent, dest)
                result.pruned.append(rel)
                log(f"prune {rel}")
            else:
                result.prune_kept.append(rel)
                result.written[rel] = old_digest
                log(f"keep {rel} (no longer shipped, but edited locally)")
    return result


def _remove_empty_parents(folder: Path, stop: Path) -> None:
    stop = stop.resolve()
    current = folder.resolve()
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def write_file_map(dest: Path, files: FileMap, *, overwrite: bool, log: Callable[[str], None] = print) -> tuple[int, int]:
    """Back-compat wrapper: returns (written, skipped)."""
    result = sync_file_map(dest, files, overwrite=overwrite, log=log)
    written = len(result.added) + len(result.updated) + len(result.overwritten)
    return written, result.unchanged + len(result.kept_local)


@dataclass
class Drift:
    missing: list[str] = field(default_factory=list)
    outdated: list[str] = field(default_factory=list)
    edited: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.missing or self.outdated or self.edited or self.removed)


def drift_file_map(dest: Path, files: FileMap, recorded: dict[str, str] | None = None) -> Drift:
    """Classify differences: missing, outdated (untouched since last sync), edited locally, removed upstream."""
    recorded = recorded or {}
    drift = Drift()
    for rel, data in sorted(files.items()):
        if is_local_override(rel):
            continue
        dst = dest / rel
        if not dst.is_file():
            drift.missing.append(rel)
            continue
        current = dst.read_bytes()
        if current == data:
            continue
        if recorded.get(rel) == sha256(current):
            drift.outdated.append(rel)
        else:
            drift.edited.append(rel)
    for rel in sorted(recorded):
        if rel not in files and (dest / rel).is_file() and not is_local_override(rel):
            drift.removed.append(rel)
    return drift


def diff_file_map(dest: Path, files: FileMap) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    changed: list[str] = []
    for rel, data in sorted(files.items()):
        dst = dest / rel
        if not dst.is_file():
            missing.append(rel)
        elif dst.read_bytes() != data:
            changed.append(rel)
    return missing, changed
