"""Workspace view of DNA: platform-only paths/blocks are dropped; sync records hashes and prunes safely."""
from __future__ import annotations

import json
from pathlib import Path

from tuner_testkit.apps.dna import targets as t
from tuner_testkit.apps.dna.cli import main, read_sync_record
from tuner_testkit.apps.dna.paths import SYNC_RECORD, is_local_override, is_platform_only

REPO_ROOT = Path(__file__).resolve().parents[4]


def _fake_source(root: Path, *, rule_text: str = "rule v1\n", extra_skill: bool = True) -> Path:
    (root / ".cursor" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".cursor" / "rules" / "a.mdc").write_text(rule_text, encoding="utf-8")
    (root / ".cursor" / "skills" / "keep").mkdir(parents=True, exist_ok=True)
    (root / ".cursor" / "skills" / "keep" / "SKILL.md").write_text("keep\n", encoding="utf-8")
    if extra_skill:
        (root / ".cursor" / "skills" / "gone").mkdir(parents=True, exist_ok=True)
        (root / ".cursor" / "skills" / "gone" / "SKILL.md").write_text("gone\n", encoding="utf-8")
    elif (root / ".cursor" / "skills" / "gone").exists():
        (root / ".cursor" / "skills" / "gone" / "SKILL.md").unlink()
        (root / ".cursor" / "skills" / "gone").rmdir()
    (root / ".cursor" / "skills" / "release-template").mkdir(parents=True, exist_ok=True)
    (root / ".cursor" / "skills" / "release-template" / "SKILL.md").write_text("platform\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# AGENTS\nshared\n<!-- platform-only:begin -->\n本仓不是 workspace\n<!-- platform-only:end -->\ntail\n",
        encoding="utf-8",
    )
    return root


def test_path_helpers() -> None:
    assert is_platform_only(".cursor/skills/release-template/SKILL.md")
    assert is_platform_only("docs/changelog/FRAMEWORK.md")
    assert not is_platform_only("docs/changelog/TEMPLATE-7.0.0.md")
    assert is_local_override(".cursor/rules/team.local.mdc")
    assert is_local_override("AGENTS.local.md")
    assert not is_local_override(".cursor/rules/team.mdc")


def test_strip_platform_only_blocks() -> None:
    text = "a\n<!-- platform-only:begin -->\nsecret platform\n<!-- platform-only:end -->\nb\n"
    assert t.strip_platform_only(text) == "a\nb\n"
    assert t.strip_platform_only("no markers\n") == "no markers\n"


def test_real_dna_renders_workspace_view() -> None:
    files = t.render_target(REPO_ROOT, "cursor")
    assert not any(rel.startswith(".cursor/skills/release-template/") for rel in files)
    assert "docs/changelog/FRAMEWORK.md" not in files
    assert any(rel.startswith("docs/changelog/TEMPLATE-") for rel in files)
    agents = files["AGENTS.md"].decode("utf-8")
    assert "本仓不是 workspace" not in agents
    assert "platform-only" not in agents
    assert "端口与自定义 apps" in agents
    hygiene = files[".cursor/rules/index-hygiene.mdc"].decode("utf-8")
    assert "INDEX.project.md" in hygiene and "平台仓另有根" not in hygiene
    claude = t.render_target(REPO_ROOT, "claude")["CLAUDE.md"].decode("utf-8")
    assert "平台仓另有根" not in claude


def test_sync_records_hashes_updates_untouched_and_keeps_edits(tmp_path: Path, monkeypatch) -> None:
    src = _fake_source(tmp_path / "src")
    dest = tmp_path / "ws"
    dest.mkdir()
    monkeypatch.setenv("TUNER_DNA_ROOT", str(src))
    assert main(["sync", "--target", str(dest)]) == 0
    record = read_sync_record(dest)
    assert ".cursor/rules/a.mdc" in record["targets"]["cursor"]
    assert not (dest / ".cursor" / "skills" / "release-template").exists()
    assert "本仓不是 workspace" not in (dest / "AGENTS.md").read_text(encoding="utf-8")

    (dest / ".cursor" / "rules" / "team.local.mdc").write_text("local\n", encoding="utf-8")
    (dest / ".cursor" / "skills" / "keep" / "SKILL.md").write_text("edited locally\n", encoding="utf-8")
    _fake_source(src, rule_text="rule v2\n", extra_skill=False)

    assert main(["check", "--target", str(dest), "--json"]) == 1
    assert main(["sync", "--target", str(dest), "--prune"]) == 0
    assert (dest / ".cursor" / "rules" / "a.mdc").read_text(encoding="utf-8") == "rule v2\n"  # untouched → updated
    assert (dest / ".cursor" / "skills" / "keep" / "SKILL.md").read_text(encoding="utf-8") == "edited locally\n"
    assert not (dest / ".cursor" / "skills" / "gone").exists()  # removed upstream, untouched → pruned
    assert (dest / ".cursor" / "rules" / "team.local.mdc").read_text(encoding="utf-8") == "local\n"

    assert main(["sync", "--target", str(dest), "--overwrite"]) == 0
    assert (dest / ".cursor" / "skills" / "keep" / "SKILL.md").read_text(encoding="utf-8") == "keep\n"
    assert main(["check", "--target", str(dest)]) == 0
    data = json.loads((dest / SYNC_RECORD).read_text(encoding="utf-8"))
    assert data["kit_version"]


def _to_crlf(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def test_crlf_source_renders_lf(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    _to_crlf(src / ".cursor" / "rules" / "a.mdc")
    _to_crlf(src / "AGENTS.md")
    files = t.render_target(src, "cursor")
    assert files[".cursor/rules/a.mdc"] == b"rule v1\n"
    assert b"\r\n" not in files["AGENTS.md"]


def test_crlf_checkout_is_not_a_local_edit(tmp_path: Path, monkeypatch) -> None:
    src = _fake_source(tmp_path / "src")
    dest = tmp_path / "ws"
    dest.mkdir()
    monkeypatch.setenv("TUNER_DNA_ROOT", str(src))
    assert main(["sync", "--target", str(dest)]) == 0
    rule = dest / ".cursor" / "rules" / "a.mdc"
    _to_crlf(rule)  # what a Windows clone with core.autocrlf=true checks out
    assert main(["check", "--target", str(dest)]) == 0

    _fake_source(src, rule_text="rule v2\n")
    drift = t.drift_file_map(dest, t.render_target(src, "cursor"), read_sync_record(dest)["targets"]["cursor"])
    assert drift.outdated == [".cursor/rules/a.mdc"] and not drift.edited
    assert main(["sync", "--target", str(dest)]) == 0
    assert rule.read_bytes() == b"rule v2\n"


def test_crlf_record_from_older_kit_counts_as_untouched(tmp_path: Path) -> None:
    dest = tmp_path / "ws"
    rule = dest / ".cursor" / "rules" / "a.mdc"
    rule.parent.mkdir(parents=True)
    rule.write_bytes(b"rule v1\n")
    recorded = {".cursor/rules/a.mdc": t.sha256(b"rule v1\r\n")}
    result = t.sync_file_map(dest, {".cursor/rules/a.mdc": b"rule v2\n"}, overwrite=False, recorded=recorded, log=lambda _m: None)
    assert result.updated == [".cursor/rules/a.mdc"]
    assert rule.read_bytes() == b"rule v2\n"


def test_prune_keeps_locally_edited_removed_file(tmp_path: Path, monkeypatch) -> None:
    src = _fake_source(tmp_path / "src")
    dest = tmp_path / "ws"
    dest.mkdir()
    monkeypatch.setenv("TUNER_DNA_ROOT", str(src))
    assert main(["sync", "--target", str(dest)]) == 0
    (dest / ".cursor" / "skills" / "gone" / "SKILL.md").write_text("mine\n", encoding="utf-8")
    _fake_source(src, extra_skill=False)
    assert main(["sync", "--target", str(dest), "--prune"]) == 0
    assert (dest / ".cursor" / "skills" / "gone" / "SKILL.md").read_text(encoding="utf-8") == "mine\n"
