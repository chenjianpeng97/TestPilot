from datetime import datetime, timezone
from pathlib import Path

from apps.sample_log_source.cli import build_parser, main
from apps.sample_log_source.core import LogLine, parse_time, read_lines, select
from tuner_testkit.ports import PORT_CONTRACTS, contract_problems
from tuner_testkit.tools import export_tools

FIXTURE = Path(__file__).resolve().parents[3] / "data" / "sample-logs"
DOGFOOD = Path(__file__).resolve().parents[3]


def test_parse_time_relative_and_iso() -> None:
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    assert parse_time("now", now=now) == now
    assert parse_time("2h", now=now) == datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
    assert parse_time("2026-11-04T10:00:00Z").hour == 10


def test_select_by_window_service_and_trace() -> None:
    lines = read_lines(FIXTURE)
    picked = select(
        lines,
        since=parse_time("2026-11-04T10:00:00Z"),
        until=parse_time("2026-11-04T10:10:00Z"),
        trace_id="t-1002",
    )
    assert [line.service for line in picked] == ["order-service", "order-service", "stock-service"]
    only_errors = select(lines, since=parse_time("2026-11-04T00:00:00Z"), until=parse_time("2026-11-05T00:00:00Z"), grep="failed")
    assert len(only_errors) == 1 and only_errors[0].level == "ERROR"


def test_select_redacts_secrets() -> None:
    ts = parse_time("2026-11-04T10:00:00Z")
    raw = LogLine(ts=ts, level="INFO", service="auth", text="login ok Authorization: Bearer abcdefghijklmnop0123456789")  # secret-scan: allow
    picked = select([raw], since=ts, until=ts)
    assert "abcdefghijklmnop0123456789" not in picked[0].text


def test_cli_matches_log_source_contract() -> None:
    usage = build_parser().format_help()
    for flag in (*PORT_CONTRACTS["log-source"].required_flags, *PORT_CONTRACTS["log-source"].optional_flags):
        assert flag in usage
    rows = [row for row in export_tools(DOGFOOD, include_kit=False) if row["tool_id"] == "sample_log_source"]
    assert rows and rows[0]["port"] == "log-source"
    assert contract_problems(rows[0]) == []


def test_main_json_envelope(capsys, monkeypatch) -> None:
    monkeypatch.chdir(DOGFOOD)
    code = main(["--since", "2026-11-04T09:00:00Z", "--until", "2026-11-04T11:00:00Z", "--service", "stock-service", "--json"])
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert '"status": "succeeded"' in out
    assert "stock-service" in out
