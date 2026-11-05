"""OpenAPI (3.x / Swagger 2.0) → synthetic HTTP exchanges for the API-object freezer.

Each operation becomes one exchange with sample values built from ``example`` /
``default`` / ``enum`` or the schema type. Integer path parameters become ``1``
and UUID parameters a fixed UUID, so ``normalize_path`` yields the same
``{id}`` / ``{uuid}`` segments as recorded traffic and later captures merge into
the same asset. Other path parameters keep their ``{name}`` placeholder.
No network access; secured operations get a placeholder bearer header that the
sanitizer masks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
SAMPLE_UUID = "00000000-0000-4000-8000-000000000000"
PLACEHOLDER_BEARER = "Bearer openapi-import-placeholder"
_MAX_DEPTH = 5


@dataclass
class Exchange:
    method: str
    path: str  # OpenAPI path template, e.g. /orders/{orderId}
    url: str
    request_headers: dict[str, str]
    request_content: str | None
    response_status: int
    response_headers: dict[str, str]
    response_content: str | None
    operation_id: str
    tags: list[str]


def load_spec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ValueError("YAML spec needs PyYAML (`uv add pyyaml`), or convert the spec to JSON") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        raise ValueError(f"{path}: not an OpenAPI document (no `paths`)")
    return data


class _Resolver:
    def __init__(self, spec: Mapping[str, Any]) -> None:
        self.spec = spec

    def deref(self, node: Any, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(node, Mapping) and "$ref" in node:
            ref = str(node["$ref"])
            if not ref.startswith("#/") or ref in seen:
                return {}
            target: Any = self.spec
            for part in ref[2:].split("/"):
                target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, Mapping) else {}
            return self.deref(target, (*seen, ref))
        return node

    def sample(self, schema: Any, depth: int = 0, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(schema, Mapping) and "$ref" in schema:
            ref = str(schema["$ref"])
            if ref in seen:
                return None
            return self.sample(self.deref(schema), depth, (*seen, ref))
        if not isinstance(schema, Mapping):
            return None
        for key in ("example", "default"):
            if key in schema:
                return schema[key]
        if isinstance(schema.get("enum"), list) and schema["enum"]:
            return schema["enum"][0]
        for combo in ("allOf", "oneOf", "anyOf"):
            options = schema.get(combo)
            if isinstance(options, list) and options:
                if combo == "allOf":
                    merged: dict[str, Any] = {}
                    for part in options:
                        value = self.sample(part, depth, seen)
                        if isinstance(value, dict):
                            merged.update(value)
                    return merged
                return self.sample(options[0], depth, seen)
        kind = schema.get("type")
        if kind == "object" or (kind is None and "properties" in schema):
            if depth >= _MAX_DEPTH:
                return {}
            props = schema.get("properties") or {}
            return {str(name): self.sample(prop, depth + 1, seen) for name, prop in props.items()}
        if kind == "array":
            if depth >= _MAX_DEPTH:
                return []
            item = self.sample(schema.get("items") or {}, depth + 1, seen)
            return [] if item is None else [item]
        if kind == "integer":
            return 0
        if kind == "number":
            return 0
        if kind == "boolean":
            return False
        if kind == "string":
            fmt = schema.get("format")
            if fmt == "uuid":
                return SAMPLE_UUID
            if fmt == "date-time":
                return "2026-01-01T00:00:00Z"
            if fmt == "date":
                return "2026-01-01"
            return "string"
        return None


def _param_sample(resolver: _Resolver, param: Mapping[str, Any]) -> Any:
    if "example" in param:
        return param["example"]
    schema = param.get("schema") if "schema" in param else param  # Swagger 2 keeps type on the param
    return resolver.sample(schema)


def _path_value(resolver: _Resolver, param: Mapping[str, Any]) -> str | None:
    schema = resolver.deref(param.get("schema") if "schema" in param else param)
    kind = schema.get("type") if isinstance(schema, Mapping) else None
    fmt = schema.get("format") if isinstance(schema, Mapping) else None
    if kind == "integer" or kind == "number":
        return "1"
    if fmt == "uuid":
        return SAMPLE_UUID
    return None  # keep {name}


def _base_url(spec: Mapping[str, Any]) -> str:
    servers = spec.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], Mapping):
        url = str(servers[0].get("url") or "")
        if url.startswith("http"):
            return url.rstrip("/")
        return "http://openapi.local" + ("/" + url.strip("/") if url.strip("/") else "")
    host = spec.get("host")
    if host:
        scheme = (spec.get("schemes") or ["http"])[0]
        base_path = str(spec.get("basePath") or "").rstrip("/")
        return f"{scheme}://{host}{base_path}"
    return "http://openapi.local"


def _request_body(resolver: _Resolver, op: Mapping[str, Any], params: list[Mapping[str, Any]]) -> tuple[str | None, str]:
    body = resolver.deref(op.get("requestBody") or {})
    content = body.get("content") if isinstance(body, Mapping) else None
    if isinstance(content, Mapping) and content:
        for ctype in ("application/json", *content.keys()):
            media = content.get(ctype)
            if not isinstance(media, Mapping):
                continue
            if "example" in media:
                value = media["example"]
            else:
                value = resolver.sample(media.get("schema") or {})
            if ctype == "application/x-www-form-urlencoded" and isinstance(value, Mapping):
                return urlencode({k: "" if v is None else v for k, v in value.items()}), ctype
            if "json" in ctype or ctype.endswith("+json"):
                return json.dumps(value if value is not None else {}, ensure_ascii=False), "application/json"
            return None, ctype
    for param in params:  # Swagger 2.0 body parameter
        if param.get("in") == "body":
            return json.dumps(resolver.sample(param.get("schema") or {}) or {}, ensure_ascii=False), "application/json"
    return None, ""


def _response(resolver: _Resolver, op: Mapping[str, Any]) -> tuple[int, str | None]:
    responses = op.get("responses") or {}
    for code in sorted(str(c) for c in responses):
        if not code.startswith("2"):
            continue
        resp = resolver.deref(responses.get(code) or responses.get(int(code)) or {})
        status = int(code) if code.isdigit() else 200
        content = resp.get("content") if isinstance(resp, Mapping) else None
        if isinstance(content, Mapping):
            media = content.get("application/json") or next(iter(content.values()), None)
            if isinstance(media, Mapping):
                value = media.get("example", resolver.sample(media.get("schema") or {}))
                return status, json.dumps(value if value is not None else {}, ensure_ascii=False)
        if isinstance(resp, Mapping) and "schema" in resp:  # Swagger 2.0
            return status, json.dumps(resolver.sample(resp["schema"]) or {}, ensure_ascii=False)
        return status, None
    return 200, None


def iter_exchanges(
    spec: Mapping[str, Any],
    *,
    path_prefix: str = "",
    tags: Iterable[str] = (),
) -> list[Exchange]:
    resolver = _Resolver(spec)
    wanted_tags = {t for t in tags if t}
    base = _base_url(spec)
    global_security = spec.get("security")
    out: list[Exchange] = []
    for raw_path, item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(item, Mapping) or (path_prefix and not str(raw_path).startswith(path_prefix)):
            continue
        shared = [resolver.deref(p) for p in item.get("parameters") or []]
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, Mapping):
                continue
            op_tags = [str(t) for t in op.get("tags") or []]
            if wanted_tags and not wanted_tags.intersection(op_tags):
                continue
            params = shared + [resolver.deref(p) for p in op.get("parameters") or []]
            path = str(raw_path)
            query: dict[str, Any] = {}
            for param in params:
                if not isinstance(param, Mapping):
                    continue
                where, name = param.get("in"), str(param.get("name") or "")
                if where == "path" and name:
                    value = _path_value(resolver, param)
                    if value is not None:
                        path = path.replace("{" + name + "}", value)
                elif where == "query" and name:
                    sample = _param_sample(resolver, param)
                    query[name] = "" if sample is None else sample
            url = base + path + (("?" + urlencode(query, doseq=True)) if query else "")
            content, ctype = _request_body(resolver, op, params)
            headers: dict[str, str] = {}
            if ctype:
                headers["Content-Type"] = ctype
            security = op.get("security", global_security)
            if security:
                headers["Authorization"] = PLACEHOLDER_BEARER
            status, resp_content = _response(resolver, op)
            out.append(
                Exchange(
                    method=method.upper(),
                    path=str(raw_path),
                    url=url,
                    request_headers=headers,
                    request_content=content,
                    response_status=status,
                    response_headers={"Content-Type": "application/json"} if resp_content is not None else {},
                    response_content=resp_content,
                    operation_id=str(op.get("operationId") or f"{method} {raw_path}"),
                    tags=op_tags,
                )
            )
    return out
