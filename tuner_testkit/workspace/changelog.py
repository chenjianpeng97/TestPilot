"""Object-level changelogs: every maintained library keeps its own trail in git.

``artifacts/inbox/`` is a local session log and is not committed. Traceability
comes from the maintained objects themselves (``docs/spec/metadata-conventions.md`` §4):

* a unit file (testcase, requirement, defect, wiki page …) bumps its front-matter ``version``;
* the library root keeps an append-only ``CHANGELOG.md`` (``knowledge/wiki/log.md`` for the wiki).

``append`` writes one line; ``check`` verifies a change set (staged files or a
commit range) against those two rules. Both are deterministic.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tuner_testkit.apps._shared.changelog import MAINTAINED_HEADER, append_entry
from tuner_testkit.catalog.front_matter import parse_front_matter

SKIP_ENV = "TUNER_SKIP_CHANGELOG_CHECK"
_INFRA_FILES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "conftest.py",
        "models.py",
        "registry.py",
        "auth.py",
        "session.py",
        "pages.py",
        ".gitkeep",
    }
)
_NON_UNIT_MD = frozenset({"index.md", "log.md", "changelog.md"})


@dataclass(frozen=True)
class Area:
    name: str
    root: str
    changelog: str
    skill: str
    suffixes: tuple[str, ...] = (".md",)
    versioned: bool = True

    def owns(self, rel: str) -> bool:
        if not rel.startswith(self.root + "/"):
            return False
        path = PurePosixPath(rel)
        if rel == self.changelog or path.name in _INFRA_FILES:
            return False
        inner = PurePosixPath(rel[len(self.root) + 1 :]).parts[:-1]
        if any(part.startswith("_") or part in {"tests", "recording", "__pycache__"} for part in inner):
            return False
        return True

    def is_unit(self, rel: str) -> bool:
        path = PurePosixPath(rel)
        return path.suffix in self.suffixes and path.name.lower() not in _NON_UNIT_MD


AREAS: dict[str, Area] = {
    area.name: area
    for area in (
        Area("testcases", "assets/testcases", "assets/testcases/CHANGELOG.md", "maintain-testcases"),
        Area("testsheet", "assets/testsheet", "assets/testsheet/CHANGELOG.md", "maintain-testsheet / execute-testsheet", versioned=False),
        Area("testdesign", "assets/testdesign", "assets/testdesign/CHANGELOG.md", "derive-test-design"),
        Area("requirements", "knowledge/requirements", "knowledge/requirements/CHANGELOG.md", "maintain-wiki"),
        Area("defects", "knowledge/defects", "knowledge/defects/CHANGELOG.md", "maintain-defectlib"),
        Area("wiki", "knowledge/wiki", "knowledge/wiki/log.md", "maintain-wiki"),
        Area("ddl", "knowledge/ddl", "knowledge/ddl/CHANGELOG.md", "dump-ddl", (".sql",), False),
        Area("api_objects", "packages/api_objects", "packages/api_objects/CHANGELOG.md", "freeze-api-objects", (".py",), False),
        Area("page_objects", "packages/page_objects", "packages/page_objects/CHANGELOG.md", "maintain-page-objects", (".py",), False),
        Area("action_words", "packages/action_words", "packages/action_words/CHANGELOG.md", "create-action-word", (".py",), False),
    )
}


def area_for(rel: str) -> Area | None:
    for area in AREAS.values():
        if area.owns(rel):
            return area
    return None


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------
def append(
    root: Path,
    *,
    area: str,
    skill: str,
    action: str,
    items: list[str],
    version: str | None = None,
    reason: str | None = None,
    author: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if area not in AREAS:
        raise KeyError(f"unknown area {area!r}; known: {', '.join(sorted(AREAS))}")
    spec = AREAS[area]
    if author is None:
        from tuner_testkit.catalog.scan import git_config_value

        author = git_config_value(root, "user.email")
    path = root / spec.changelog
    line = append_entry(
        path,
        tool=skill,
        action=action,
        items=items,
        header=MAINTAINED_HEADER,
        version=version,
        reason=reason,
        author=author,
        **(extra or {}),
    )
    return {"area": area, "changelog": spec.changelog, "line": line.rstrip("\n")}


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def workspace_roots(repo: Path) -> list[Path]:
    """Workspace roots inside a git repo: the repo itself, or (platform repo) its nested workspaces."""
    if (repo / "tuner_testkit" / "project.py").is_file():
        return sorted(child for child in repo.iterdir() if child.is_dir() and (child / "INDEX.project.md").is_file())
    return [repo]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, timeout=30, check=False)


def _changes(repo: Path, base: str | None) -> list[tuple[str, str]]:
    """(status letter, repo-relative path) for staged changes, or ``base..HEAD``."""
    args = ["diff", "--name-status", "-z", "--find-renames"]
    args += [f"{base}...HEAD"] if base else ["--cached"]
    out = _git(repo, *args)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip() or "git diff failed")
    fields = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        if status.startswith(("R", "C")):
            changes.append((status[0], fields[i + 2]))
            i += 3
        else:
            changes.append((status[0], fields[i + 1]))
            i += 2
    return changes


def _blob(repo: Path, ref: str, rel: str) -> str | None:
    out = _git(repo, "show", f"{ref}:{rel}")
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def _version(text: str | None) -> str | None:
    if text is None:
        return None
    value = parse_front_matter(text).get("version")
    return None if value is None else str(value).strip()


def check(repo: Path, *, base: str | None = None) -> dict[str, Any]:
    """Verify changes in maintained areas carry a changelog line and a version bump."""
    if os.environ.get(SKIP_ENV):
        return {"ok": True, "skipped": True, "reason": f"{SKIP_ENV} is set", "errors": [], "warnings": [], "areas": {}}
    changes = _changes(repo, base)
    changed_paths = {path for _, path in changes}
    old_ref = base or "HEAD"
    new_ref = "HEAD" if base else ""
    errors: list[str] = []
    warnings: list[str] = []
    areas: dict[str, dict[str, Any]] = {}
    for ws in workspace_roots(repo):
        prefix = "" if ws == repo else ws.relative_to(repo).as_posix() + "/"
        for status, path in changes:
            if not path.startswith(prefix):
                continue
            rel = path[len(prefix) :]
            area = area_for(rel)
            if area is None:
                continue
            key = prefix + area.name
            entry = areas.setdefault(
                key,
                {"area": area.name, "changelog": prefix + area.changelog, "skill": area.skill, "files": 0},
            )
            entry["files"] += 1
            if status == "D" or not area.versioned or not area.is_unit(rel):
                continue
            new_text = _blob(repo, new_ref, path)
            new_version = _version(new_text)
            if status == "A":
                if new_version is None:
                    warnings.append(f"{path}: new {area.name} file has no front-matter `version`")
                continue
            old_version = _version(_blob(repo, old_ref, path))
            if old_version is not None and new_version == old_version:
                errors.append(f"{path}: changed but `version` is still {old_version}; bump it ({area.skill})")
    for _key, entry in sorted(areas.items()):
        entry["changelog_changed"] = entry["changelog"] in changed_paths
        if not entry["changelog_changed"]:
            errors.append(
                f"{entry['changelog']}: {entry['files']} file(s) changed in {entry['area']} without a changelog line "
                f"(tuner-workspace changelog append --area {entry['area']} …; skill {entry['skill']})"
            )
    return {
        "ok": not errors,
        "mode": f"{base}...HEAD" if base else "staged",
        "errors": errors,
        "warnings": warnings,
        "areas": areas,
    }
