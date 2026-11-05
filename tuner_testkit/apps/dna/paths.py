"""DNA overlay paths — Cursor rules/skills plus git hooks and specs."""

from __future__ import annotations

# Relative to the template source root (or a bundled payload that mirrors it).
DNA_PATHS: tuple[str, ...] = (
    ".cursor/rules",
    ".cursor/skills",
    ".cursor/agents",
    ".cursor/hooks",
    ".cursor/hooks.json",
    "docs/spec",
    "docs/changelog",
    "tools/git-hooks",
    "AGENTS.md",
)

# Files and folders that only make sense in the platform repo. They stay in the
# source tree but are never hashed into the release manifest, bundled or synced.
PLATFORM_ONLY_PATHS: tuple[str, ...] = (
    ".cursor/skills/release-template",
    "docs/changelog/FRAMEWORK.md",
)

# Text blocks between these markers are platform-only and are stripped when
# DNA is rendered into a workspace.
PLATFORM_ONLY_BEGIN = "<!-- platform-only:begin -->"
PLATFORM_ONLY_END = "<!-- platform-only:end -->"

# Local override layer: workspace files that DNA never ships and sync/prune
# never touch. Matched against the relative posix path.
LOCAL_OVERRIDE_MARKERS: tuple[str, ...] = (".local.",)
LOCAL_OVERRIDE_NAMES: frozenset[str] = frozenset({"AGENTS.local.md"})

# Written into the workspace by ``tuner-dna sync``: kit version plus the hash of
# every file it wrote, so later syncs can tell untouched files from local edits.
SYNC_RECORD = ".tuner-dna.json"
LEGACY_VERSION_MARKER = ".tuner-dna-version"


def is_platform_only(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(rel == p or rel.startswith(p + "/") for p in PLATFORM_ONLY_PATHS)


def is_local_override(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    name = rel.rsplit("/", 1)[-1]
    return name in LOCAL_OVERRIDE_NAMES or any(marker in name for marker in LOCAL_OVERRIDE_MARKERS)
