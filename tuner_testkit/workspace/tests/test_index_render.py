from __future__ import annotations

from pathlib import Path

from tuner_testkit.workspace.index_render import check_index, render_index, render_text

CATALOG = {
    "knowledge": {
        "ddl": [{"datasource": "main", "tables": ["orders"], "path": "assets/ddl/main", "table_count": 1}],
        "sql_files": [],
        "assets": [{"path": "assets/usecases/a.md", "category": "usecases", "domain": "d", "source": "s", "confidence": "high", "title": "A"}],
    },
    "api_objects": [{"method": "GET", "path": "/orders", "file": "packages/api_objects/orders/GET.v1.py"}],
    "page_objects": [],
    "action_words": [{"word_id": "db_seed.x", "name": "X", "category": "db_seed"}],
    "tools": [
        {"tool_id": "t", "origin": "workspace", "argv": ["python", "-m", "apps.t"], "summary": "T", "readme_path": "apps/t/README.md"},
        {"tool_id": "kit", "origin": "kit", "argv": ["x"], "summary": "K"},
    ],
    "tests": {"features": [{"path": "tests/features/a.feature", "scenarios": [{}, {}], "tags": ["x"]}]},
}

INDEX = """# idx

<!-- auto:begin:ddl -->
old
<!-- auto:end:ddl -->

manual text stays

<!-- auto:begin:apps -->
| a |
<!-- auto:end:apps -->

<!-- auto:begin:mystery -->
keep
<!-- auto:end:mystery -->
"""


def test_render_text_replaces_known_zones_only() -> None:
    new_text, rendered, unknown = render_text(INDEX, CATALOG)
    assert rendered == ["ddl", "apps"]
    assert unknown == ["mystery"]
    assert "manual text stays" in new_text
    assert "| `main` | `orders` | `assets/ddl/main` |" in new_text
    assert "| `t` | `python -m apps.t` | T | `apps/t/README.md` |" in new_text
    assert "`kit`" not in new_text  # kit tools are not workspace apps
    assert "keep" in new_text


def test_render_and_check_round_trip(tmp_path: Path) -> None:
    index = tmp_path / "INDEX.project.md"
    index.write_text(INDEX, encoding="utf-8")
    first = render_index(tmp_path, catalog=CATALOG)
    assert first["changed"] is True and first["zones"] == ["ddl", "apps"]
    assert check_index(tmp_path, catalog=CATALOG)["up_to_date"] is True
    second = render_index(tmp_path, catalog=CATALOG)
    assert second["changed"] is False
    stale = dict(CATALOG)
    stale["tools"] = []
    result = check_index(tmp_path, catalog=stale)
    assert result["up_to_date"] is False and result["stale_zones"] == ["apps"]


LAYERED = {
    **CATALOG,
    "knowledge": {
        "ddl": [],
        "sql_files": [],
        "assets": [
            {"path": "knowledge/requirements/REQ-a.md", "layer": "knowledge", "category": "requirements", "id": "REQ-a",
             "version": "1.0.0", "status": "active", "title": "A"},
            {"path": "assets/testcases/m/s/X.md", "layer": "assets", "category": "testcases", "domain": None,
             "source": "REQ-a", "confidence": "high", "title": "X"},
        ],
    },
    "tools": [
        {"tool_id": "logs", "origin": "workspace", "module": "apps.logs", "port": "log-source", "argv": ["python", "-m", "apps.logs"], "summary": "L"},
        {"tool_id": "t", "origin": "workspace", "module": "apps.t", "argv": ["python", "-m", "apps.t"], "summary": "T"},
    ],
}


def test_knowledge_and_ports_zones() -> None:
    text = "<!-- auto:begin:knowledge -->\n<!-- auto:end:knowledge -->\n<!-- auto:begin:assets -->\n<!-- auto:end:assets -->\n" \
           "<!-- auto:begin:ports -->\n<!-- auto:end:ports -->\n"
    new_text, rendered, _ = render_text(text, LAYERED)
    assert rendered == ["knowledge", "assets", "ports"]
    knowledge_zone = new_text.split("auto:end:knowledge")[0]
    assert "REQ-a" in knowledge_zone and "assets/testcases" not in knowledge_zone
    assets_zone = new_text.split("auto:begin:assets")[1].split("auto:end:assets")[0]
    assert "assets/testcases/m/s/X.md" in assets_zone and "knowledge/requirements" not in assets_zone
    ports_zone = new_text.split("auto:begin:ports")[1]
    assert "`log-source` | `logs` | `apps.logs`" in ports_zone and "`t`" not in ports_zone


def test_legacy_index_without_knowledge_zone_keeps_listing_knowledge() -> None:
    text = "<!-- auto:begin:assets -->\n<!-- auto:end:assets -->\n"
    new_text, _, _ = render_text(text, LAYERED)
    assert "knowledge/requirements/REQ-a.md" in new_text and "assets/testcases/m/s/X.md" in new_text
