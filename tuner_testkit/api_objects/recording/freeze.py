"""Freeze captures into ``api_objects`` route-tree files."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .capture import Capture
from .codegen import build_assert_ops, build_extract_ops, merge_capture_into_schemas, render_api_model_source
from .normalize import DEFAULT_TOOL, route_dir_segments

try:
    from ..auth import ensure_auth_file
except Exception:  # noqa: BLE001 — freeze must work even if package auth import fails
    def ensure_auth_file(outputs_dir: Path) -> Path:  # type: ignore[misc]
        return outputs_dir / "auth.py"

_ASSET_FILE_RE = re.compile(r"^(?P<method>[A-Z]+)\.v(?P<major>\d+)\.py$")
_ASSET_FILE_ALT_RE = re.compile(r"^(?P<method>[A-Z]+)_v(?P<major>\d+)\.py$")
_EXPORT_KINDS = (
    "recording export",
    "apps.recorder export",
    "apps.api_recorder export",
)


@dataclass(frozen=True)
class FreezeResult:
    action: str  # "created" | "updated" | "skipped"
    path: Path
    method: str
    normalized_path: str
    detail: str = ""
    major: int = 1
    """Asset major version, so side-car writers can align their ``v<N>`` suffix."""


def ensure_package_inits(root: Path, segments: list[str]) -> None:
    """Create directories and empty ``__init__.py`` along the route tree."""
    root.mkdir(parents=True, exist_ok=True)
    init = root / "__init__.py"
    if not init.exists():
        init.write_text('"""Route-aligned APIModel assets."""\n', encoding="utf-8")

    cur = root
    for seg in segments:
        cur = cur / seg
        cur.mkdir(parents=True, exist_ok=True)
        pkg_init = cur / "__init__.py"
        if not pkg_init.exists():
            pkg_init.write_text("", encoding="utf-8")


def asset_filename(method: str, major: int) -> str:
    """Per ``api-objects-syntax.md``: ``<METHOD>.v<MAJOR>.py``."""
    return f"{method.upper()}.v{major}.py"


def find_existing_asset(route_dir: Path, method: str) -> Optional[tuple[Path, int]]:
    """Return ``(path, major)`` for the lowest major version of this method."""
    if not route_dir.is_dir():
        return None
    found: list[tuple[int, Path]] = []
    for p in route_dir.iterdir():
        if not p.is_file():
            continue
        m = _ASSET_FILE_RE.match(p.name) or _ASSET_FILE_ALT_RE.match(p.name)
        if not m:
            continue
        if m.group("method").upper() != method.upper():
            continue
        found.append((int(m.group("major")), p))
    if not found:
        return None
    found.sort(key=lambda x: x[0])
    major, path = found[0]
    return path, major


def _literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        out: dict[str, Any] = {}
        for k, v in zip(node.keys, node.values, strict=True):
            if k is None:
                continue
            out[str(_literal(k))] = _literal(v)
        return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value  # type: ignore[operator]
    raise ValueError(f"unsupported literal: {ast.dump(node)}")


def _call_kwargs(call: ast.Call) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        out[kw.arg] = kw.value
    return out


def parse_existing_asset(path: Path) -> dict[str, Any]:
    """Best-effort AST parse of an APIModel asset file."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not node.targets:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "APIModel":
            continue
        raw = _call_kwargs(node.value)
        result: dict[str, Any] = {"var_target": None}
        t0 = node.targets[0]
        if isinstance(t0, ast.Name):
            result["var_target"] = t0.id
        for key in ("id", "name", "description", "method", "path", "body_format"):
            if key in raw:
                try:
                    result[key] = _literal(raw[key])
                except ValueError:
                    pass
        for key in ("query_schema", "body_schema", "files_schema", "response_hints", "headers_policy", "auth_policy"):
            if key in raw:
                try:
                    result[key] = _literal(raw[key])
                except ValueError:
                    result[key] = {}
        if "asserts" in raw and isinstance(raw["asserts"], ast.List):
            asserts = []
            for elt in raw["asserts"].elts:
                if isinstance(elt, ast.Call):
                    kw = _call_kwargs(elt)
                    try:
                        asserts.append({k: _literal(v) for k, v in kw.items()})
                    except ValueError:
                        continue
            result["asserts"] = asserts
        if "extracts" in raw and isinstance(raw["extracts"], ast.List):
            extracts = []
            for elt in raw["extracts"].elts:
                if isinstance(elt, ast.Call):
                    kw = _call_kwargs(elt)
                    try:
                        extracts.append({k: _literal(v) for k, v in kw.items()})
                    except ValueError:
                        continue
            result["extracts"] = extracts
        return result
    raise ValueError(f"no APIModel assignment found in {path}")


def _merge_ops(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for op in existing + incoming:
        key = tuple(op.get(f) for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(op)
    return out


def write_init_exports(route_dir: Path, filename: str, var_name: str) -> None:
    """Keep directory ``__init__.py`` re-exporting the asset via importlib."""
    init_path = route_dir / "__init__.py"
    loader_block = f'''
# --- recording export: {filename} ---
from importlib.machinery import SourceFileLoader
from pathlib import Path as _Path

_{var_name}_mod = SourceFileLoader(
    "{var_name}_mod",
    str(_Path(__file__).resolve().parent / "{filename}"),
).load_module()
{var_name} = _{var_name}_mod.{var_name}
# --- end export: {filename} ---
'''
    existing = init_path.read_text(encoding="utf-8") if init_path.exists() else ""
    for kind in _EXPORT_KINDS:
        pattern = re.compile(
            rf"# --- {re.escape(kind)}: {re.escape(filename)} ---.*?# --- end export: {re.escape(filename)} ---\n?",
            re.S,
        )
        existing = pattern.sub("", existing)
    init_path.write_text(existing.rstrip() + "\n" + loader_block, encoding="utf-8")


class ApiObjectFreezer:
    """Create/update route-aligned API Objects under ``outputs_dir``."""

    def __init__(self, outputs_dir: Path, *, tool: str = DEFAULT_TOOL) -> None:
        self.outputs_dir = outputs_dir.resolve()
        self.tool = (tool or DEFAULT_TOOL).strip() or DEFAULT_TOOL
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        ensure_package_inits(self.outputs_dir, [])
        # Shared auth module (Postman-style); never overwrite a customized file.
        ensure_auth_file(self.outputs_dir)

    def freeze(self, capture: Capture) -> FreezeResult:
        segments = route_dir_segments(capture.normalized_path)
        if not segments:
            return FreezeResult(
                action="skipped",
                path=self.outputs_dir,
                method=capture.method,
                normalized_path=capture.normalized_path,
                detail="empty path",
                major=0,
            )

        ensure_package_inits(self.outputs_dir, segments)
        route_dir = self.outputs_dir.joinpath(*segments)
        existing = find_existing_asset(route_dir, capture.method)

        if existing is None:
            major = 1
            filename = asset_filename(capture.method, major)
            target = route_dir / filename
            var, source = render_api_model_source(capture=capture, major=major, tool=self.tool)
            target.write_text(source, encoding="utf-8")
            write_init_exports(route_dir, filename, var)
            return FreezeResult(
                action="created",
                path=target,
                method=capture.method,
                normalized_path=capture.normalized_path,
                major=major,
            )

        path, major = existing
        try:
            parsed = parse_existing_asset(path)
        except ValueError:
            # Unreadable / hand-edited beyond parse — rewrite v1 file in place.
            parsed = {}

        q_schema, b_schema, f_schema = merge_capture_into_schemas(
            existing_query=parsed.get("query_schema") or {},
            existing_body=parsed.get("body_schema") or {},
            existing_files=parsed.get("files_schema") or {},
            capture=capture,
        )
        asserts = _merge_ops(
            list(parsed.get("asserts") or []),
            build_assert_ops(capture),
            key_fields=("jsonpath", "operator"),
        )
        extracts = _merge_ops(
            list(parsed.get("extracts") or []),
            build_extract_ops(capture),
            key_fields=("jsonpath", "variable_name"),
        )

        from dataclasses import replace

        # Prefer multipart over form over json when either side used it.
        existing_fmt = parsed.get("body_format") or "json"
        if capture.body_format == "multipart" or existing_fmt == "multipart":
            capture_for_render = replace(
                capture,
                body_format="multipart",
                files_schema=f_schema or capture.files_schema,
            )
        elif capture.body_format == "form" or existing_fmt == "form":
            capture_for_render = replace(capture, body_format="form")
        else:
            capture_for_render = capture

        var, source = render_api_model_source(
            capture=capture_for_render,
            major=major,
            query_schema=q_schema,
            body_schema=b_schema,
            files_schema=f_schema,
            asserts=asserts,
            extracts=extracts,
            name=parsed.get("name"),
            tool=self.tool,
        )
        # Always write canonical METHOD.vN.py (migrate from METHOD_vN.py if needed).
        canonical = route_dir / asset_filename(capture.method, major)
        canonical.write_text(source, encoding="utf-8")
        if path.resolve() != canonical.resolve() and path.exists():
            path.unlink()
        write_init_exports(route_dir, canonical.name, var)
        return FreezeResult(
            action="updated",
            path=canonical,
            method=capture.method,
            normalized_path=capture.normalized_path,
            detail=f"merged into v{major}",
            major=major,
        )
