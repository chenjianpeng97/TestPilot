"""Structured, sanitized capture from one HTTP exchange."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from email import message_from_bytes
from email.policy import HTTP
from typing import Any, Mapping
from urllib.parse import parse_qsl

from .normalize import DEFAULT_TOOL, body_keys, fingerprint, normalize_path, schema_from_mapping, split_url
from .sanitize import detect_auth_strategy, sanitize_headers, sanitize_mapping

_BOUNDARY_RE = re.compile(r"boundary=(?P<q>\"([^\"]+)\"|([^;\s]+))", re.I)
_NAME_RE = re.compile(r'name="([^"]+)"', re.I)
_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.I)


@dataclass(frozen=True)
class Capture:
    method: str
    host: str
    path: str
    normalized_path: str
    query: dict[str, Any]
    request_headers: dict[str, str]
    request_body: Any
    body_format: str  # "json" | "form" | "multipart" | "none"
    response_status: int
    response_headers: dict[str, str]
    response_body: Any
    response_is_json: bool
    auth_required: bool
    auth_strategy: str
    auth_source: str
    query_schema: dict[str, Any] = field(default_factory=dict)
    body_schema: dict[str, Any] = field(default_factory=dict)
    files_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def fp(self) -> str:
        return fingerprint(
            method=self.method,
            normalized_path=self.normalized_path,
            query_keys=self.query.keys(),
            body_keys_=body_keys(self.request_body),
            files_keys_=self.files_schema.keys(),
        )


def _parse_multipart(
    raw: bytes, content_type: str, *, tool: str = DEFAULT_TOOL
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Parse multipart/form-data; never keep file bytes — only field names.

    Returns ``(text_fields, files_schema, body_format)``.
    """
    m = _BOUNDARY_RE.search(content_type or "")
    if not m or not raw:
        return {}, {}, "none"
    boundary = (m.group(2) or m.group(3) or "").strip()
    if not boundary:
        return {}, {}, "none"

    # Wrap as a MIME message so stdlib can split parts.
    envelope = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n\r\n".encode("utf-8")
        + raw
    )
    try:
        msg = message_from_bytes(envelope, policy=HTTP)
    except Exception:  # noqa: BLE001 -- a malformed multipart body is frozen without fields, never breaks capture
        return {}, {}, "none"

    text_fields: dict[str, Any] = {}
    files_schema: dict[str, Any] = {}

    parts = list(msg.iter_parts()) if msg.is_multipart() else []
    if not parts and msg.get_content_maintype() == "multipart":
        # Fallback: some payloads parse as multipart without iter_parts yielding
        parts = [p for p in msg.walk() if p is not msg]

    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        cd = part.get("Content-Disposition", "") or ""
        name_m = _NAME_RE.search(cd)
        if not name_m:
            continue
        name = name_m.group(1)
        filename_m = _FILENAME_RE.search(cd)
        if filename_m or part.get_filename():
            raw_name = (filename_m.group(1) if filename_m else part.get_filename()) or ""
            note = f"captured by apps.{tool} (file field; content discarded)"
            if raw_name:
                note = f"captured by apps.{tool}; sample filename={raw_name!s}"
            files_schema[name] = {
                "type": "file",
                "required": False,
                "note": note,
            }
            continue
        # Text field — decode payload, discard binary-looking values as empty string
        payload = part.get_payload(decode=True)
        if payload is None:
            payload_s = part.get_payload()
            text = "" if payload_s is None else str(payload_s)
        else:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = ""
        text_fields[name] = text

    if not text_fields and not files_schema:
        return {}, {}, "none"
    return sanitize_mapping(text_fields), files_schema, "multipart"


def _parse_body(
    raw: bytes | str | None, content_type: str, *, tool: str = DEFAULT_TOOL
) -> tuple[Any, str, dict[str, Any]]:
    """Return ``(body, body_format, files_schema)``.

    ``body_format`` is json|form|multipart|none. ``files_schema`` is only
    populated for multipart captures (file field names; no file bytes).
    """
    empty_files: dict[str, Any] = {}
    if raw is None:
        return None, "none", empty_files

    ct = (content_type or "").split(";", 1)[0].strip().lower()
    ct_full = content_type or ""

    # Multipart first — may be binary-ish; do not utf-8-decode whole body.
    if "multipart/form-data" in ct_full.lower():
        raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8", errors="replace")
        text_fields, files_schema, fmt = _parse_multipart(raw_bytes, ct_full, tool=tool)
        if fmt == "multipart":
            return text_fields, "multipart", files_schema
        return None, "none", empty_files

    if isinstance(raw, bytes):
        if not raw:
            return None, "none", empty_files
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, "none", empty_files
    else:
        text = raw
        if not text:
            return None, "none", empty_files

    stripped = text.lstrip()

    if "json" in ct or stripped.startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, "none", empty_files
        if isinstance(data, Mapping):
            return sanitize_mapping(data), "json", empty_files
        return data, "json", empty_files

    is_form_ct = ct in {
        "application/x-www-form-urlencoded",
        "application/x-www-form-urlencoded;charset=utf-8",
    } or ct.startswith("application/x-www-form-urlencoded")
    looks_like_form = ("=" in text) and (not stripped.startswith(("{", "["))) and ("json" not in ct)
    if is_form_ct or looks_like_form:
        parsed = {k: v for k, v in parse_qsl(text, keep_blank_values=True)}
        if parsed:
            return sanitize_mapping(parsed), "form", empty_files

    return None, "none", empty_files


def _parse_response_body(raw: bytes | str | None, content_type: str) -> tuple[Any, bool]:
    if raw is None:
        return None, False
    if isinstance(raw, bytes):
        if not raw:
            return None, False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, False
    else:
        text = raw
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if "json" in ct or text.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, False
        if isinstance(data, Mapping):
            return sanitize_mapping(data), True
        return data, True
    return None, False


def build_capture(
    *,
    method: str,
    url: str,
    request_headers: Mapping[str, Any],
    request_content: bytes | str | None,
    response_status: int,
    response_headers: Mapping[str, Any],
    response_content: bytes | str | None,
    tool: str = DEFAULT_TOOL,
) -> Capture:
    host, path, query = split_url(url)
    npath = normalize_path(path)
    req_ct = ""
    for k, v in request_headers.items():
        if str(k).lower() == "content-type":
            req_ct = str(v)
            break
    resp_ct = ""
    for k, v in response_headers.items():
        if str(k).lower() == "content-type":
            resp_ct = str(v)
            break

    stamp = (tool or DEFAULT_TOOL).strip() or DEFAULT_TOOL
    body, parsed_format, files_schema = _parse_body(request_content, req_ct, tool=stamp)
    method_u = method.upper()
    if method_u == "GET":
        body = None
        body_format = "json"  # APIModel default; ignored for GET at execute time
        files_schema = {}
    elif parsed_format == "form":
        body_format = "form"
    elif parsed_format == "multipart":
        body_format = "multipart"
    elif parsed_format == "json":
        body_format = "json"
    else:
        # Unknown / empty body: keep json default for non-file POSTs
        body_format = "json"

    resp_body, resp_is_json = _parse_response_body(response_content, resp_ct)
    auth_required, auth_strategy, auth_source = detect_auth_strategy(request_headers)

    safe_query = sanitize_mapping(query)
    return Capture(
        method=method_u,
        host=host,
        path=path.split("?", 1)[0],
        normalized_path=npath,
        query=safe_query,
        request_headers=sanitize_headers(request_headers),
        request_body=body,
        body_format=body_format,
        response_status=int(response_status),
        response_headers=sanitize_headers(response_headers),
        response_body=resp_body,
        response_is_json=resp_is_json,
        auth_required=auth_required,
        auth_strategy=auth_strategy,
        auth_source=auth_source,
        query_schema=schema_from_mapping(safe_query, required=False, tool=stamp),
        body_schema=schema_from_mapping(
            body if isinstance(body, Mapping) else {}, required=False, tool=stamp
        ),
        files_schema=dict(files_schema or {}),
    )
