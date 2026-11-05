"""Release manifest hashes must not depend on the checkout's line endings."""
from __future__ import annotations

from pathlib import Path

from tuner_testkit.apps.init_repo import manifest as mf


def _tree(root: Path, eol: bytes) -> Path:
    rules = root / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "a.mdc").write_bytes(b"line one" + eol + b"line two" + eol)
    (root / "AGENTS.md").write_bytes(b"# AGENTS" + eol)
    return root


def test_crlf_and_lf_checkouts_hash_the_same(tmp_path: Path) -> None:
    lf = mf.compute_hashes(_tree(tmp_path / "lf", b"\n"))
    crlf = mf.compute_hashes(_tree(tmp_path / "crlf", b"\r\n"))
    assert lf and lf == crlf


def test_binary_bytes_are_hashed_as_is(tmp_path: Path) -> None:
    root = _tree(tmp_path / "bin", b"\n")
    hooks = root / "tools" / "git-hooks"
    hooks.mkdir(parents=True)
    (hooks / "blob.bin").write_bytes(b"\0\r\n")
    before = mf.compute_hashes(root)["tools/git-hooks/blob.bin"]
    (hooks / "blob.bin").write_bytes(b"\0\n")
    assert mf.compute_hashes(root)["tools/git-hooks/blob.bin"] != before
