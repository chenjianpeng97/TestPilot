"""Append-only changelog for auto-generated asset areas.

Tools that (re)generate assets — ``apps/dump_ddl`` (DDL), ``apps.recorder``
(合录 page+api), ``apps.api_recorder`` (API objects via proxy), ``apps.page_recorder`` (page objects only), project-specific generators — append **one line per run** to the
changelog of the area they write into. ``maintain-index`` then updates
``INDEX.md`` by reading only the **tail delta** of these changelogs, instead of
re-reading full asset bodies (e.g. every ``assets/ddl/*.sql``). That keeps index
maintenance cheap (token-wise) and deterministic.

Design goals:

- **No third-party deps** (stdlib only), mirroring ``tuner_testkit.logging``.
- **Append-only, line-oriented, greppable**: one ISO-timestamped line per run.
- **Idempotent header**: the file is created with a stable header on first use.

Typical use from a tool::

    from tuner_testkit.apps._shared.changelog import append_entry

    append_entry(
        REPO_ROOT / "knowledge" / "ddl" / "CHANGELOG.md",
        tool="dump_ddl",
        action="dump-ddl",
        items=["invoice", "sys_user"],
        datasource="main",
    )
"""
from __future__ import annotations

import datetime as _dt
import pathlib
from collections.abc import Iterable
from typing import Any

_HEADER = (
    "# CHANGELOG — auto-generated asset area\n"
    "\n"
    "> Append-only, one line per generator run. `maintain-index` reads the tail\n"
    "> delta to update `INDEX.md` without re-reading full asset bodies.\n"
    "> Format: `- <iso-ts> | <tool> | <action> | items=a,b | key=value ...`\n"
    "\n"
)


MAINTAINED_HEADER = (
    "# CHANGELOG — maintained object library\n"
    "\n"
    "> Append-only, one line per maintenance session (skill or tool), written by\n"
    "> `tuner-workspace changelog append`. Committed with the change it describes.\n"
    "> Format: `- <iso-ts> | <skill> | <action> | items=a,b | version=x->y | reason=… | author=…`\n"
    "\n"
)


def _clean(value: Any) -> str:
    """Keep one line greppable: no pipes or newlines inside a field."""
    return " ".join(str(value).replace("|", "/").split())


def append_entry(
    changelog_path: str | pathlib.Path,
    *,
    tool: str,
    action: str,
    items: Iterable[Any] | None = None,
    header: str | None = None,
    **fields: Any,
) -> str:
    """Append one changelog line and return it.

    - ``changelog_path``: path to the area's ``CHANGELOG.md`` (created if absent).
    - ``tool``: the generator or skill name (e.g. ``"dump_ddl"``, ``"maintain-testcases"``).
    - ``action``: short verb for what happened (e.g. ``"dump-ddl"``, ``"update"``).
    - ``items``: the concrete artifacts touched (tables, routes, case IDs, ...).
    - ``header``: header written when the file is created (default: auto-area header).
    - ``fields``: extra key=value context (datasource, count, version, reason, ...).
    """
    path = pathlib.Path(changelog_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(header or _HEADER, encoding="utf-8", newline="\n")

    ts = _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    parts = [ts, _clean(tool), _clean(action)]
    if items is not None:
        item_list = [_clean(i) for i in items]
        parts.append("items=" + ",".join(item_list) if item_list else "items=")
    for key, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={_clean(value)}")

    line = "- " + " | ".join(parts) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
    return line
