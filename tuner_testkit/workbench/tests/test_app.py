from __future__ import annotations

import json
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


def test_home_is_dashboard_with_nav(client) -> None:
    html = client.get("/").text
    assert "工作台看板" in html
    assert "造数" in html
    assert "工具" in html
    assert "ddl_tables" not in html
    # Cache-bust so a kit upgrade does not keep serving a stale app.css.
    assert 'href="/static/app.css?v=' in html


DASH_PAGES = ("assets", "automation", "tools", "doctor", "config")


def _forbid_collecting(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("dashboard requests must not scan the workspace")

    import tuner_testkit.apps.dashboard.collect as collect_mod

    for name in ("collect", "collect_assets", "collect_automation", "collect_tools", "collect_doctor", "collect_config"):
        monkeypatch.setattr(collect_mod, name, boom)
    monkeypatch.setattr("tuner_testkit.workbench.app.build_catalog", boom)
    monkeypatch.setattr("tuner_testkit.workbench.app.build_directory", boom)


@pytest.fixture
def dash_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Workspace with dashboard results written by the real collector (doctor + config included)."""
    from tuner_testkit.apps.dashboard.collect import collect
    from tuner_testkit.apps.dashboard.render import write_outputs

    root = tmp_path / "ws"
    (root / "assets" / "testcases" / "mod").mkdir(parents=True)
    (root / "assets" / "testcases" / "mod" / "TC-1.md").write_text("---\nstatus: ready\n---\n", encoding="utf-8")
    (root / "assets" / "testsheet" / "r1").mkdir(parents=True)
    (root / "assets" / "testsheet" / "r1" / "testsheet.md").write_text("# 测试单\n", encoding="utf-8")
    monkeypatch.setenv("TUNER_ROOT", str(root))
    result = collect(
        root,
        sections=["assets", "automation", "tools", "doctor"],
        doctor_config_loader=lambda _root: ({"channels": {"browser": "playwright-mcp"}}, {"findings": [], "errors": 0}),
    )
    result["sections"]["config"] = {
        "mode": "environments",
        "active": "dev",
        "environments": [
            {"name": "dev", "api_base_url": "http://api.example", "ui_base_url": "", "sections": {"REDIS": 2},
             "databases": [{"alias": "main", "type": "mysql", "host": "db.example", "port": 3306, "name": "app"}]},
        ],
        "error": None,
        "channels": {"browser": "playwright-mcp"},
        "ports": {},
        "knowledge": {"source_roots": 1, "api_docs": 0},
    }
    write_outputs(result, root=root)
    return root


def _client(root: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tuner_testkit.workbench.app import create_app

    app = create_app(root=root)
    return TestClient(app), app


def test_dashboard_pages_only_read_results(dash_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_collecting(monkeypatch)
    client, app = _client(dash_root)
    home = client.get("/")
    assert home.status_code == 200
    assert "统计于" in home.text and "本机尚未统计" not in home.text
    for page in DASH_PAGES:
        resp = client.get(f"/dashboard/{page}")
        assert resp.status_code == 200, page
    assert "db.example:3306" in client.get("/dashboard/config").text
    assert "r1" in client.get("/dashboard/assets").text
    assert client.get("/dashboard/nope").status_code == 404
    body = client.get("/api/dashboard").json()
    assert body["counts"]["testcases"] == 1
    assert app.state.dashboard.parse_count == 1


def test_dashboard_reparses_only_when_file_changes(dash_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    _forbid_collecting(monkeypatch)
    client, app = _client(dash_root)
    for _ in range(3):
        client.get("/")
    assert app.state.dashboard.parse_count == 1
    json_path = dash_root / "artifacts" / "catalogs" / "dashboard.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data["counts"]["testcases"] = 42
    json_path.write_text(json.dumps(data), encoding="utf-8")
    stat = json_path.stat()
    os.utime(json_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert client.get("/api/dashboard").json()["counts"]["testcases"] == 42
    assert app.state.dashboard.parse_count == 2


def test_dashboard_falls_back_to_markdown(dash_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_collecting(monkeypatch)
    (dash_root / "artifacts" / "catalogs" / "dashboard.json").unlink()
    client, _ = _client(dash_root)
    html = client.get("/").text
    assert "本机尚未统计" in html
    assert "DASHBOARD.md" in html
    for page in DASH_PAGES:
        assert client.get(f"/dashboard/{page}").status_code == 200, page
    assert client.get("/api/dashboard").json()["counts"]["testcases"] == 1


def test_dashboard_without_any_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_collecting(monkeypatch)
    client, _ = _client(tmp_path)
    assert "本机尚未统计" in client.get("/").text
    for page in DASH_PAGES:
        assert client.get(f"/dashboard/{page}").status_code == 200, page


def test_knowledge_catalog_is_built_once(client, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_catalog(*_a, **_k):
        calls.append(1)
        return {"knowledge": {"assets": []}, "artifacts": {"inbox": {}}, "tests": {"features": []}}

    monkeypatch.setattr("tuner_testkit.workbench.app.build_catalog", fake_catalog)
    assert client.get("/knowledge").status_code == 200
    assert client.get("/knowledge").status_code == 200
    assert len(calls) == 1
    assert client.get("/knowledge", params={"refresh": 1}).status_code == 200
    assert len(calls) == 2


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
