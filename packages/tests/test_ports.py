"""Port contracts: kit defines, workspace apps implement."""
from __future__ import annotations

import argparse

import pytest

from tuner_testkit.ports import PORT_CONTRACTS, contract_problems, known_ports, port_status
from tuner_testkit.tools import manifest as m


def _row(**kw):
    base = {"tool_id": "logs", "module": "apps.logs", "port": "log-source", "origin": "workspace", "destructive": False,
            "argv_plan": [{"flag": "--since"}, {"flag": "--until"}, {"flag": "--json"}]}
    base.update(kw)
    return base


def test_contracts_known() -> None:
    assert known_ports() == ["log-source"]  # records with a fixed place and template (defects, cases) are not ports
    assert PORT_CONTRACTS["log-source"].read_only is True
    assert PORT_CONTRACTS["log-source"].ask_topic == "sut-log-source"


def test_contract_problems() -> None:
    assert contract_problems(_row()) == []
    assert contract_problems(_row(port=None)) == []
    missing = contract_problems(_row(argv_plan=[{"flag": "--since"}]))
    assert any("--until" in p for p in missing) and any("--json" in p for p in missing)
    assert any("read-only" in p for p in contract_problems(_row(destructive=True)))
    assert any("not in the kit" in p for p in contract_problems(_row(origin="kit")))
    assert any("unknown port" in p for p in contract_problems(_row(port="smoke-signal")))


def test_port_status_bound_unbound_broken() -> None:
    rows = {r["port"]: r for r in port_status([_row()], {"log-source": "apps.logs"})}
    assert rows["log-source"]["status"] == "bound"
    unbound = {r["port"]: r for r in port_status([_row()], {})}
    assert unbound["log-source"]["status"] == "unbound" and unbound["log-source"]["implementers"] == ["apps.logs"]
    broken = {r["port"]: r for r in port_status([], {"log-source": "apps.missing"})}
    assert broken["log-source"]["status"] == "broken" and broken["log-source"]["problems"]


def test_tool_decorator_carries_port() -> None:
    def parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser()
        for flag in ("--since", "--until"):
            p.add_argument(flag, required=True, help=flag)
        p.add_argument("--json", action="store_true", help="json")
        return p

    try:
        spec = m.register_tool(parser, tool_id="port_demo", name="demo", module="apps.port_demo", port="log-source")
        row = m.spec_to_dict(spec)
        assert row["port"] == "log-source"
        assert contract_problems(row) == []
        with pytest.raises(ValueError):
            m.register_tool(parser, tool_id="port_bad", name="bad", module="apps.port_bad", port="Log Source")
    finally:
        m._REGISTRY.pop("port_demo", None)  # noqa: SLF001
