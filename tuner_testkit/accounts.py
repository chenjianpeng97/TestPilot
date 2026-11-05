"""Test accounts: the single source is ``data/sut-accounts.local.yaml`` (gitignored).

Format (``docs/spec/data-syntax.md``)::

    accounts:
      - id: qa-admin
        role: admin
        email: qa@acme.example      # or ``username``
        password: "..."

Runtime code that needs a login (action words, API / page login) resolves it here
after the explicit arguments and the ``TEST_USERNAME`` / ``TEST_PASSWORD`` override
(CI injection). Reading uses PyYAML when installed, otherwise a small parser that
handles the flat ``accounts`` list above.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

ACCOUNTS_REL = Path("data") / "sut-accounts.local.yaml"
ACCOUNT_ENV = "TUNER_ACCOUNT"  # optional: pick an account id when the file lists several


def accounts_path(root: Path | None = None) -> Path:
    if root is None:
        from tuner_testkit.project import project_root

        root = project_root()
    return Path(root) / ACCOUNTS_REL


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if text.startswith(("'", '"')) and text.endswith(text[0]) and len(text) >= 2:
        return text[1:-1]
    text = re.sub(r"\s+#.*$", "", text).strip()
    if text.startswith("[") and text.endswith("]"):
        return [part.strip().strip("'\"") for part in text[1:-1].split(",") if part.strip()]
    return text


def _parse_minimal(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_accounts = False
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\S", line):
            in_accounts = line.startswith("accounts:")
            current = None
            continue
        if not in_accounts:
            continue
        item = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
        if item:
            current = {item.group(1): _scalar(item.group(2))}
            rows.append(current)
            continue
        field = re.match(r"^\s+(\w+):\s*(.*)$", line)
        if field and current is not None:
            current[field.group(1)] = _scalar(field.group(2))
    return rows


def load_accounts(root: Path | None = None) -> list[dict[str, Any]]:
    path = accounts_path(root)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return _parse_minimal(text)
    data = yaml.safe_load(text) or {}
    rows = data.get("accounts") if isinstance(data, dict) else None
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def resolve_account(
    root: Path | None = None, *, account_id: str | None = None, role: str | None = None
) -> dict[str, str]:
    """``{"id", "username", "password"}`` of the chosen account, or ``{}`` when none matches.

    Selection: *account_id* > ``TUNER_ACCOUNT`` env > first account with *role* > first account.
    """
    rows = load_accounts(root)
    wanted = account_id or os.environ.get(ACCOUNT_ENV) or ""
    pick = None
    if wanted:
        pick = next((r for r in rows if str(r.get("id")) == wanted), None)
    elif role:
        pick = next((r for r in rows if str(r.get("role")) == role), None)
    elif rows:
        pick = rows[0]
    if not pick:
        return {}
    username = str(pick.get("username") or pick.get("email") or "")
    password = str(pick.get("password") or "")
    if not username or not password or password == "replace-me":
        return {}
    return {"id": str(pick.get("id") or ""), "username": username, "password": password}
