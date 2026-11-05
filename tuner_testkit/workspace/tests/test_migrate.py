"""tuner-workspace migrate knowledge: pre-7.0 assets/ knowledge moves to knowledge/."""
from __future__ import annotations

from pathlib import Path

from tuner_testkit.workspace import migrate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _legacy(root: Path) -> None:
    _write(root / "assets" / "ddl" / "main" / "orders.sql", "create table orders (id int);\n")
    _write(root / "assets" / "CHANGELOG.md", "# CHANGELOG\n\n- 2026-01-01 | dump_ddl | dump-ddl | items=orders\n")
    _write(root / "assets" / "usecases" / "order" / "create.md", "见 assets/domain-notes/order/rules.md\n")
    _write(root / "assets" / "domain-notes" / "order" / "rules.md", "字段见 `assets/ddl/main/orders.sql`\n")
    _write(root / "assets" / "domain-notes" / "testreport" / "acme.md", "# 画像\n")
    _write(root / "assets" / "testcases" / "README.md", "依据 assets/usecases/order/create.md\n")
    _write(root / "INDEX.project.md", "<!-- auto:begin:ddl -->\n<!-- auto:end:ddl -->\n<!-- auto:begin:apps -->\n<!-- auto:end:apps -->\n")
    _write(root / ".cursor" / "rules" / "x.mdc", "assets/ddl stays: DNA is refreshed by tuner-dna\n")
    _write(root / "config" / "env_local.py", "# assets/ddl secret file untouched\n")


def test_rewrite_refs_boundaries() -> None:
    text, n = migrate.rewrite_refs("a assets/ddl/main x `assets/domain-notes/testreport/a.md` myassets/ddl assets/design")
    assert n == 3
    assert "knowledge/ddl/main" in text and "assets/testreport/profiles/a.md" in text
    assert "myassets/ddl" in text and text.endswith("knowledge/wiki/design")


def test_plan_is_dry_run(tmp_path: Path) -> None:
    _legacy(tmp_path)
    plan = migrate.plan(tmp_path)
    assert plan["needed"] and not plan["conflicts"]
    assert (tmp_path / "assets" / "ddl" / "main" / "orders.sql").is_file()  # nothing moved yet
    targets = {m["to"] for m in plan["moves"]}
    assert "knowledge/ddl/main/orders.sql" in targets
    assert "assets/testreport/profiles/acme.md" in targets
    assert "knowledge/wiki/domain-notes/order/rules.md" in targets
    rewritten = {r["path"] for r in plan["rewrites"]}
    assert "assets/testcases/README.md" in rewritten
    assert ".cursor/rules/x.mdc" not in rewritten and "config/env_local.py" not in rewritten
    assert plan["index_zones"] == ["knowledge", "ports"]


def test_apply_moves_rewrites_and_is_idempotent(tmp_path: Path) -> None:
    _legacy(tmp_path)
    result = migrate.apply(tmp_path)
    assert result["applied"] is True
    assert (tmp_path / "knowledge" / "ddl" / "main" / "orders.sql").is_file()
    assert (tmp_path / "assets" / "testreport" / "profiles" / "acme.md").is_file()
    assert not (tmp_path / "assets" / "ddl").exists() and not (tmp_path / "assets" / "domain-notes").exists()
    rules = (tmp_path / "knowledge" / "wiki" / "domain-notes" / "order" / "rules.md").read_text(encoding="utf-8")
    assert "knowledge/ddl/main/orders.sql" in rules
    assert "knowledge/wiki/usecases/order/create.md" in (tmp_path / "assets" / "testcases" / "README.md").read_text(encoding="utf-8")
    changelog = (tmp_path / "knowledge" / "ddl" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "items=orders" in changelog and not (tmp_path / "assets" / "CHANGELOG.md").exists()
    index = (tmp_path / "INDEX.project.md").read_text(encoding="utf-8")
    assert "auto:begin:knowledge" in index and "auto:begin:ports" in index
    assert (tmp_path / "knowledge" / "wiki" / "index.md").is_file()
    assert (tmp_path / "work" / "tasks").is_dir()
    assert "assets/ddl" in (tmp_path / ".cursor" / "rules" / "x.mdc").read_text(encoding="utf-8")
    assert migrate.plan(tmp_path)["needed"] is False
