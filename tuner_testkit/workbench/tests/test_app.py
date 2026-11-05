from __future__ import annotations

from pathlib import Path

import pytest

DOGFOOD = Path(__file__).resolve().parents[2] / "tests_fixtures" / "sample_workspace"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tuner_testkit.action_words.registry import reset_registry_for_tests
    from tuner_testkit.catalog.directory import clear_directory_cache
    from tuner_testkit.tools.manifest import reset_registry_for_tests as reset_tools
    from tuner_testkit.workbench.app import create_app

    reset_tools()
    reset_registry_for_tests()
    clear_directory_cache(DOGFOOD)
    monkeypatch.setenv("TUNER_ROOT", str(DOGFOOD))
    return TestClient(create_app(root=DOGFOOD))


@pytest.fixture
def platform_client(monkeypatch: pytest.MonkeyPatch):
    """Workbench rooted at the platform repo itself (AI components page reads its DNA)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tuner_testkit.tools.manifest import reset_registry_for_tests as reset_tools
    from tuner_testkit.workbench.app import create_app

    reset_tools()
    repo = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("TUNER_ROOT", str(repo))
    return TestClient(create_app(root=repo))


def test_health_and_home(client) -> None:
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/").status_code == 200


def test_api_tools_lists_sample_tool_and_seed(client) -> None:
    items = client.get("/api/tools").json()["items"]
    ids = {row["id"] for row in items}
    assert "sample_tool" in ids
    assert "db_seed.sample_seed" in ids
    sample = next(row for row in items if row["id"] == "sample_tool")
    assert "params_schema" in sample and "count" in sample["params_schema"].get("properties", {})


def test_api_tools_search(client) -> None:
    items = client.get("/api/tools", params={"q": "sample"}).json()["items"]
    assert items
    assert all("sample" in row["id"].lower() or "sample" in row["name"].lower() for row in items)


def test_api_env_lists_names_only(client) -> None:
    resp = client.get("/api/env")
    assert resp.status_code == 200
    body = resp.json()
    assert "available" in body and "active" in body and "mode" in body
    blob = str(body).lower()
    for secret in ("password", "token", "secret", "authorization", "cookie"):
        assert secret not in blob
    assert client.get("/env").status_code == 200


def test_home_uses_kind_cards(client) -> None:
    html = client.get("/").text
    assert "造数" in html
    assert "工具" in html
    assert "ddl_tables" not in html


def test_db_seed_specialized_page_has_example(client) -> None:
    resp = client.get("/words/db_seed/db_seed.sample_seed")
    assert resp.status_code == 200
    text = resp.text
    assert "db_seed.sample_seed" in text
    assert "DEMO" in text
    assert "dry_run" in text
    assert "cleanup" in text


def test_api_words_lists_db_seed(client) -> None:
    items = client.get("/api/words", params={"category": "db_seed"}).json()["items"]
    ids = {row["id"] for row in items}
    assert "db_seed.sample_seed" in ids
    sample = next(row for row in items if row["id"] == "db_seed.sample_seed")
    assert sample["example_params"]["prefix"] == "DEMO"
    assert sample["has_dry_run"] is True


def test_api_ai_lists_platform_dna(platform_client) -> None:
    body = platform_client.get("/api/ai").json()
    assert body["total"] >= 4
    kinds = {row["kind"] for row in body["items"]}
    assert {"rule", "skill", "agent", "hook"} <= kinds
    names = {row["name"] for row in body["items"]}
    assert "create-action-word" in names
    assert "sut-self-learning" in names
    skill = next(row for row in body["items"] if row["name"] == "create-action-word")
    assert skill["version"] != "-"
    assert skill["kind"] == "skill"
    html = platform_client.get("/ai").text
    assert "AI 组件" in html
    assert "create-action-word" in html
    assert "1.1.4" in html or skill["version"] in html


def test_ai_detail_shows_version_and_role(platform_client) -> None:
    resp = platform_client.get("/ai/skill/create-action-word")
    assert resp.status_code == 200
    text = resp.text
    assert "create-action-word" in text
    assert "v" in text
    assert ".cursor/skills/create-action-word/SKILL.md" in text
    skills = platform_client.get("/api/ai", params={"kind": "skill"}).json()
    assert skills["items"]
    assert all(row["kind"] == "skill" for row in skills["items"])
    assert platform_client.get("/ai/skill/does-not-exist").status_code == 404


def test_api_run_sample_tool(client) -> None:
    resp = client.post("/api/tools/sample_tool/run", json={"params": {"count": 1, "label": "wb", "json": True}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["envelope"]["status"] == "succeeded"
