"""``@tool`` manifest registry: argparse → JSON Schema + argv plan.

Discovery imports every ``apps/<name>/tool.py`` under the workspace root and
every ``tuner_testkit/apps/<name>/tool.py`` shipped with the kit. ``tool.py``
must stay import-safe (no DB / browser / proxy imports at module level) so
the catalog and the workbench can list tools without pulling heavy deps.

The manifest is deliberately protocol-neutral: it says *what* a tool is and
*how* to invoke it; who runs it (local CLI, workbench, a future cloud runner)
is not its concern.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PORT_RE = re.compile(r"^[a-z][a-z0-9-]*$")
ParserFactory = Callable[[], argparse.ArgumentParser]
RuntimeKind = Literal["job", "long_lived"]
Visibility = Literal["workbench", "local"]
ArgvPlanKind = Literal["option", "store_true", "store_false", "positional", "json_option"]

_REGISTRY: dict[str, "ToolSpec"] = {}
_discovered_roots: set[str] = set()
_kit_discovered = False


@dataclass
class ToolSpec:
    tool_id: str
    name: str
    module: str
    argv: list[str]
    summary: str = ""
    group: str = "general"
    destructive: bool = False
    timeout: int = 180
    runtime: RuntimeKind = "job"
    visibility: Visibility = "workbench"
    readme_path: str | None = None
    port: str | None = None  # port contract this app implements (docs/spec/ports.md), e.g. "log-source"
    origin: str = "workspace"  # "workspace" (apps/<name>) or "kit" (tuner_testkit.apps.<name>)
    parser_factory: ParserFactory | None = None
    json_params: tuple[str, ...] = ()
    hide_params: tuple[str, ...] = ()
    schema_overlay: dict[str, Any] | None = None
    params_schema: dict[str, Any] = field(default_factory=dict)
    argv_plan: list[dict[str, Any]] = field(default_factory=list)

    def refresh_from_parser(self) -> None:
        if self.parser_factory is None:
            return
        parser = self.parser_factory()
        self.argv_plan, self.params_schema = plan_and_schema(
            parser,
            json_params=self.json_params,
            hide_params=self.hide_params,
            schema_overlay=self.schema_overlay,
        )


def tool(
    *,
    tool_id: str,
    name: str,
    module: str,
    summary: str = "",
    group: str = "general",
    argv: list[str] | None = None,
    destructive: bool = False,
    timeout: int = 180,
    runtime: RuntimeKind = "job",
    visibility: Visibility = "workbench",
    readme_path: str | None = None,
    port: str | None = None,
    json_params: Iterable[str] = (),
    hide_params: Iterable[str] = (),
    schema_overlay: dict[str, Any] | None = None,
) -> Callable[[ParserFactory], ParserFactory]:
    """Register a CLI tool. Decorate an import-safe ``build_parser``.

    ``port`` declares that this workspace app is the adapter for a kit port
    contract (``docs/spec/ports.md``), e.g. ``port="log-source"``.
    """

    def decorator(factory: ParserFactory) -> ParserFactory:
        spec = register_tool(
            factory,
            tool_id=tool_id,
            name=name,
            module=module,
            summary=summary,
            group=group,
            argv=argv,
            destructive=destructive,
            timeout=timeout,
            runtime=runtime,
            visibility=visibility,
            readme_path=readme_path,
            port=port,
            json_params=json_params,
            hide_params=hide_params,
            schema_overlay=schema_overlay,
        )
        factory._tool_id = spec.tool_id  # type: ignore[attr-defined]
        return factory

    return decorator


def register_tool(
    factory: ParserFactory,
    *,
    tool_id: str,
    name: str,
    module: str,
    summary: str = "",
    group: str = "general",
    argv: list[str] | None = None,
    destructive: bool = False,
    timeout: int = 180,
    runtime: RuntimeKind = "job",
    visibility: Visibility = "workbench",
    readme_path: str | None = None,
    port: str | None = None,
    json_params: Iterable[str] = (),
    hide_params: Iterable[str] = (),
    schema_overlay: dict[str, Any] | None = None,
) -> ToolSpec:
    if not TOOL_ID_RE.fullmatch(tool_id):
        raise ValueError(f"invalid tool_id: {tool_id!r} (expected ^[a-z][a-z0-9_]*$)")
    if port is not None and not PORT_RE.fullmatch(port):
        raise ValueError(f"invalid port: {port!r} (expected ^[a-z][a-z0-9-]*$)")
    if ".." in module or not (module.startswith("apps.") or module.startswith("tuner_testkit.apps.")):
        raise ValueError(f"invalid tool module: {module!r} (expected apps.<name> or tuner_testkit.apps.<name>)")
    if runtime not in ("job", "long_lived"):
        raise ValueError(f"invalid runtime: {runtime!r}")
    if visibility not in ("workbench", "local"):
        raise ValueError(f"invalid visibility: {visibility!r}")
    prefix = list(argv) if argv is not None else ["python", "-m", module]
    spec = ToolSpec(
        tool_id=tool_id,
        name=name,
        module=module,
        argv=prefix,
        summary=summary,
        group=group,
        destructive=destructive,
        timeout=int(timeout),
        runtime=runtime,
        visibility=visibility,
        readme_path=readme_path,
        port=port,
        origin="kit" if module.startswith("tuner_testkit.") else "workspace",
        parser_factory=factory,
        json_params=tuple(json_params),
        hide_params=tuple(hide_params),
        schema_overlay=schema_overlay,
    )
    spec.refresh_from_parser()
    _REGISTRY[tool_id] = spec  # re-registration after reload wins
    return spec


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def discover(repo_root: str | Path | None = None, *, include_kit: bool = True) -> None:
    """Import ``apps/*/tool.py`` under *repo_root* and (once) the kit's own tool manifests."""
    global _kit_discovered
    root = Path(repo_root) if repo_root is not None else _repo_root()
    key = str(root.resolve())
    if key not in _discovered_roots:
        _discovered_roots.add(key)
        _import_workspace_tools(root)
    if include_kit and not _kit_discovered:
        _kit_discovered = True
        _import_kit_tools()


def _import_workspace_tools(root: Path) -> None:
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return
    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
    _purge_foreign_package("apps", apps_dir)
    for child in sorted(apps_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        tool_file = child / "tool.py"
        if not tool_file.is_file():
            continue
        mod_name = f"apps.{child.name}.tool"
        existing = sys.modules.get(mod_name)
        if existing is not None and Path(getattr(existing, "__file__", "") or "").resolve() == tool_file.resolve():
            importlib.reload(existing)
            continue
        if existing is not None:
            # A different workspace's apps.<name>.tool is cached: load by path instead.
            _exec_module(f"_tuner_tool_{child.name}_{abs(hash(str(tool_file.resolve())))}", tool_file)
            continue
        importlib.import_module(mod_name)


def _purge_foreign_package(name: str, expected_dir: Path) -> None:
    """Drop cached ``name`` / ``name.*`` modules that were imported from another workspace."""
    pkg = sys.modules.get(name)
    if pkg is None:
        return
    paths = [Path(p).resolve() for p in (getattr(pkg, "__path__", None) or [])]
    if paths and all(p == expected_dir.resolve() for p in paths):
        return
    for mod_name in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        sys.modules.pop(mod_name, None)


def _import_kit_tools() -> None:
    kit_apps = Path(__file__).resolve().parent.parent / "apps"
    if not kit_apps.is_dir():
        return
    for child in sorted(kit_apps.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if not (child / "tool.py").is_file():
            continue
        mod_name = f"tuner_testkit.apps.{child.name}.tool"
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
        else:
            importlib.import_module(mod_name)


def _exec_module(mod_name: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise


def export_tools(repo_root: str | Path | None = None, *, include_kit: bool = True) -> list[dict[str, Any]]:
    """All registered tools as catalog rows (sorted by ``tool_id``)."""
    discover(repo_root, include_kit=include_kit)
    return [spec_to_dict(spec) for spec in sorted(_REGISTRY.values(), key=lambda item: item.tool_id)]


def get_tool(tool_id: str, repo_root: str | Path | None = None) -> ToolSpec:
    discover(repo_root)
    spec = _REGISTRY.get(tool_id)
    if spec is None:
        raise KeyError(f"unknown tool {tool_id!r}; known: {sorted(_REGISTRY)}")
    return spec


def spec_to_dict(spec: ToolSpec) -> dict[str, Any]:
    return {
        "tool_id": spec.tool_id,
        "name": spec.name,
        "summary": spec.summary,
        "group": spec.group,
        "module": spec.module,
        "origin": spec.origin,
        "argv": list(spec.argv),
        "params_schema": spec.params_schema,
        "argv_plan": list(spec.argv_plan),
        "destructive": spec.destructive,
        "timeout": spec.timeout,
        "runtime": spec.runtime,
        "visibility": spec.visibility,
        "readme_path": spec.readme_path,
        "port": spec.port,
    }


def reset_registry_for_tests() -> None:
    """Test helper: clear registration so discover can run again."""
    global _kit_discovered
    _REGISTRY.clear()
    _discovered_roots.clear()
    _kit_discovered = False


def _repo_root() -> Path:
    from tuner_testkit.project import project_root

    return project_root()


# ---------------------------------------------------------------------------
# argparse → JSON Schema + argv plan
# ---------------------------------------------------------------------------
_TYPE_MAP: dict[Any, str] = {int: "integer", float: "number", bool: "boolean", str: "string"}


def _json_type_for(action: argparse.Action) -> str:
    conv = getattr(action, "type", None)
    if conv in _TYPE_MAP:
        return _TYPE_MAP[conv]
    return "string"


def plan_and_schema(
    parser: argparse.ArgumentParser,
    *,
    json_params: tuple[str, ...] = (),
    hide_params: tuple[str, ...] = (),
    schema_overlay: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Introspect an argparse parser into (``argv_plan``, JSON Schema)."""
    json_set = set(json_params)
    hide_set = set(hide_params) | {"help"}
    plan: list[dict[str, Any]] = []
    properties: dict[str, Any] = {}
    required: list[str] = []

    for action in parser._actions:  # noqa: SLF001 — argparse has no public action list
        dest = getattr(action, "dest", None)
        if not dest or dest in hide_set or dest == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            continue
        option_strings = list(getattr(action, "option_strings", []) or [])
        flag = next((s for s in option_strings if s.startswith("--")), option_strings[0] if option_strings else None)
        help_text = (getattr(action, "help", None) or "")
        description = help_text if help_text != argparse.SUPPRESS else ""
        default = getattr(action, "default", None)
        has_default = default is not None and default != argparse.SUPPRESS

        if dest in json_set:
            plan.append({"key": dest, "kind": "json_option", "flag": flag or f"--{dest.replace('_', '-')}"})
            prop: dict[str, Any] = {"type": "object"}
            if description:
                prop["description"] = description
            properties[dest] = prop
            continue

        action_type = type(action).__name__
        if action_type == "_StoreTrueAction" or (getattr(action, "const", None) is True and getattr(action, "nargs", None) == 0):
            plan.append({"key": dest, "kind": "store_true", "flag": flag or f"--{dest.replace('_', '-')}"})
            prop = {"type": "boolean", "default": False}
            if description:
                prop["description"] = description
            properties[dest] = prop
            continue
        if action_type == "_StoreFalseAction":
            plan.append({"key": dest, "kind": "store_false", "flag": flag or f"--{dest.replace('_', '-')}"})
            prop = {"type": "boolean", "default": True}
            if description:
                prop["description"] = description
            properties[dest] = prop
            continue

        nargs = getattr(action, "nargs", None)
        json_type = _json_type_for(action)
        if flag is None:
            variadic = nargs in ("*", "+", argparse.REMAINDER)
            plan.append({"key": dest, "kind": "positional", "variadic": variadic})
            if variadic:
                prop = {"type": "array", "items": {"type": json_type}}
            else:
                prop = {"type": json_type}
            if description:
                prop["description"] = description
            if getattr(action, "choices", None):
                prop["enum"] = list(action.choices)
            properties[dest] = prop
            if nargs == "+" or (getattr(action, "required", True) and nargs not in ("*", "?")):
                required.append(dest)
            continue

        plan.append({"key": dest, "kind": "option", "flag": flag})
        if nargs in ("*", "+"):
            prop = {"type": "array", "items": {"type": json_type}}
        else:
            prop = {"type": json_type}
        if description:
            prop["description"] = description
        if getattr(action, "choices", None):
            prop["enum"] = list(action.choices)
        if has_default and nargs not in ("*", "+"):
            prop["default"] = default if isinstance(default, (int, float, bool, str)) else str(default)
        properties[dest] = prop
        if getattr(action, "required", False):
            required.append(dest)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    if schema_overlay:
        schema = {**schema, **schema_overlay}
        if "properties" in schema_overlay:
            schema["properties"] = {**properties, **schema_overlay["properties"]}
    return plan, schema


# ---------------------------------------------------------------------------
# Params → argv (the runner half of the contract)
# ---------------------------------------------------------------------------
def validate_params(schema: dict[str, Any], params: dict[str, Any]) -> list[str]:
    """Minimal JSON-Schema-ish validation: required keys, unknown keys, scalar types, enums."""
    errors: list[str] = []
    properties: dict[str, Any] = schema.get("properties", {}) or {}
    for key in schema.get("required", []) or []:
        if key not in params or params[key] in (None, ""):
            errors.append(f"missing required parameter: {key}")
    if not schema.get("additionalProperties", True):
        for key in params:
            if key not in properties:
                errors.append(f"unknown parameter: {key}")
    for key, value in params.items():
        prop = properties.get(key)
        if prop is None or value is None:
            continue
        expected = prop.get("type")
        if expected == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
            if not (isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip())):
                errors.append(f"{key}: expected integer, got {value!r}")
        elif expected == "number" and not isinstance(value, (int, float)):
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{key}: expected number, got {value!r}")
        elif expected == "boolean" and not isinstance(value, bool):
            if not (isinstance(value, str) and value.lower() in {"true", "false", "1", "0", "yes", "no"}):
                errors.append(f"{key}: expected boolean, got {value!r}")
        elif expected == "array" and not isinstance(value, (list, tuple)):
            errors.append(f"{key}: expected array, got {value!r}")
        elif expected == "object" and not isinstance(value, dict):
            errors.append(f"{key}: expected object, got {value!r}")
        enum = prop.get("enum")
        if enum and value not in enum and str(value) not in [str(e) for e in enum]:
            errors.append(f"{key}: {value!r} not in {enum}")
    return errors


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_argv(spec: ToolSpec | dict[str, Any], params: dict[str, Any] | None = None) -> list[str]:
    """Turn ``params`` into a full command line using the tool's ``argv`` prefix and ``argv_plan``."""
    import json as _json

    data = spec_to_dict(spec) if isinstance(spec, ToolSpec) else spec
    params = dict(params or {})
    argv: list[str] = list(data["argv"])
    positionals: list[str] = []
    for step in data.get("argv_plan", []):
        key = step["key"]
        if key not in params or params[key] is None:
            continue
        value = params[key]
        kind = step["kind"]
        if kind == "store_true":
            if _truthy(value):
                argv.append(step["flag"])
        elif kind == "store_false":
            if not _truthy(value):
                argv.append(step["flag"])
        elif kind == "json_option":
            argv.extend([step["flag"], value if isinstance(value, str) else _json.dumps(value, ensure_ascii=False)])
        elif kind == "positional":
            if step.get("variadic") and isinstance(value, (list, tuple)):
                positionals.extend(str(v) for v in value)
            else:
                positionals.append(str(value))
        else:  # option
            if isinstance(value, (list, tuple)):
                argv.append(step["flag"])
                argv.extend(str(v) for v in value)
            elif value != "":
                argv.extend([step["flag"], str(value)])
    argv.extend(positionals)
    return argv
