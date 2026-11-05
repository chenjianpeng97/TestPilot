"""Path normalization, static filtering, and fingerprint helpers."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, urlsplit

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_INT_RE = re.compile(r"^\d+$")

# User requirement: never capture .js / .css. Also skip other common static blobs
# so SPA asset noise does not pollute api_objects. PDF/xlsx downloads are kept
# (path may look static but are API export routes).
STATIC_EXTENSIONS = frozenset(
    {
        ".js",
        ".mjs",
        ".cjs",
        ".css",
        ".map",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webm",
        ".mp3",
        ".wav",
    }
)

SKIP_METHODS = frozenset({"OPTIONS", "HEAD", "CONNECT"})
DEFAULT_TOOL = "recorder"


def split_url(url: str) -> tuple[str, str, dict[str, str]]:
    """Return ``(host, path, query_dict)`` from a full URL."""
    parts = urlsplit(url)
    host = parts.netloc
    path = parts.path or "/"
    query = {k: v for k, v in parse_qsl(parts.query, keep_blank_values=True)}
    return host, path, query


def normalize_path(path: str) -> str:
    """Normalize dynamic segments: integers → ``{id}``, UUIDs → ``{uuid}``."""
    if not path:
        return "/"
    # Drop query/fragment if a caller passed a raw URI path by mistake.
    path = path.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = "/" + path
    segments = path.split("/")
    out: list[str] = []
    for seg in segments:
        if not seg:
            out.append(seg)
            continue
        if _UUID_RE.match(seg):
            out.append("{uuid}")
        elif _INT_RE.match(seg):
            out.append("{id}")
        else:
            out.append(seg)
    normalized = "/".join(out)
    return normalized if normalized.startswith("/") else "/" + normalized


def path_extension(path: str) -> str:
    leaf = path.rsplit("/", 1)[-1]
    if "." not in leaf:
        return ""
    return "." + leaf.rsplit(".", 1)[-1].lower()


def is_static_request(
    *,
    path: str,
    content_type: str = "",
    response_content_type: str = "",
) -> bool:
    """True when the flow is a static .js/.css (or similar) asset."""
    ext = path_extension(path)
    if ext in {".js", ".mjs", ".cjs", ".css"}:
        return True
    if ext in STATIC_EXTENSIONS:
        return True
    for ct in (content_type, response_content_type):
        cl = (ct or "").split(";", 1)[0].strip().lower()
        if not cl:
            continue
        if cl in {"text/css", "text/javascript", "application/javascript", "application/x-javascript"}:
            return True
        if any(cl.startswith(p) for p in ("image/", "font/", "audio/", "video/")):
            return True
    return False


def skip_api_flow(
    *,
    method: str,
    url: str,
    request_content_type: str = "",
    response_content_type: str = "",
    include_host: str | None = None,
) -> str | None:
    """Return why this flow should not be frozen, or ``None`` to freeze it.

    Reasons: ``method`` / ``host`` / ``static`` (static also covers HTML document GETs).
    """
    method_u = (method or "").upper()
    if method_u in SKIP_METHODS:
        return "method"
    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    path = parts.path or "/"
    needle = (include_host or "").strip().lower() or None
    if needle and needle not in host:
        return "host"
    if is_static_request(
        path=path,
        content_type=request_content_type,
        response_content_type=response_content_type,
    ):
        return "static"
    if "text/html" in (response_content_type or "").lower() and method_u == "GET":
        return "static"
    return None


def body_keys(body: Any) -> list[str]:
    if isinstance(body, Mapping):
        return sorted(str(k) for k in body.keys())
    return []


def fingerprint(
    *,
    method: str,
    normalized_path: str,
    query_keys: Iterable[str],
    body_keys_: Iterable[str],
    files_keys_: Iterable[str] | None = None,
) -> str:
    q = ",".join(sorted(query_keys))
    b = ",".join(sorted(body_keys_))
    f = ",".join(sorted(str(k) for k in (files_keys_ or [])))
    if f:
        return f"{method.upper()} {normalized_path}?{q}|{b}|files:{f}"
    return f"{method.upper()} {normalized_path}?{q}|{b}"


def service_from_path(normalized_path: str) -> str:
    parts = [p for p in normalized_path.split("/") if p and not p.startswith("{")]
    return parts[0] if parts else "api"


def route_dir_segments(normalized_path: str) -> list[str]:
    """Directory segments under api_objects root (route tree, no leading empty)."""
    return [p for p in normalized_path.split("/") if p]


def infer_type(value: Any) -> str:
    if value is None:
        return "any"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "any"


def schema_from_mapping(
    values: Optional[Mapping[str, Any]],
    *,
    required: bool = False,
    tool: str = DEFAULT_TOOL,
) -> dict[str, Any]:
    stamp = (tool or DEFAULT_TOOL).strip() or DEFAULT_TOOL
    out: dict[str, Any] = {}
    for k, v in (values or {}).items():
        out[str(k)] = {
            "type": infer_type(v),
            "required": required,
            "note": f"captured by apps.{stamp}",
        }
    return out


def camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    s3 = re.sub(r"[^0-9a-zA-Z_]+", "_", s2)
    return s3.strip("_").lower()


def asset_var_name(method: str, normalized_path: str, major: int) -> str:
    parts = [p for p in normalized_path.split("/") if p and not p.startswith("{")]
    leaf = parts[-1] if parts else "root"
    base = camel_to_snake(leaf)
    if not base or not base[0].isalpha():
        base = f"route_{base}" if base else "route"
    return f"{base}_{method.lower()}_v{major}"
