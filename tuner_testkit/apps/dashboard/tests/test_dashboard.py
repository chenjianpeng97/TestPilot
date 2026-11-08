from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tuner_testkit.apps.dashboard import cli
from tuner_testkit.apps.dashboard.collect import KIT_COMMANDS, collect, collect_tools
from tuner_testkit.apps.dashboard.render import MARKDOWN_NAME, flat_counts, write_outputs


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    cases = root / "assets" / "testcases"
    _write(cases / "mod_a" / "suite" / "TC-A-001.md", "---\nstatus: ready\n---\n# a1\n")
    _write(cases / "mod_a" / "suite" / "TC-A-002.md", "---\nstatus: draft\n---\n# a2\n")
    _write(cases / "mod_a" / "suite" / "README.md", "# suite\n")
    _write(cases / "mod_b" / "TC-B-001.md", "---\nstatus: ready\n---\n# b1\n")
    _write(cases / "CHANGELOG.md", "# changelog\n")
    _write(root / "assets" / "testsheet" / "r1" / "testsheet.md", "# 测试单\n")
    _write(root / "assets" / "testsheet" / "archived" / "r0" / "testsheet.md", "# 旧测试单\n")
    _write(root / "knowledge" / "defects" / "DEF-20260101-001.md", "---\nstatus: 新建\n---\n# d\n")
    _write(root / "knowledge" / "requirements" / "REQ-001.md", "# req\n")
    _write(root / "packages" / "api_objects" / "orders" / "list_orders.py", 'method = "GET"\npath = "/api/orders"\n')
    _write(root / "packages" / "api_objects" / "orders" / "create_order.py", 'method = "post"\npath = "/api/orders"\n')
    _write(root / "packages" / "page_objects" / "portal" / "login.py", 'class LoginPage(PageModel):\n    page_id = "login"\n')
    _write(
        root / "packages" / "action_words" / "db_seed" / "add_order.py",
        '@register\nclass AddOrder(ActionWord):\n    word_id = "db_seed.add_order"\n    name = "插入订单"\n',
    )
    _write(
        root / "packages" / "action_words" / "db_assert" / "order_exists.py",
        '@registry.register\nclass OrderExists(ActionWord):\n    word_id = "db_assert.order_exists"\n',
    )
    _write(root / "packages" / "action_words" / "db_seed" / "_helpers.py", "@register\nclass Hidden: ...\n")
    _write(
        root / "tests" / "features" / "orders.feature",
        "Feature: 订单\n  Scenario: 新建\n    Given x\n  Scenario: 删除\n    Given y\n",
    )
    _write(
        root / "tests" / "pytest" / "test_orders.py",
        "def test_a():\n    pass\n\nasync def test_b():\n    pass\n\nclass TestC:\n    def test_c(self):\n        pass\n\ndef helper():\n    pass\n",
    )
    _write(
        root / "apps" / "decorated" / "tool.py",
        'from tuner_testkit.tools import tool\n\n@tool(tool_id="decorated", name="装饰器写法", module="apps.decorated", group="data", destructive=True)\n'
        "def build_parser():\n    ...\n",
    )
    _write(
        root / "apps" / "called" / "tool.py",
        'from tuner_testkit.tools import tool\nfrom .cli import build_parser as _bp\n\n'
        'build_parser = tool(tool_id="called", name="调用写法", module="apps.called", port="log-source")(_bp)\n',
    )
    _write(root / "apps" / "script_only" / "__init__.py", "")
    return root


def test_counts_follow_definitions(ws: Path) -> None:
    result = collect(ws, sections=["assets", "automation", "tools"])
    counts = flat_counts(result["sections"])
    assert counts["testcases"] == 3
    assert counts["testsheets_active"] == 1
    assert counts["testsheets_archived"] == 1
    assert counts["defects"] == 1
    assert counts["requirements"] == 1
    assert counts["api_objects"] == 2
    assert counts["page_objects"] == 1
    assert counts["action_words"] == 2
    assert counts["db_seeds"] == 1
    assert counts["bdd_features"] == 1
    assert counts["bdd_scenarios"] == 2
    assert counts["pytest_files"] == 1
    assert counts["pytest_tests"] == 3
    assert counts["workspace_tools"] == 2
    assert counts["workspace_apps_without_tool"] == 1
    assets = result["sections"]["assets"]
    assert assets["testcases"]["by_module"][0] == {"name": "mod_a", "count": 2}
    assert {"name": "ready", "count": 2} in assets["testcases"]["by_status"]
    auto = result["sections"]["automation"]
    assert {"name": "POST", "count": 1} in auto["api_objects"]["by_method"]


def test_tools_parsed_statically(ws: Path) -> None:
    tools = collect_tools(ws)
    by_id = {t["id"]: t for t in tools["workspace"]}
    assert by_id["decorated"]["name"] == "装饰器写法"
    assert by_id["decorated"]["destructive"] is True
    assert by_id["called"]["port"] == "log-source"
    assert tools["workspace_without_tool"] == ["script_only"]


def test_every_kit_command_has_a_summary(ws: Path) -> None:
    commands = collect_tools(ws)["kit_commands"]
    if not commands:
        pytest.skip("tuner-testkit is not installed as a distribution")
    assert [c["command"] for c in commands if c["command"] not in KIT_COMMANDS] == []


def test_unchanged_counts_do_not_rewrite_markdown(ws: Path) -> None:
    first = collect(ws, sections=["assets", "automation", "tools"])
    first["checked_at"] = "2026-01-01T00:00:00+00:00"
    out = write_outputs(first, root=ws)
    assert out["changed"] is True and out["delta"] == {}
    md = ws / MARKDOWN_NAME
    before = md.read_text(encoding="utf-8")

    second = collect(ws, sections=["assets", "automation", "tools"])
    second["checked_at"] = "2026-01-02T00:00:00+00:00"
    out = write_outputs(second, root=ws)
    assert out["changed"] is False
    assert out["updated"] == "2026-01-01T00:00:00+00:00"
    assert md.read_text(encoding="utf-8") == before
    data = json.loads((ws / "artifacts" / "catalogs" / "dashboard.json").read_text(encoding="utf-8"))
    assert data["checked_at"] == "2026-01-02T00:00:00+00:00"
    assert data["updated"] == "2026-01-01T00:00:00+00:00"

    _write(ws / "assets" / "testcases" / "mod_b" / "TC-B-002.md", "---\nstatus: ready\n---\n# b2\n")
    third = collect(ws, sections=["assets", "automation", "tools"])
    third["checked_at"] = "2026-01-03T00:00:00+00:00"
    out = write_outputs(third, root=ws)
    assert out["changed"] is True
    assert out["delta"] == {"testcases": "3 -> 4"}
    assert "testcases: 4" in md.read_text(encoding="utf-8")


def test_failed_section_keeps_previous_counts(ws: Path) -> None:
    good = collect(ws, sections=["assets", "automation", "tools"])
    write_outputs(good, root=ws)
    broken = collect(ws, sections=["automation", "tools"])
    broken["sections"]["assets"] = {"error": "OSError: boom"}
    out = write_outputs(broken, root=ws)
    assert out["changed"] is False
    assert out["counts"]["testcases"] == 3
    assert out["errors"] == {"assets": "OSError: boom"}


def test_markdown_has_no_config_or_hosts(ws: Path) -> None:
    result = collect(ws, sections=["assets", "automation", "tools"])
    result["sections"]["config"] = {
        "mode": "environments",
        "environments": [{"name": "dev", "api_base_url": "http://sut.internal.example", "databases": [{"host": "db.internal.example"}]}],
    }
    out = write_outputs(result, root=ws, out_dir=ws / "out")
    text = Path(out["markdown"]).read_text(encoding="utf-8")
    assert "internal.example" not in text
    assert "dev" not in text
    assert not (ws / MARKDOWN_NAME).exists()
    assert Path(out["json"]).parent == ws / "out"


def test_describe_environments_whitelist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tuner_testkit.config import describe_environments
    from tuner_testkit.project import reset_path_cache

    monkeypatch.setenv("TUNER_ROOT", str(tmp_path))
    reset_path_cache()
    local = SimpleNamespace(
        ACTIVE_ENV="dev",
        ENVIRONMENTS={
            "dev": {
                "TEST_BASE_URL": "http://api.example",
                "DATABASES": {
                    "main": {"type": "mysql", "host": "db.example", "port": 3306, "name": "app",
                             "user": "admin-user", "password": "hunter2"},
                },
                "TEST_ACCOUNTS": {"admin": {"username": "boss", "password": "hunter2"}},
                "API_TOKEN": "tok-123",
                "ssh": {"host": "jump.example", "user": "root", "password": "hunter2"},
            },
            "SSH": {"host": "jump.example", "user": "root", "password": "hunter2"},
        },
    )
    view = describe_environments(local)
    reset_path_cache()
    assert view["active"] == "dev"
    dev = next(e for e in view["environments"] if e["name"] == "dev")
    assert dev["databases"] == [{"alias": "main", "type": "mysql", "host": "db.example", "port": 3306, "name": "app"}]
    assert dev["sections"] == {"TEST_ACCOUNTS": 1}
    blob = json.dumps(view, ensure_ascii=False).lower()
    for word in ("password", "hunter2", "token", "tok-123", "admin-user", "boss", '"user"', "jump.example"):
        assert word not in blob


def test_status_reads_results_without_collecting(ws: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    write_outputs(collect(ws, sections=["assets"]), root=ws)
    monkeypatch.setattr(cli, "collect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("status must not collect")))
    assert cli.main(["status", "--root", str(ws)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["testcases"] == 3

    (ws / "artifacts" / "catalogs" / "dashboard.json").unlink()
    assert cli.main(["status", "--root", str(ws)]) == 0
    assert json.loads(capsys.readouterr().out)["source"].endswith(MARKDOWN_NAME)


def test_refresh_cli_writes_out_dir(ws: Path, tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "out"
    assert cli.main(["refresh", "--root", str(ws), "--no-doctor", "--out-dir", str(out_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed"] is True
    assert (out_dir / MARKDOWN_NAME).is_file() and (out_dir / "dashboard.json").is_file()
    assert not (ws / MARKDOWN_NAME).exists()
    assert "doctor" not in payload["timings"]
