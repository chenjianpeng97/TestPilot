"""Config schema: section merge, masking, committed-secret scan, section validation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tuner_testkit import config_schema as cs
from tuner_testkit.config import apply_selected_environment


def _env(**kw):
    base = dict(DATABASES={}, TEST_BASE_URL="", TEST_UI_BASE_URL="", ACTIVE_ENV=None,
                OPS={}, CHANNELS={"browser": "playwright-mcp"}, PORTS={}, KNOWLEDGE={"api_docs": [], "source_roots": []})
    base.update(kw)
    return SimpleNamespace(**base)


def test_apply_sections_merges_nested_and_flat() -> None:
    target = _env(DATABASES={"main": {"type": "mysql", "host": "a"}}, OPS={"ssh": {"host": "h"}})
    cs.apply_sections(target, {
        "DATABASES": {"main": {"host": "b", "password": "p"}},
        "OPS": {"ssh": {"user": "u"}, "rancher": {"url": "r"}},
        "CHANNELS": {"browser": "cursor-browser"},
        "PORTS": {"log-source": "apps.x"},
        "TEST_UI_BASE_URL": "http://ui",
    })
    assert target.DATABASES["main"] == {"type": "mysql", "host": "b", "password": "p"}
    assert target.OPS == {"ssh": {"host": "h", "user": "u"}, "rancher": {"url": "r"}}
    assert target.CHANNELS == {"browser": "cursor-browser"}
    assert target.PORTS == {"log-source": "apps.x"}
    assert target.TEST_UI_BASE_URL == "http://ui"


def test_selected_environment_applies_machine_level_sections() -> None:
    target = _env()
    local = SimpleNamespace(
        CHANNELS={"browser": "cursor-browser"},
        KNOWLEDGE={"source_roots": ["D:/src"]},
        ENVIRONMENTS={"dev": {"TEST_BASE_URL": "http://api", "OPS": {"rancher": {"namespace": "dev"}}}},
    )
    assert apply_selected_environment(target, local, environ={}, active_file_text=None) == "dev"
    assert target.CHANNELS["browser"] == "cursor-browser"
    assert target.KNOWLEDGE["source_roots"] == ["D:/src"]
    assert target.OPS == {"rancher": {"namespace": "dev"}}
    assert target.TEST_BASE_URL == "http://api"


def test_describe_masks_secrets_and_reports_placeholders() -> None:
    env = _env(
        DATABASES={"main": {"host": "db", "password": "real-pass"}, "x": {"password": "CHANGE_ME"}},  # secret-scan: allow
        OPS={"rancher": {"url": "https://r", "token": "t0k"}},  # secret-scan: allow
        TEST_BASE_URL="http://api",
        ACTIVE_ENV="dev",
    )
    view = cs.describe(env, available=["dev"], mode="environments", env_local=True)
    assert view["databases"]["main"]["password"] == cs.MASK
    assert view["databases"]["x"]["password"] == cs.PLACEHOLDER_MARK
    assert "account" not in view
    assert view["ops"]["rancher"] == {"url": "https://r", "token": cs.MASK}
    assert view["ui_base_url"] == "http://api" and view["ui_base_url_explicit"] is False
    assert view["placeholders"] == ["DATABASES.x.password"]
    assert view["channels"]["browser"] == "playwright-mcp"


def test_committed_secret_literals(tmp_path: Path) -> None:
    good = tmp_path / "env.py"
    good.write_text('DATABASES = {"main": {"password": "CHANGE_ME"}}\nTOKEN = ""\n', encoding="utf-8")
    assert cs.committed_secret_literals(good) == []
    bad = tmp_path / "env_overlay.py"
    bad.write_text('DATABASES = {"main": {"password": "hunter2-real"}}\nAPI_TOKEN = "abc123"\n', encoding="utf-8")  # secret-scan: allow
    hits = cs.committed_secret_literals(bad)
    assert len(hits) == 2 and all("hunter2" not in h for h in hits)


def test_validate_sections_channels_ports_knowledge(tmp_path: Path) -> None:
    env = _env(CHANNELS={"browser": "netscape", "ide": "x"}, PORTS={"log-source": "tuner_testkit.x", "nope": "apps.y"},
               KNOWLEDGE={"source_roots": [str(tmp_path / "missing")], "api_docs": ["docs/none.json"], "odd": 1})
    codes = {f.code for f in cs.validate_sections(env, root=tmp_path, tools=[])}
    assert {"channels.browser", "channels.unknown_key", "ports.unknown", "ports.module",
            "knowledge.source_roots", "knowledge.api_docs", "knowledge.unknown_key"} <= codes
    assert "ports.log-source" in codes  # bound to a module that no tool implements


def test_validate_sections_clean(tmp_path: Path) -> None:
    tools = [{"tool_id": "logs", "module": "apps.logs", "port": "log-source", "origin": "workspace", "destructive": False,
              "argv_plan": [{"flag": "--since"}, {"flag": "--until"}, {"flag": "--json"}]}]
    env = _env(PORTS={"log-source": "apps.logs"})
    assert [f for f in cs.validate_sections(env, root=tmp_path, tools=tools) if f.severity == "error"] == []
