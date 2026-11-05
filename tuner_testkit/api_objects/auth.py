"""Shared auth + replay helpers for ``api_objects`` ``__main__`` blocks.

Postman / Apifox style: one place to manage credentials; asset files only
reference this module. Never commit real tokens — load from env.

Env vars:
  - ``TEST_BASE_URL``     — API host (see ``tuner_testkit.config``)
  - ``TEST_BEARER_TOKEN`` — Bearer token for authenticated replay
  - ``TEST_USERNAME`` / ``TEST_PASSWORD`` — used to materialize login bodies
    and optional auto-login when token is missing
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from tuner_testkit.api_test.client import ApiClient
from tuner_testkit.api_test.model import APIModel, ApiResponse
from tuner_testkit.config import get_test_base_url

_SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|session|credential|passwd|pwd)", re.I)
_USER_KEY_RE = re.compile(r"(user|username|account|loginname)$", re.I)
_PASS_KEY_RE = re.compile(r"(password|passwd|pwd)$", re.I)


def bootstrap_repo_path() -> Path:
    """Ensure the SUT repo root is on ``sys.path`` (never the kit install path)."""
    from tuner_testkit.project import ensure_project_on_path

    return ensure_project_on_path()


# --- credential surface (fill via env; never hardcode secrets here) ---


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def bearer_token() -> str:
    return _env("TEST_BEARER_TOKEN")


def username() -> str:
    return _env("TEST_USERNAME")


def password() -> str:
    return _env("TEST_PASSWORD")


def get_client() -> ApiClient:
    return ApiClient(base_url=get_test_base_url())


def get_auth(*, allow_login: bool = True) -> dict[str, str]:
    """Return ``{"bearer_token": ...}`` for ``APIModel.execute(auth=...)``."""
    token = bearer_token()
    if not token and allow_login and username() and password():
        token = _try_login_for_token()
    if not token:
        raise SystemExit(
            "Missing auth for replay. Set TEST_BEARER_TOKEN, or "
            "TEST_USERNAME + TEST_PASSWORD (and a working TEST_BASE_URL)."
        )
    return {"bearer_token": token}


def _try_login_for_token() -> str:
    """Best-effort login against ``/prod-api/login`` when credentials are set."""
    client = get_client()
    try:
        r = client.session.post(
            f"{client.base_url.rstrip('/')}/prod-api/login",
            json={"username": username(), "password": password()},
            timeout=30,
        )
        data = r.json() if r.content else {}
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Auto-login failed: {exc}") from exc
    token = ""
    if isinstance(data, Mapping):
        inner = data.get("data")
        if isinstance(inner, Mapping):
            token = str(inner.get("token") or inner.get("access_token") or "")
        if not token:
            token = str(data.get("token") or "")
    if not token:
        raise SystemExit(f"Auto-login returned no token (http={r.status_code})")
    return token


def materialize_payload(data: Any) -> Any:
    """Replace sanitized ``***`` placeholders with env credentials."""
    if not isinstance(data, Mapping):
        return data
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = str(k)
        if isinstance(v, Mapping):
            out[key] = materialize_payload(v)
            continue
        if v == "***":
            if _PASS_KEY_RE.search(key):
                out[key] = password()
            elif _USER_KEY_RE.search(key):
                out[key] = username()
            elif _SENSITIVE_KEY_RE.search(key):
                out[key] = bearer_token()
            else:
                out[key] = _env(f"TEST_{key.upper()}")
            continue
        out[key] = v
    return out


def replay_execute(
    model: APIModel,
    *,
    path: str | None = None,
    query: Optional[Mapping[str, Any]] = None,
    body: Any = None,
    files: Optional[Mapping[str, Any]] = None,
    use_auth: bool = True,
) -> ApiResponse:
    """Send the recorded sample via ``APIModel`` / ``ApiClient``.

    ``files`` is only used when ``model.body_format == "multipart"``.
    Values follow ``APIModel.set_files`` FileInput shapes (path / tuple / mapping).
    """
    m = replace(model, path=path) if path else model
    inv = m
    q = materialize_payload(dict(query or {}))
    if q:
        inv = inv.set_query(q)
    if body is not None and m.method.upper() != "GET":
        inv = inv.set_json(materialize_payload(body))
    if files and (m.body_format or "").lower() == "multipart":
        inv = inv.set_files(dict(files))
    auth = get_auth() if use_auth else {}
    return inv.execute(auth=auth, client=get_client())


_VOLATILE_TOP_KEYS = frozenset(
    {
        "rows",
        "data",
        "list",
        "records",
        "total",
        "timestamp",
        "time",
        "date",
        "requestId",
        "request_id",
        "traceId",
        "trace_id",
    }
)


def assert_recorded_response(resp: ApiResponse, recorded: Mapping[str, Any]) -> None:
    """Assert live response against the recorded sample (stable fields + shape)."""
    expected_status = int(recorded.get("http_status", 200))
    if resp.status_code != expected_status:
        raise AssertionError(
            f"http_status: expected {expected_status}, got {resp.status_code}"
        )

    expected_json = recorded.get("json")
    if not recorded.get("is_json", expected_json is not None):
        # Binary / non-JSON: status-only (body bytes are scenario-volatile).
        return

    if not isinstance(expected_json, Mapping):
        return
    if not isinstance(resp.json, Mapping):
        raise AssertionError(f"expected JSON object, got {type(resp.json).__name__}")

    actual: Mapping[str, Any] = resp.json
    if "code" in expected_json and actual.get("code") != expected_json.get("code"):
        raise AssertionError(
            f"$.code: expected {expected_json.get('code')!r}, got {actual.get('code')!r}"
        )

    # Shape: every top-level key in the sample must still exist.
    missing = [k for k in expected_json.keys() if k not in actual]
    if missing:
        raise AssertionError(f"response missing keys from recorded sample: {missing}")

    # Scalar top-level fields (skip secrets / collections / volatile counters).
    for key, exp in expected_json.items():
        if str(key) in _VOLATILE_TOP_KEYS:
            continue
        if _SENSITIVE_KEY_RE.search(str(key)):
            continue
        if isinstance(exp, (dict, list)):
            continue
        if exp == "***":
            continue
        if actual.get(key) != exp:
            raise AssertionError(
                f"$.{key}: expected {exp!r}, got {actual.get(key)!r}"
            )


def ensure_auth_file(outputs_dir: Path) -> Path:
    """Create a stub ``auth.py`` under outputs_dir if missing (custom --outputs_dir)."""
    target = outputs_dir / "auth.py"
    if target.exists():
        return target
    # Prefer pointing users at the package auth module when under packages/api_objects.
    stub = '''\
"""Local auth stub for a custom outputs_dir.

Prefer maintaining credentials in ``tuner_testkit.api_objects.auth`` (repo package).
This file is only created when recorder writes outside the default package tree.
"""
from tuner_testkit.api_objects.auth import *  # noqa: F403
'''
    target.write_text(stub, encoding="utf-8")
    return target
