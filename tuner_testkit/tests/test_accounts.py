from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.accounts import load_accounts, resolve_account

SAMPLE = """\
# comment
sut: acme
accounts:
  - id: qa-admin
    role: admin
    permissions: ["user:manage", "order:approve"]
    email: qa@acme.example
    password: "real-pass"   # secret-scan: allow
  - id: qa-viewer
    role: viewer
    username: viewer
    password: v-pass
workspace:
  slug: demo
"""


def _write(tmp_path: Path, text: str = SAMPLE) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "sut-accounts.local.yaml").write_text(text, encoding="utf-8")


def test_missing_file_gives_no_account(tmp_path: Path) -> None:
    assert load_accounts(tmp_path) == []
    assert resolve_account(tmp_path) == {}


def test_first_account_is_default(tmp_path: Path) -> None:
    _write(tmp_path)
    assert [a["id"] for a in load_accounts(tmp_path)] == ["qa-admin", "qa-viewer"]
    got = resolve_account(tmp_path)
    assert got == {"id": "qa-admin", "username": "qa@acme.example", "password": "real-pass"}


def test_pick_by_id_or_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path)
    monkeypatch.delenv("TUNER_ACCOUNT", raising=False)
    assert resolve_account(tmp_path, account_id="qa-viewer")["username"] == "viewer"
    assert resolve_account(tmp_path, role="viewer")["id"] == "qa-viewer"
    monkeypatch.setenv("TUNER_ACCOUNT", "qa-viewer")
    assert resolve_account(tmp_path)["id"] == "qa-viewer"


def test_placeholder_password_is_not_a_credential(tmp_path: Path) -> None:
    _write(tmp_path, "accounts:\n  - id: a\n    email: a@x\n    password: replace-me\n")
    assert resolve_account(tmp_path) == {}
