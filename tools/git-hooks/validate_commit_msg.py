#!/usr/bin/env python
"""Validate a commit message against docs/spec/commit-convention.md.

Two deterministic checks:

1. **Format**: first line is Conventional Commits ``type(scope): subject`` with
   ``type`` / ``scope`` from the allowed sets (scope may be comma/slash-separated
   for multi-layer changes; ``!`` marks a breaking change).
2. **Scope↔change consistency**: map ``git diff --cached --name-only`` paths to
   layers and assert the declared scope covers every recognized changed layer
   (``packages`` is the umbrella scope for api_objects/page_objects/action_words).

Merge/Revert commits are skipped. If staged files cannot be read, the format
check still runs but the consistency check is skipped (fail-open on git errors).

Exit code 0 = ok, 1 = rejected.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# Keep in sync with docs/spec/commit-convention.md
ALLOWED_TYPES = {
    "feat", "fix", "refactor", "docs", "test", "perf",
    "chore", "build", "ci", "style", "revert",
}

ALLOWED_SCOPES = {
    "knowledge", "assets", "apps", "packages", "api_objects", "page_objects", "action_words",
    "tests", "docs", "rules", "skills", "agents", "hooks", "init_repo", "index", "work",
    # in-repo dogfood workspace (scaffolded from this platform repo)
    "dogfood",
    # fine-grained package aliases also accepted
    "db", "logging", "recorder", "config", "api_test", "excel",
}

# Tests can inject the staged file list instead of calling git.
STAGED_ENV = "TUNER_COMMIT_STAGED"

# packages umbrella covers these sub-layers
PACKAGES_UMBRELLA = {"api_objects", "page_objects", "action_words", "packages",
                     "db", "logging", "api_test", "excel", "config"}

HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$"
)


def _staged_files() -> list[str]:
    injected = os.environ.get(STAGED_ENV)
    if injected is not None:
        return [line.strip() for line in injected.splitlines() if line.strip()]
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            capture_output=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    # -z: NUL-separated and unquoted, so non-ASCII paths arrive as real UTF-8 names.
    return [p for p in out.stdout.decode("utf-8", errors="replace").split("\0") if p.strip()]


def _path_to_layer(path: str) -> str | None:
    """Map a repo path to a canonical scope layer, or None if unrecognized."""
    p = path.replace("\\", "/")
    if p.startswith("dogfood/"):
        return "dogfood"
    if p.startswith("packages/api_objects/"):
        return "api_objects"
    if p.startswith("packages/page_objects/"):
        return "page_objects"
    if p.startswith("packages/action_words/"):
        return "action_words"
    if p.startswith("packages/"):
        return "packages"
    if p.startswith("tuner_testkit/apps/init_repo/"):
        return "init_repo"
    if p.startswith("tuner_testkit/apps/"):
        return "apps"
    if p.startswith("tuner_testkit/"):
        return "packages"
    if p.startswith("apps/"):
        return "apps"
    if p.startswith("work/"):
        return "work"
    if p.startswith("knowledge/"):
        return "knowledge"
    if p.startswith("assets/"):
        return "assets"
    if p.startswith("tests/"):
        return "tests"
    if p.startswith("docs/"):
        return "docs"
    if p.startswith(".cursor/rules/"):
        return "rules"
    if p.startswith(".cursor/skills/"):
        return "skills"
    if p.startswith(".cursor/agents/"):
        return "agents"
    if p.startswith(".cursor/hooks") or p.startswith("tools/git-hooks/"):
        return "hooks"
    if p in {"INDEX.md", "INDEX.project.md", ".cursor/REGISTRY.md"}:
        return "index"
    # root config / meta files carry no required layer scope
    return None


def _covers(declared: set[str], layer: str) -> bool:
    if layer in declared:
        return True
    # packages is the umbrella for its sub-layers
    if "packages" in declared and layer in PACKAGES_UMBRELLA:
        return True
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("commit-msg: missing message file argument", file=sys.stderr)
        return 1

    try:
        with open(argv[1], encoding="utf-8-sig") as fh:  # tolerate a Windows editor BOM
            raw = fh.read()
    except OSError as exc:
        print(f"commit-msg: cannot read message file: {exc}", file=sys.stderr)
        return 1

    lines = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")]
    header = next((ln for ln in lines if ln.strip()), "")

    if header.startswith(("Merge", "Revert", "fixup!", "squash!")):
        return 0

    match = HEADER_RE.match(header)
    if not match:
        _reject(
            "首行不符合 Conventional Commits 格式 `type(scope): subject`。",
            header,
        )
        return 1

    commit_type = match.group("type")
    if commit_type not in ALLOWED_TYPES:
        _reject(
            f"type `{commit_type}` 不在允许集合内：{sorted(ALLOWED_TYPES)}",
            header,
        )
        return 1

    scope_raw = match.group("scope") or ""
    declared = {
        s.strip() for s in re.split(r"[,/]", scope_raw) if s.strip()
    }
    unknown = declared - ALLOWED_SCOPES
    if unknown:
        _reject(
            f"scope {sorted(unknown)} 不在允许集合内：{sorted(ALLOWED_SCOPES)}",
            header,
        )
        return 1

    # Consistency check (best-effort; skipped when no staged files readable)
    files = _staged_files()
    changed_layers = {
        layer for f in files if (layer := _path_to_layer(f)) is not None
    }
    if changed_layers:
        missing = {ly for ly in changed_layers if not _covers(declared, ly)}
        if missing:
            _reject(
                "声明的 scope 未覆盖实际改动的层：缺 "
                f"{sorted(missing)}；已声明 {sorted(declared) or '(无)'}。\n"
                "  请在 scope 中加入这些层（多层用逗号分隔），或用上位 scope `packages`。",
                header,
            )
            return 1

    return 0


def _reject(reason: str, header: str) -> None:
    print("[x] commit-msg 校验未通过：", file=sys.stderr)
    print(f"  {reason}", file=sys.stderr)
    print(f"  首行：{header!r}", file=sys.stderr)
    print("  规范见 docs/spec/commit-convention.md", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
