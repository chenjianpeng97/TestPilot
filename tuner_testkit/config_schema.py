"""Config schema: which sections exist, how they merge, how to mask and validate them.

``config/`` answers "where, and through which channel". Human-readable
contract: ``docs/spec/config-syntax.md``.

Sections
--------
Per environment (inside ``env_local.ENVIRONMENTS[<name>]``, or flat):

* ``TEST_UI_BASE_URL`` / ``TEST_BASE_URL`` — scalars (test accounts live in ``data/sut-accounts.local.yaml``)
* ``DATABASES`` — alias -> connection dict (merged per alias)
* ``OPS`` — operations channels (``rancher`` / ``ssh`` / ``log_platform`` …), read by port adapters

Workspace level (``config/env.py`` / ``env_overlay.py`` committed; top-level of
``env_local.py`` may override per machine):

* ``CHANNELS`` — execution channels, e.g. ``{"browser": "playwright-mcp"}``
* ``PORTS`` — port name -> adapter module, e.g. ``{"log-source": "apps.acme_logs"}``
* ``KNOWLEDGE`` — ``api_docs`` (list of URLs/paths), ``source_roots`` (local paths), ``wiki``
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

PROFILE_SCALARS: tuple[str, ...] = ("TEST_BASE_URL", "TEST_UI_BASE_URL")
PROFILE_DICT_SECTIONS: tuple[str, ...] = ("DATABASES", "OPS")
WORKSPACE_SECTIONS: tuple[str, ...] = ("CHANNELS", "PORTS", "KNOWLEDGE")
ALL_SECTIONS: tuple[str, ...] = (*PROFILE_SCALARS, *PROFILE_DICT_SECTIONS, *WORKSPACE_SECTIONS)

BROWSER_CHANNELS: tuple[str, ...] = ("playwright-mcp", "cursor-browser")
CHANNEL_KEYS: dict[str, tuple[str, ...]] = {"browser": BROWSER_CHANNELS}
DEFAULT_CHANNELS: dict[str, str] = {"browser": "playwright-mcp"}
KNOWLEDGE_KEYS: tuple[str, ...] = ("api_docs", "source_roots", "wiki")
DEFAULT_KNOWLEDGE: dict[str, Any] = {"api_docs": [], "source_roots": [], "wiki": "knowledge/wiki"}

PLACEHOLDERS = frozenset({"CHANGE_ME", "change_me", "replace-me", "REPLACE_ME", "...", "<secret>"})
SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|cookie|authorization|session|api[_-]?key|private[_-]?key|credential)"
)
MASK = "***"
PLACEHOLDER_MARK = "<placeholder>"


# ---------------------------------------------------------------------------
# merging
# ---------------------------------------------------------------------------
def _merge_nested(target: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    """Merge ``alias -> dict`` maps per alias (DATABASES / OPS)."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key] = {**target[key], **value}
        elif isinstance(value, dict):
            target[key] = dict(value)
        else:
            target[key] = value


def apply_sections(target: Any, source: Mapping[str, Any], *, sections: Iterable[str] = ALL_SECTIONS) -> None:
    """Merge known sections from ``source`` onto module/object ``target``."""
    for name in sections:
        if name not in source:
            continue
        value = source[name]
        if name in PROFILE_SCALARS:
            if value:
                setattr(target, name, str(value))
            continue
        if not isinstance(value, dict):
            continue
        current = getattr(target, name, None)
        if not isinstance(current, dict):
            current = {}
            setattr(target, name, current)
        if name in PROFILE_DICT_SECTIONS:
            _merge_nested(current, value)
        else:
            current.update(value)


def module_sections(mod: Any) -> dict[str, Any]:
    return {name: getattr(mod, name) for name in ALL_SECTIONS if hasattr(mod, name)}


# ---------------------------------------------------------------------------
# masking / description
# ---------------------------------------------------------------------------
def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.strip() in PLACEHOLDERS


def mask(value: Any, *, key: str = "") -> Any:
    """Recursively mask secret-looking keys; placeholders are reported, never real values."""
    if isinstance(value, Mapping):
        return {str(k): mask(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v, key=key) for v in value]
    if key and SECRET_KEY_RE.search(key) and value not in (None, ""):
        return PLACEHOLDER_MARK if is_placeholder(value) else MASK
    return value


def find_placeholders(value: Any, prefix: str = "") -> list[str]:
    """Dotted paths whose value is still a template placeholder."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for k, v in value.items():
            found.extend(find_placeholders(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            found.extend(find_placeholders(v, f"{prefix}[{i}]"))
    elif is_placeholder(value):
        found.append(prefix)
    return found


def describe(env: Any, *, available: list[str] | None = None, mode: str = "unknown", env_local: bool = False) -> dict[str, Any]:
    """Masked, JSON-able view of the merged config (what ``tuner-config show --json`` prints)."""
    databases = getattr(env, "DATABASES", None) or {}
    channels = {**DEFAULT_CHANNELS, **(getattr(env, "CHANNELS", None) or {})}
    knowledge = {**DEFAULT_KNOWLEDGE, **(getattr(env, "KNOWLEDGE", None) or {})}
    ops = getattr(env, "OPS", None) or {}
    ui = str(getattr(env, "TEST_UI_BASE_URL", "") or "")
    api = str(getattr(env, "TEST_BASE_URL", "") or "")
    placeholders = find_placeholders(
        {"DATABASES": databases, "OPS": ops}
    )
    return {
        "mode": mode,
        "env_local": env_local,
        "active_env": getattr(env, "ACTIVE_ENV", None),
        "available": sorted(available or []),
        "ui_base_url": ui or api,
        "api_base_url": api,
        "ui_base_url_explicit": bool(ui),
        "databases": mask(databases),
        "channels": channels,
        "ports": dict(getattr(env, "PORTS", None) or {}),
        "knowledge": mask(knowledge),
        "ops": mask(ops),
        "placeholders": placeholders,
    }


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    severity: str  # error | warn | info
    code: str
    message: str
    fix: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def committed_secret_literals(path: Path) -> list[str]:
    """``key = "literal"`` / ``{"password": "literal"}`` with a real-looking secret in a committed file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    hits: list[str] = []

    def _check(key: str, node: ast.AST, line: int) -> None:
        if not SECRET_KEY_RE.search(key):
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value and value not in PLACEHOLDERS:
                hits.append(f"{path.name}:{line} {key}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key_node, value_node in zip(node.keys, node.values, strict=True):
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    _check(key_node.value, value_node, getattr(key_node, "lineno", 0))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _check(target.id, node.value, node.lineno)
    return hits


def validate_sections(env: Any, *, root: Path, tools: list[dict[str, Any]] | None = None) -> list[Finding]:
    """Schema checks on the merged config. ``tools`` are catalog rows for the PORTS check."""
    findings: list[Finding] = []
    channels = getattr(env, "CHANNELS", None)
    if channels is None:
        findings.append(Finding("warn", "channels.missing", "config 没有 CHANNELS，按默认 browser=playwright-mcp", "maintain-config"))
        channels = {}
    elif not isinstance(channels, Mapping):
        findings.append(Finding("error", "channels.type", "CHANNELS 必须是 dict", "maintain-config"))
        channels = {}
    for key, value in channels.items():
        allowed = CHANNEL_KEYS.get(str(key))
        if allowed is None:
            findings.append(Finding("warn", "channels.unknown_key", f"CHANNELS 有未知键 {key!r}", "docs/spec/config-syntax.md"))
        elif value not in allowed:
            findings.append(
                Finding("error", f"channels.{key}", f"CHANNELS[{key!r}]={value!r} 不在 {list(allowed)}", "maintain-config")
            )

    ports = getattr(env, "PORTS", None) or {}
    if not isinstance(ports, Mapping):
        findings.append(Finding("error", "ports.type", "PORTS 必须是 dict", "maintain-config"))
        ports = {}
    from tuner_testkit.ports import PORT_CONTRACTS, port_status

    for name, module in ports.items():
        if name not in PORT_CONTRACTS:
            findings.append(Finding("warn", "ports.unknown", f"PORTS 有未知端口 {name!r}", "docs/spec/ports.md"))
        if module and not str(module).startswith("apps."):
            findings.append(Finding("error", "ports.module", f"PORTS[{name!r}]={module!r} 必须指向 workspace apps.<name>", "create-app"))
    if tools is not None:
        for row in port_status(tools, ports):
            if row["status"] == "broken":
                for problem in row["problems"]:
                    findings.append(Finding("error", f"ports.{row['port']}", problem, "create-app / maintain-config"))

    knowledge = getattr(env, "KNOWLEDGE", None) or {}
    if isinstance(knowledge, Mapping):
        for key in knowledge:
            if key not in KNOWLEDGE_KEYS:
                findings.append(Finding("warn", "knowledge.unknown_key", f"KNOWLEDGE 有未知键 {key!r}", "docs/spec/config-syntax.md"))
        for raw in _as_list(knowledge.get("source_roots")):
            if not Path(str(raw)).expanduser().exists():
                findings.append(Finding("warn", "knowledge.source_roots", f"源码根不存在：{raw}", "maintain-config"))
        for raw in _as_list(knowledge.get("api_docs")):
            text = str(raw)
            if "://" not in text and not (root / text).exists() and not Path(text).expanduser().exists():
                findings.append(Finding("warn", "knowledge.api_docs", f"API 文档路径不存在：{text}", "maintain-config"))
    return findings


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]
