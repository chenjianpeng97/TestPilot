"""Catalog build against a synthetic workspace and against dogfood/."""
from __future__ import annotations

import json
from pathlib import Path

from tuner_testkit.catalog.build import CATALOG_VERSION, build_catalog, write_catalog
from tuner_testkit.catalog.scan import scan_assets, scan_inbox, scan_run_manifests
from tuner_testkit.tools import manifest as tools_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOGFOOD = REPO_ROOT / "dogfood"


def setup_function() -> None:
    tools_manifest.reset_registry_for_tests()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_catalog_synthetic_workspace(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname='x'\nversion='0'\n")
    _write(tmp_path / "assets" / "ddl" / "main" / "orders.sql", "CREATE TABLE orders (id int);\n")
    _write(tmp_path / "assets" / "sql" / "q.sql", "-- domain: sales\nSELECT 1;\n")
    _write(
        tmp_path / "assets" / "usecases" / "sales" / "checkout.md",
        "---\ndomain: sales\nsource: zentao#1\ndate: 2026-01-01\nversion: 1.0.0\nconfidence: high\n---\n# Checkout\n",
    )
    _write(tmp_path / "packages" / "api_objects" / "orders" / "GET.v1.py", "class M:\n    method = 'GET'\n    path = '/orders'\n")
    _write(tmp_path / "packages" / "api_objects" / "auth.py", "method = 'X'\n")
    _write(tmp_path / "packages" / "page_objects" / "shop" / "login.py", "page_id = 'shop.login@v1'\nPageModel = None\n")
    _write(tmp_path / "packages" / "page_objects" / "session.py", "PageModel = None\n")
    _write(tmp_path / "tests" / "features" / "a.feature", "@x\nFeature: A\n  @y\n  Scenario: one\n    Given g\n  Scenario Outline: two\n    Given g\n")
    _write(tmp_path / "tests" / "pytest" / "test_perf.py", "def test_x(): pass\n")
    _write(tmp_path / "data" / "mocks" / "m.json", "{}")
    _write(tmp_path / "data" / "sut-accounts.local.yaml", "secret: 1\n")
    _write(tmp_path / "docs" / "guide.md", "# g\n")
    _write(
        tmp_path / "artifacts" / "inbox" / "20260101T000000Z-agent-slice.md",
        "---\nagent: sut-self-learning\nslice: slice\nstarted: 2026-01-01T00:00:00Z\nstatus: done\n---\n# slice — intent\n",
    )
    _write(tmp_path / "artifacts" / "inbox" / "20260102T000000Z-agent-open.md", "---\nagent: a\nslice: b\nstatus: open\nstarted: 2026-01-02T00:00:00Z\n---\n# open\n")
    _write(
        tmp_path / "artifacts" / "runs" / "r1" / "manifest.json",
        json.dumps({"kind": "run", "run_id": "r1", "status": "succeeded", "started": "2026-01-01T00:00:00Z", "files": ["stdout.log"]}),
    )
    (tmp_path / "artifacts" / "evidence" / "e1").mkdir(parents=True)

    payload = build_catalog(tmp_path, include_kit_tools=False)
    counts = payload["counts"]
    assert payload["catalog_version"] == CATALOG_VERSION
    assert counts["ddl_tables"] == 1 and counts["sql_files"] == 1 and counts["assets"] == 2
    assert counts["api_objects"] == 1 and payload["api_objects"][0]["path"] == "/orders"
    assert counts["page_objects"] == 1 and payload["page_objects"][0]["page_id"] == "shop.login@v1"
    assert counts["features"] == 1 and counts["scenarios"] == 2
    assert counts["pytest_nodes"] == 1
    assert counts["data_files"] == 1  # *.local.yaml never listed
    assert counts["docs"] == 1
    assert counts["inbox"] == 2 and counts["inbox_open"] == 1
    assert payload["artifacts"]["inbox"]["recent"][0]["status"] == "open"  # newest first
    assert counts["runs"] == 1 and payload["artifacts"]["runs"]["recent"][0]["run_id"] == "r1"
    assert counts["evidence_runs"] == 1
    assert counts["tools"] == 0 and counts["action_words"] == 0
    usecase = next(a for a in payload["knowledge"]["assets"] if a["category"] == "usecases")
    assert usecase["confidence"] == "high" and usecase["title"] == "Checkout"
    assert "author_mismatch" in usecase

    out = write_catalog(payload, tmp_path / "artifacts" / "catalogs" / "workspace.json")
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["features"] == 1


def test_scan_knowledge_layer(tmp_path: Path) -> None:
    _write(tmp_path / "knowledge" / "ddl" / "main" / "orders.sql", "CREATE TABLE orders (id int);\n")
    _write(tmp_path / "knowledge" / "ddl" / "CHANGELOG.md", "# c\n")
    _write(tmp_path / "knowledge" / "wiki" / "index.md", "# index\n")
    _write(tmp_path / "knowledge" / "wiki" / "domain-notes" / "acme" / "profile.md", "---\nversion: 1.0.0\n---\n# Acme\n")
    _write(tmp_path / "knowledge" / "requirements" / "REQ-a.md", "---\nkind: requirement\nid: REQ-a\nstatus: active\n---\n# REQ-a A\n")
    _write(tmp_path / "knowledge" / "defects" / "DEF-20261104-001.md", "---\nid: DEF-20261104-001\nstatus: 激活\n---\n# d\n")
    _write(tmp_path / "assets" / "testcases" / "README.md", "# cases\n")
    rows = {row["path"]: row for row in scan_assets(tmp_path)}
    assert set(rows) == {
        "knowledge/wiki/domain-notes/acme/profile.md",
        "knowledge/requirements/REQ-a.md",
        "knowledge/defects/DEF-20261104-001.md",
        "assets/testcases/README.md",
    }
    assert rows["knowledge/wiki/domain-notes/acme/profile.md"]["category"] == "domain-notes"
    assert rows["knowledge/requirements/REQ-a.md"]["layer"] == "knowledge" and rows["knowledge/requirements/REQ-a.md"]["id"] == "REQ-a"
    assert rows["assets/testcases/README.md"]["layer"] == "assets"
    payload = build_catalog(tmp_path, include_kit_tools=False)
    assert payload["knowledge"]["ddl"][0]["path"] == "knowledge/ddl/main"


def test_build_catalog_dogfood_sees_fixtures() -> None:
    payload = build_catalog(DOGFOOD)
    tools = {row["tool_id"]: row for row in payload["tools"]}
    assert "sample_tool" in tools
    assert tools["sample_tool"]["origin"] == "workspace"
    assert "count" in tools["sample_tool"]["params_schema"]["properties"]
    assert tools["sample_tool"]["params_schema"]["required"] == ["count"]
    assert "author_mismatch" in tools["sample_tool"]
    assert "out" not in tools["sample_tool"]["params_schema"]["properties"]  # hide_params
    assert tools["sample_tool"]["readme_path"] == "apps/sample_tool/README.md"
    assert tools["mock_server"]["origin"] == "kit"
    words = {row.get("word_id"): row for row in payload["action_words"]}
    assert "db_seed.sample_seed" in words
    assert words["db_seed.sample_seed"]["destructive"] is True
    assert "dry_run" in words["db_seed.sample_seed"]["params_schema"]["properties"]
    assert payload["counts"]["features"] == 5
    assert any(a["path"].endswith("roadmap.md") for a in payload["knowledge"]["assets"])


def test_scan_helpers_tolerate_missing_dirs(tmp_path: Path) -> None:
    assert scan_assets(tmp_path) == []
    assert scan_inbox(tmp_path) == {"total": 0, "by_status": {}, "recent": []}
    assert scan_run_manifests(tmp_path, "runs") == {"total": 0, "recent": []}
