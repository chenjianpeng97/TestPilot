"""tuner-workspace doctor: deterministic checklist over a scaffolded workspace."""
from __future__ import annotations

from pathlib import Path

from tuner_testkit.apps.init_repo.scaffold import scaffold
from tuner_testkit.tools import manifest as tools_manifest
from tuner_testkit.workspace.doctor import run_doctor


def setup_function() -> None:
    tools_manifest.reset_registry_for_tests()


def _config(view: dict, errors: int = 0):
    def loader(_root: Path):
        return view, {"errors": errors, "warnings": 0, "findings": []}

    return loader


def _by_id(result: dict) -> dict[str, dict]:
    return {c["id"]: c for c in result["checks"]}


def test_fresh_scaffold_reports_gaps(tmp_path: Path) -> None:
    ws = tmp_path / "acme"
    scaffold(ws, with_ai=False)
    view = {"env_local": False, "mode": "none", "api_base_url": "", "ui_base_url": "", "placeholders": [],
            "databases": {}, "channels": {"browser": "playwright-mcp"}, "ports": {}, "knowledge": {}}
    result = run_doctor(ws, config_loader=_config(view))
    checks = _by_id(result)
    assert not result["ok"]
    assert checks["layout.dirs"]["status"] == "ok"
    assert "layout.legacy" not in checks
    assert checks["config.env_local"]["status"] == "missing"
    assert checks["data.accounts"]["status"] == "missing"
    assert checks["channels.browser"]["status"] == "ok"
    assert checks["ports.log-source"]["status"] == "missing"
    assert "sut-log-source" in checks["ports.log-source"]["fix"]
    assert "ports.defect-sink" not in checks
    assert checks["knowledge.defects"]["status"] == "info"
    assert checks["knowledge.ddl"]["status"] == "missing"
    assert checks["knowledge.wiki"]["status"] == "info"  # index.md stub exists, no pages yet
    assert checks["dna.version"]["status"] == "missing"  # scaffolded with --no-ai


def test_configured_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "acme"
    scaffold(ws, with_ai=False)
    (ws / "knowledge" / "ddl" / "main").mkdir(parents=True, exist_ok=True)
    (ws / "knowledge" / "ddl" / "main" / "orders.sql").write_text("create table orders (id int);\n", encoding="utf-8")
    (ws / "data" / "sut-accounts.local.yaml").write_text(
        "accounts:\n  - id: qa-admin\n    role: admin\n    password: x\n", encoding="utf-8"  # secret-scan: allow
    )
    view = {"env_local": True, "mode": "environments", "active_env": "uat", "api_base_url": "https://api.acme",
            "ui_base_url": "https://acme", "placeholders": [], "databases": {"main": {}},
            "channels": {"browser": "cursor-browser"}, "ports": {}, "knowledge": {"source_roots": ["D:/src"], "api_docs": []}}
    checks = _by_id(run_doctor(ws, config_loader=_config(view)))
    assert checks["config.api_url"]["status"] == "ok"
    assert checks["data.accounts"]["status"] == "ok"
    assert checks["knowledge.ddl"]["status"] == "ok"
    assert checks["knowledge.source_roots"]["status"] == "ok"
    assert checks["channels.browser"]["detail"].endswith("cursor-browser")


def test_legacy_layout_and_broken_config(tmp_path: Path) -> None:
    ws = tmp_path / "old"
    scaffold(ws, with_ai=False)
    (ws / "assets" / "usecases" / "order").mkdir(parents=True)
    (ws / "assets" / "usecases" / "order" / "create.md").write_text("# x\n", encoding="utf-8")
    checks = _by_id(run_doctor(ws, config_loader=_config({"error": "EnvProfileError: 未选择环境"})))
    assert checks["layout.legacy"]["status"] == "warn"
    assert checks["config.load"]["status"] == "error"


def test_defect_library_counts_and_errors(tmp_path: Path) -> None:
    from datetime import date

    from tuner_testkit.defects import create

    ws = tmp_path / "acme"
    scaffold(ws, with_ai=False)
    path = create(ws / "knowledge" / "defects", day=date(2026, 11, 4), title="库存未回填", severity="严重", defect_type="编码")
    view = {"channels": {"browser": "playwright-mcp"}, "ports": {}, "knowledge": {}}
    checks = _by_id(run_doctor(ws, config_loader=_config(view)))
    assert checks["knowledge.defects"]["status"] == "error"  # template placeholders not filled yet
    path.write_text(path.read_text(encoding="utf-8").replace("（待填）", "已填写"), encoding="utf-8")
    checks = _by_id(run_doctor(ws, config_loader=_config(view)))
    assert checks["knowledge.defects"] == {**checks["knowledge.defects"], "status": "ok", "detail": "激活 1"}


def test_checks_carry_tier_and_ok_ignores_feature_checks() -> None:
    from tuner_testkit.workspace.doctor import FEATURE_GROUPS, _Report

    report = _Report()
    report.add("config.api_url", "ok", "x")
    report.add("knowledge.ddl", "missing", "x")
    report.add("ports.log-source", "missing", "x", group="ports")
    tiers = {c["id"]: c["tier"] for c in report.checks}
    assert tiers == {"config.api_url": "core", "knowledge.ddl": "feature", "ports.log-source": "feature"}
    assert report.summary("core")["missing"] == 0
    assert report.summary("feature")["missing"] == 2
    assert {"knowledge", "ports", "trace"} == set(FEATURE_GROUPS)


def test_capabilities_report_ready_and_blockers() -> None:
    from tuner_testkit.workspace.doctor import _capabilities, _Report

    report = _Report()
    for check_id in ("layout.dirs", "config.ui_url", "data.accounts", "channels.browser"):
        report.add(check_id, "ok", "x")
    report.add("knowledge.source_roots", "info", "未配置源码根", fix="maintain-config")
    caps = {c["id"]: c for c in _capabilities(report.checks)}
    assert caps["ui-run"]["ready"] is True
    assert caps["source"]["ready"] is False
    assert caps["source"]["blockers"][0]["id"] == "knowledge.source_roots"
    assert caps["backend-log"]["blockers"][0]["detail"] == "检查项不存在"
