from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import requests

from tuner_testkit.config import get_test_base_url
from tuner_testkit.logging import log_api_call

from .errors import AuthPolicyError, FilesPolicyError, HeadersPolicyError
from .model import ApiResponse, APIModel


_SENSITIVE_HEADER_RE = re.compile(r"(authorization|cookie|set-cookie|token|secret|password|session)", re.IGNORECASE)

# 响应/入参脱敏：token/password 等敏感字段只留掩码，绝不落盘明文
_SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|session|cookie)", re.IGNORECASE)
_SENSITIVE_JSON_VALUE_RE = re.compile(
    r'("[^"]*(?:token|secret|password|session)[^"]*"\s*:\s*")([^"]*)(")',
    re.IGNORECASE,
)


def _sanitize_params(params: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        k: ("***" if _SENSITIVE_KEY_RE.search(str(k)) else v)
        for k, v in (params or {}).items()
    }


def _response_snippet(text: str, *, limit: int = 300) -> str:
    snippet = _SENSITIVE_JSON_VALUE_RE.sub(r"\1***\3", text or "")
    snippet = " ".join(snippet.split())  # 压成单行，便于 grep
    return snippet[:limit] + ("…" if len(snippet) > limit else "")


def _sanitize_headers(headers: Mapping[str, Any], *, forbidden: Mapping[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    forbidden_lc = {str(k).lower() for k in forbidden}
    for k, v in headers.items():
        ks = str(k)
        if str(k).lower() in forbidden_lc:
            raise HeadersPolicyError(f"Header {ks!r} is forbidden")
        if _SENSITIVE_HEADER_RE.search(ks):
            # Defensive: even if a key isn't explicitly listed, reject risky keys.
            raise HeadersPolicyError(f"Header {ks!r} looks sensitive and is not allowed to be persisted")
        out[ks] = str(v)
    return out


def _strip_content_type(headers: Dict[str, str]) -> Dict[str, str]:
    """Let requests set multipart boundary; drop any caller Content-Type."""
    return {k: v for k, v in headers.items() if k.lower() != "content-type"}


def _filename_from_path(path: str | Path) -> str:
    return Path(path).name or "upload.bin"


def normalize_file_input(value: Any, *, field_name: str) -> Tuple[str, Any, Optional[str]]:
    """Normalize a FileInput into ``(filename, content_or_fileobj, content_type?)``.

    Accepted shapes:
      * ``"path/to.xlsx"`` / ``Path(...)``
      * ``(filename, bytes|path|Path, content_type?)``
      * ``{"filename": ..., "content"|"path": ..., "content_type": ...}``
    """
    if value is None:
        raise FilesPolicyError(f"file field {field_name!r} is None")

    if isinstance(value, (str, Path)):
        path = Path(value)
        if not path.is_file():
            raise FilesPolicyError(f"file field {field_name!r}: path not found: {path}")
        return _filename_from_path(path), path.open("rb"), None

    if isinstance(value, (bytes, bytearray)):
        return f"{field_name}.bin", bytes(value), "application/octet-stream"

    if isinstance(value, tuple):
        if len(value) < 2:
            raise FilesPolicyError(
                f"file field {field_name!r}: tuple must be (filename, content[, content_type])"
            )
        filename = str(value[0])
        content = value[1]
        content_type = str(value[2]) if len(value) >= 3 and value[2] is not None else None
        if isinstance(content, (str, Path)):
            path = Path(content)
            if not path.is_file():
                raise FilesPolicyError(f"file field {field_name!r}: path not found: {path}")
            return filename, path.open("rb"), content_type
        if isinstance(content, (bytes, bytearray)):
            return filename, bytes(content), content_type
        # Already a file-like object
        return filename, content, content_type

    if isinstance(value, Mapping):
        filename = str(value.get("filename") or value.get("name") or f"{field_name}.bin")
        content_type = value.get("content_type") or value.get("mime")
        content_type_s = str(content_type) if content_type is not None else None
        if "content" in value:
            content = value["content"]
            if isinstance(content, (str, Path)) and Path(str(content)).is_file():
                return filename, Path(content).open("rb"), content_type_s
            if isinstance(content, (bytes, bytearray)):
                return filename, bytes(content), content_type_s
            return filename, content, content_type_s
        if "path" in value:
            path = Path(value["path"])
            if not path.is_file():
                raise FilesPolicyError(f"file field {field_name!r}: path not found: {path}")
            return filename or _filename_from_path(path), path.open("rb"), content_type_s
        raise FilesPolicyError(
            f"file field {field_name!r}: mapping must include 'content' or 'path'"
        )

    raise FilesPolicyError(
        f"file field {field_name!r}: unsupported FileInput type {type(value).__name__}"
    )


def build_requests_files(files: Mapping[str, Any] | None) -> Optional[Dict[str, Any]]:
    if not files:
        return None
    out: Dict[str, Any] = {}
    for field_name, raw in files.items():
        filename, content, content_type = normalize_file_input(raw, field_name=str(field_name))
        if content_type:
            out[str(field_name)] = (filename, content, content_type)
        else:
            out[str(field_name)] = (filename, content)
    return out


@dataclass
class ApiClient:
    base_url: str
    session: requests.Session = field(default_factory=requests.Session)

    @classmethod
    def default(cls) -> "ApiClient":
        return cls(base_url=get_test_base_url())

    def request(
        self,
        *,
        model: APIModel,
        query: Mapping[str, Any],
        json_body: Any,
        headers: Mapping[str, Any],
        auth: Mapping[str, Any],
        timeout: Optional[float],
        files: Optional[Mapping[str, Any]] = None,
    ) -> ApiResponse:
        url = f"{self.base_url.rstrip('/')}{model.path}"

        hp = model.headers_policy or {}
        forbidden = [str(x) for x in hp.get("forbidden", [])]

        # model.Invocation already enforces allowlist. Here we do a final forbidden/sensitive check.
        sanitized_headers = _sanitize_headers(headers, forbidden={h: True for h in forbidden})

        # Auth injection (runtime only)
        ap = model.auth_policy or {}
        required = bool(ap.get("required", False))
        strategy = ap.get("strategy", "none")

        if required and strategy in ("bearer_token", "cookie_session"):
            if strategy == "bearer_token":
                token = auth.get("bearer_token")
                if not token:
                    raise AuthPolicyError("Missing auth.bearer_token for bearer_token strategy")
                sanitized_headers["Authorization"] = f"Bearer {token}"
            elif strategy == "cookie_session":
                cookie = auth.get("cookie")
                if not cookie:
                    raise AuthPolicyError("Missing auth.cookie for cookie_session strategy")
                sanitized_headers["Cookie"] = str(cookie)
        elif required and strategy not in ("bearer_token", "cookie_session", "none"):
            raise AuthPolicyError(f"Unsupported auth strategy: {strategy!r}")

        body_format = (getattr(model, "body_format", "json") or "json").lower()
        if body_format == "multipart":
            sanitized_headers = _strip_content_type(sanitized_headers)

        # requests params
        kwargs: Dict[str, Any] = {
            "method": model.method.upper(),
            "url": url,
            "params": dict(query or {}),
            "headers": sanitized_headers,
            "timeout": timeout,
        }

        file_fields_log: Optional[Dict[str, str]] = None
        if model.method.upper() != "GET":
            if body_format == "form":
                kwargs["data"] = json_body if json_body is not None else {}
            elif body_format == "multipart":
                kwargs["data"] = json_body if isinstance(json_body, dict) else ({} if json_body is None else json_body)
                built = build_requests_files(files)
                if built:
                    kwargs["files"] = built
                    # Log filenames without re-opening paths: prefer declared names
                    file_fields_log = {}
                    for fk, fv in (files or {}).items():
                        if isinstance(fv, (str, Path)):
                            file_fields_log[str(fk)] = os.path.basename(str(fv))
                        elif isinstance(fv, tuple) and fv:
                            file_fields_log[str(fk)] = str(fv[0])
                        elif isinstance(fv, Mapping):
                            file_fields_log[str(fk)] = str(
                                fv.get("filename") or fv.get("name") or fv.get("path") or fk
                            )
                        else:
                            file_fields_log[str(fk)] = str(fk)
            else:
                kwargs["json"] = json_body

        # 请求/响应留痕（脱敏）：query 敏感键掩码；body 只记键名（避免密码等入日志）
        body_keys = sorted(json_body.keys()) if isinstance(json_body, dict) else None
        started = time.monotonic()
        try:
            r = self.session.request(**kwargs)
        except Exception as exc:
            log_api_call(
                model.method, url,
                summary="request failed",
                query=_sanitize_params(query or {}),
                body_keys=body_keys,
                file_fields=file_fields_log,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_api_call(
            model.method, url,
            status=int(r.status_code),
            query=_sanitize_params(query or {}),
            body_keys=body_keys,
            file_fields=file_fields_log,
            elapsed_ms=elapsed_ms,
            resp=_response_snippet(getattr(r, "text", "") or ""),
        )

        raw_content_attr = getattr(r, "content", None)
        raw_content = bytes(raw_content_attr) if raw_content_attr else b""
        try:
            text = r.text or ""
        except (UnicodeDecodeError, LookupError):
            text = ""
        try:
            parsed = r.json()
        except ValueError:  # JSONDecodeError (json / requests) is a ValueError
            parsed = None

        ok = 200 <= int(r.status_code) < 300

        return ApiResponse(
            ok=ok,
            status_code=int(r.status_code),
            headers=dict(r.headers or {}),
            json=parsed,
            text=text,
            extracted={},
            content=raw_content,
        )
