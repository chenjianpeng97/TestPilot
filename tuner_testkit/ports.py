"""Port contracts: capabilities the kit defines but never implements.

Teams differ too much on some channels (backend logs over SSH, a log platform
API, Rancher) for the kit to ship one implementation. The kit fixes the
*contract* here; each workspace writes an
adapter as a normal ``apps/<name>/`` CLI app that declares
``@tool(..., port="<name>")`` and is bound in ``config`` ``PORTS``.

Human-readable contract: ``docs/spec/ports.md``. This module is the
deterministic half used by ``tuner-config validate`` and ``tuner-workspace doctor``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PortContract:
    name: str
    summary: str
    required_flags: tuple[str, ...]
    optional_flags: tuple[str, ...] = ()
    read_only: bool = True
    status: str = "stable"  # stable | draft
    ask_topic: str | None = None  # tuner-task ask topic when the channel is unknown


PORT_CONTRACTS: dict[str, PortContract] = {
    "log-source": PortContract(
        name="log-source",
        summary="按时间窗、服务、关键字或 trace id 读取被测系统后端日志，脱敏后输出。",
        required_flags=("--since", "--until", "--json"),
        optional_flags=("--service", "--grep", "--trace-id", "--limit", "--out"),
        read_only=True,
        ask_topic="sut-log-source",
    ),
}


def known_ports() -> list[str]:
    return sorted(PORT_CONTRACTS)


def contract_problems(tool_row: Mapping[str, Any]) -> list[str]:
    """Problems with a catalog tool row (``spec_to_dict``) that claims a port."""
    port = tool_row.get("port")
    if not port:
        return []
    tool_id = tool_row.get("tool_id", "?")
    contract = PORT_CONTRACTS.get(str(port))
    if contract is None:
        return [f"{tool_id}: unknown port {port!r}; known: {', '.join(known_ports())}"]
    flags = {step.get("flag") for step in tool_row.get("argv_plan") or [] if step.get("flag")}
    problems = [f"{tool_id}: port {port} requires option {flag}" for flag in contract.required_flags if flag not in flags]
    if contract.read_only and tool_row.get("destructive"):
        problems.append(f"{tool_id}: port {port} is read-only; do not mark the tool destructive")
    if tool_row.get("origin") == "kit":
        problems.append(f"{tool_id}: port adapters live in workspace apps/, not in the kit")
    return problems


def port_status(
    tools: Iterable[Mapping[str, Any]],
    bindings: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """One row per known port: binding from config ``PORTS``, implementing tools, status.

    status: ``bound`` (binding points at a tool that implements the port and passes
    the contract), ``broken`` (binding set but the tool is missing / wrong / fails the
    contract), ``unbound`` (no binding; candidates may exist).
    """
    rows = list(tools)
    bindings = dict(bindings or {})
    out: list[dict[str, Any]] = []
    for name in known_ports():
        contract = PORT_CONTRACTS[name]
        implementers = [row for row in rows if row.get("port") == name]
        bound_module = bindings.get(name)
        bound_module = str(bound_module).strip() if bound_module else ""
        problems: list[str] = []
        status = "unbound"
        if bound_module:
            match = [row for row in implementers if row.get("module") == bound_module]
            if not match:
                status = "broken"
                problems.append(
                    f"PORTS[{name!r}] = {bound_module!r}, but no apps/*/tool.py declares port={name!r} with that module"
                )
            else:
                problems.extend(contract_problems(match[0]))
                status = "broken" if problems else "bound"
        out.append(
            {
                "port": name,
                "status": status,
                "contract_status": contract.status,
                "summary": contract.summary,
                "binding": bound_module or None,
                "implementers": [row.get("module") for row in implementers],
                "problems": problems,
                "ask_topic": contract.ask_topic,
            }
        )
    return out
