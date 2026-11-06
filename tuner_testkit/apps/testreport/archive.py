"""Archive a finished testsheet round: assets/testsheet/<round>/ -> assets/testsheet/archived/<round>/."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from tuner_testkit.workspace.changelog import append as changelog_append

from .stats import build

ARCHIVED = "archived"


def testsheet_root(root: Path) -> Path:
    return root / "assets" / "testsheet"


def archive_sheet(
    root: Path, round_name: str, *, dry_run: bool = False, author: str | None = None
) -> dict[str, Any]:
    """Move a round into archived/ and leave one changelog line.

    Archiving is the user's decision, so nothing blocks it. ``warnings`` lists what the user
    should hear before confirming (cases still without a result, blocked cases, parse errors,
    open defects). ``dry_run`` only reports them and moves nothing.
    """
    name = round_name.replace("\\", "/").strip("/")
    if not name or "/" in name or name in {".", "..", ARCHIVED}:
        raise ValueError(f"round must be a folder name under assets/testsheet/: {round_name}")
    source = testsheet_root(root) / name
    if not (source / "testsheet.md").is_file():
        if (testsheet_root(root) / ARCHIVED / name / "testsheet.md").is_file():
            raise ValueError(f"{name} is already archived")
        raise FileNotFoundError(source / "testsheet.md")
    data = build([source], root=root)
    warnings = _warnings(data)
    dest = testsheet_root(root) / ARCHIVED / name
    if dest.exists():
        raise ValueError(f"already exists: {dest.relative_to(root).as_posix()}")
    if dry_run:
        return {"round": name, "path": dest.relative_to(root).as_posix(), "rows": data["rows"], "warnings": warnings, "moved": False}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    rel = dest.relative_to(root).as_posix()
    changelog_append(
        root,
        area="testsheet",
        skill="maintain-testsheet",
        action="archive",
        items=[rel],
        reason="archived by user" + (f"; {len(warnings)} warning(s): " + "; ".join(warnings) if warnings else ""),
        author=author,
    )
    return {"round": name, "path": rel, "rows": data["rows"], "warnings": warnings, "moved": True}


def _warnings(data: dict[str, Any]) -> list[str]:
    rows = data["rows"]
    out: list[str] = []
    if rows.get("待执行"):
        out.append(f"{rows['待执行']} 条用例还没有结果（待执行）")
    if rows.get("阻塞"):
        out.append(f"{rows['阻塞']} 条用例是阻塞")
    if data["errors"]:
        out.append(f"stats --check 还有 {data['errors']} 个 error")
    return out
