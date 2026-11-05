from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from .errors import ApiAssertError, FilesPolicyError, HeadersPolicyError, SchemaValidationError
from .jsonpath import exists as jsonpath_exists
from .jsonpath import get as jsonpath_get


@dataclass(frozen=True)
class AssertOperation:
    name: str
    jsonpath: str
    operator: str  # "eq" | "exists"
    expected: Any


@dataclass(frozen=True)
class ExtractVariableOperation:
    name: str
    jsonpath: str
    variable_name: str


@dataclass(frozen=True)
class ApiResponse:
    """Shape-stable HTTP response used by APIModel extract/assert layers.

    The ``json`` field is populated when the response body parses as JSON;
    ``content`` always holds the raw response bytes (for binary payloads
    such as xlsx/pdf/png downloads). Both are present regardless of
    content-type — callers pick the field appropriate for the asset.
    """

    ok: bool
    status_code: int
    headers: Mapping[str, str]
    json: Any
    text: str
    extracted: Dict[str, Any] = field(default_factory=dict)
    content: bytes = b""


def _merge_shallow(base: Optional[Mapping[str, Any]], patch: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base or {})
    if patch:
        for k, v in patch.items():
            out[k] = v
    return out


def _validate_keys_or_autofill(
    *,
    schema: MutableMapping[str, Any],
    values: Mapping[str, Any],
    allow_autofill: bool,
    schema_name: str,
) -> None:
    missing = [k for k in values.keys() if k not in schema]
    if not missing:
        return
    if not allow_autofill:
        raise SchemaValidationError(f"{schema_name} has unknown keys: {missing}")
    for k in missing:
        schema[k] = {"type": "any", "required": False, "note": "autofilled by set_*"}


def _enforce_headers_policy(
    *,
    headers: Mapping[str, Any],
    allowlist: Iterable[str],
    forbidden: Iterable[str],
) -> Dict[str, str]:
    allow = {h.lower() for h in allowlist}
    forbid = {h.lower() for h in forbidden}

    out: Dict[str, str] = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in forbid:
            raise HeadersPolicyError(f"Header {k!r} is forbidden")
        if lk not in allow:
            raise HeadersPolicyError(f"Header {k!r} is not in allowlist")
        out[str(k)] = str(v)
    return out


def _require_multipart(model: "APIModel", *, action: str) -> None:
    fmt = (model.body_format or "json").lower()
    if fmt != "multipart":
        raise FilesPolicyError(
            f"{action} requires body_format='multipart' (got {model.body_format!r})"
        )


def _required_file_fields(schema: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for key, meta in (schema or {}).items():
        if isinstance(meta, Mapping) and bool(meta.get("required")):
            out.append(str(key))
    return out


_PATH_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate_path(path: str, params: Mapping[str, Any]) -> str:
    """Replace ``{name}`` segments. Raises if any named placeholder remains."""
    out = path
    for key, value in params.items():
        out = out.replace("{" + str(key) + "}", str(value))
    leftover = _PATH_PLACEHOLDER_RE.findall(out)
    if leftover:
        raise SchemaValidationError(
            f"path still has placeholders {leftover}; pass them via set_path"
        )
    return out


@dataclass(frozen=True)
class APIModel:
    # Identity
    id: str
    name: str
    description: str
    method: str
    path: str

    # Contract
    query_schema: Dict[str, Any] = field(default_factory=dict)
    body_schema: Dict[str, Any] = field(default_factory=dict)
    files_schema: Dict[str, Any] = field(default_factory=dict)
    response_hints: Dict[str, Any] = field(default_factory=dict)
    headers_policy: Dict[str, Any] = field(default_factory=dict)
    auth_policy: Dict[str, Any] = field(default_factory=dict)
    body_format: str = "json"
    """How the request body is serialised on the wire.

    One of:
        * ``"json"`` (default, backwards compatible) — body is sent as
          ``application/json`` via ``requests`` ``json=`` kwarg.
        * ``"form"`` — body is sent as ``application/x-www-form-urlencoded``
          via ``requests`` ``data=`` kwarg. Used when a backend endpoint
          (e.g. DMS authorization export) only accepts form-encoded bodies.
        * ``"multipart"`` — text fields via ``data=`` (from ``set_json``) and
          file fields via ``files=`` (from ``set_files``). Used for Excel
          import / multipart uploads. Do not set Content-Type manually.

    Ignored for ``GET`` methods.
    """

    # Operations
    asserts: List[AssertOperation] = field(default_factory=list)
    extracts: List[ExtractVariableOperation] = field(default_factory=list)

    # Runtime binding (not persisted secrets)
    _client: Any = field(default=None, repr=False, compare=False)

    def bind(self, client: Any) -> "APIModel":
        return replace(self, _client=client)

    def set_query(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        return APIInvocation(self).set_query(values, autofill_schema=autofill_schema)

    def set_json(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        return APIInvocation(self).set_json(values, autofill_schema=autofill_schema)

    def set_files(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        return APIInvocation(self).set_files(values, autofill_schema=autofill_schema)

    def set_headers(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        return APIInvocation(self).set_headers(values)

    def set_path(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        return APIInvocation(self).set_path(values)

    def override_query(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        return APIInvocation(self).override_query(values)

    def override_json(self, values: Any = None) -> "APIInvocation":
        return APIInvocation(self).override_json(values)

    def override_files(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        return APIInvocation(self).override_files(values)

    def override_headers(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        return APIInvocation(self).override_headers(values)

    def execute(self, *, auth: Optional[Mapping[str, Any]] = None, client: Any = None, timeout: Optional[float] = None) -> ApiResponse:
        return APIInvocation(self).execute(auth=auth, client=client, timeout=timeout)


@dataclass(frozen=True)
class APIInvocation:
    model: APIModel

    # invocation state
    _set_query: Dict[str, Any] = field(default_factory=dict)
    _set_json: Dict[str, Any] = field(default_factory=dict)
    _set_files: Dict[str, Any] = field(default_factory=dict)
    _set_headers: Dict[str, Any] = field(default_factory=dict)
    _path_params: Dict[str, Any] = field(default_factory=dict)
    _override_query: Optional[Dict[str, Any]] = None
    _override_json: Any = None
    _override_json_set: bool = False
    _override_files: Optional[Dict[str, Any]] = None
    _override_headers: Optional[Dict[str, Any]] = None

    # schema mutation is represented as copies on the bound model
    _query_schema: Optional[Dict[str, Any]] = None
    _body_schema: Optional[Dict[str, Any]] = None
    _files_schema: Optional[Dict[str, Any]] = None

    def _with_model_schemas(
        self,
        *,
        query_schema: Optional[Dict[str, Any]] = None,
        body_schema: Optional[Dict[str, Any]] = None,
        files_schema: Optional[Dict[str, Any]] = None,
    ) -> "APIInvocation":
        return replace(
            self,
            _query_schema=query_schema if query_schema is not None else self._query_schema,
            _body_schema=body_schema if body_schema is not None else self._body_schema,
            _files_schema=files_schema if files_schema is not None else self._files_schema,
        )

    def set_query(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        values = dict(values or {})
        schema = dict(self._query_schema if self._query_schema is not None else self.model.query_schema)
        _validate_keys_or_autofill(schema=schema, values=values, allow_autofill=autofill_schema, schema_name="query_schema")
        return replace(self, _set_query=_merge_shallow(self._set_query, values))._with_model_schemas(query_schema=schema)

    def set_json(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        values = dict(values or {})
        schema = dict(self._body_schema if self._body_schema is not None else self.model.body_schema)
        _validate_keys_or_autofill(schema=schema, values=values, allow_autofill=autofill_schema, schema_name="body_schema")
        return replace(self, _set_json=_merge_shallow(self._set_json, values))._with_model_schemas(body_schema=schema)

    def set_files(self, values: Optional[Mapping[str, Any]] = None, *, autofill_schema: bool = True) -> "APIInvocation":
        _require_multipart(self.model, action="set_files")
        values = dict(values or {})
        schema = dict(self._files_schema if self._files_schema is not None else self.model.files_schema)
        missing = [k for k in values.keys() if k not in schema]
        if missing and not autofill_schema:
            raise SchemaValidationError(f"files_schema has unknown keys: {missing}")
        for k in missing:
            schema[str(k)] = {"type": "file", "required": False, "note": "autofilled by set_files"}
        return replace(self, _set_files=_merge_shallow(self._set_files, values))._with_model_schemas(files_schema=schema)

    def set_headers(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        values = dict(values or {})
        hp = self.model.headers_policy or {}
        allowlist = hp.get("allowlist", [])
        forbidden = hp.get("forbidden", [])
        checked = _enforce_headers_policy(headers=values, allowlist=allowlist, forbidden=forbidden)
        return replace(self, _set_headers=_merge_shallow(self._set_headers, checked))

    def set_path(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        values = {str(k): v for k, v in dict(values or {}).items()}
        return replace(self, _path_params=_merge_shallow(self._path_params, values))

    def override_query(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        values = dict(values or {})
        # override still must respect schema; allow autofill via set_query if needed
        schema = dict(self._query_schema if self._query_schema is not None else self.model.query_schema)
        _validate_keys_or_autofill(schema=schema, values=values, allow_autofill=False, schema_name="query_schema")
        return replace(self, _override_query=values)._with_model_schemas(query_schema=schema)

    def override_json(self, values: Any = None) -> "APIInvocation":
        # For rebuild, allow any shape but keep body_schema unchanged.
        return replace(self, _override_json=values, _override_json_set=True)

    def override_files(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        _require_multipart(self.model, action="override_files")
        values = dict(values or {})
        schema = dict(self._files_schema if self._files_schema is not None else self.model.files_schema)
        _validate_keys_or_autofill(schema=schema, values=values, allow_autofill=False, schema_name="files_schema")
        # 整表替换：清空此前 set_files，避免旧文件字段残留
        return replace(self, _override_files=values, _set_files={})._with_model_schemas(files_schema=schema)

    def override_headers(self, values: Optional[Mapping[str, Any]] = None) -> "APIInvocation":
        values = dict(values or {})
        hp = self.model.headers_policy or {}
        allowlist = hp.get("allowlist", [])
        forbidden = hp.get("forbidden", [])
        checked = _enforce_headers_policy(headers=values, allowlist=allowlist, forbidden=forbidden)
        return replace(self, _override_headers=checked)

    def _final_query(self) -> Dict[str, Any]:
        base: Mapping[str, Any] = self._override_query if self._override_query is not None else {}
        return _merge_shallow(base, self._set_query)

    def _final_json(self) -> Any:
        if self._override_json_set:
            base = self._override_json
        else:
            base = {}
        if isinstance(base, dict):
            return _merge_shallow(base, self._set_json)
        # If override_json is not a dict (string/list/etc), set_json is ignored by design.
        return base

    def _final_files(self) -> Dict[str, Any]:
        base: Mapping[str, Any] = self._override_files if self._override_files is not None else {}
        return _merge_shallow(base, self._set_files)

    def _final_headers(self) -> Dict[str, str]:
        base = self._override_headers if self._override_headers is not None else {}
        return {**base, **{k: str(v) for k, v in self._set_headers.items()}}

    def _effective_model(self) -> APIModel:
        m = self.model
        if self._query_schema is not None:
            m = replace(m, query_schema=self._query_schema)
        if self._body_schema is not None:
            m = replace(m, body_schema=self._body_schema)
        if self._files_schema is not None:
            m = replace(m, files_schema=self._files_schema)
        return m

    def _validate_required_files(self, m: APIModel, files: Mapping[str, Any]) -> None:
        if (m.body_format or "json").lower() != "multipart":
            return
        schema = self._files_schema if self._files_schema is not None else m.files_schema
        missing = [k for k in _required_file_fields(schema) if k not in files or files[k] is None]
        if missing:
            raise FilesPolicyError(f"multipart required file fields missing: {missing}")

    def execute(self, *, auth: Optional[Mapping[str, Any]] = None, client: Any = None, timeout: Optional[float] = None) -> ApiResponse:
        from .client import ApiClient  # local import to avoid cycles

        m = self._effective_model()
        if self._path_params:
            m = replace(m, path=interpolate_path(m.path, self._path_params))
        use_client = client or m._client or ApiClient.default()
        files = self._final_files()
        self._validate_required_files(m, files)

        resp = use_client.request(
            model=m,
            query=self._final_query(),
            json_body=self._final_json(),
            files=files,
            headers=self._final_headers(),
            auth=auth or {},
            timeout=timeout,
        )

        payload = resp.json
        if isinstance(payload, dict):
            eval_obj: Any = dict(payload)
            eval_obj["http_status"] = resp.status_code
        else:
            eval_obj = {"http_status": resp.status_code, "body": payload}

        extracted: Dict[str, Any] = dict(resp.extracted)

        for op in m.asserts:
            if op.operator == "exists":
                actual = jsonpath_exists(eval_obj, op.jsonpath)
                if bool(actual) is not bool(op.expected):
                    raise ApiAssertError(f"Assert failed [{op.name}]: expected exists={op.expected}, got {actual}")
            elif op.operator == "eq":
                actual = jsonpath_get(eval_obj, op.jsonpath, default=None)
                if actual != op.expected:
                    raise ApiAssertError(f"Assert failed [{op.name}]: expected {op.expected!r}, got {actual!r}")
            else:
                raise ApiAssertError(f"Unsupported operator: {op.operator!r}")

        for op in m.extracts:
            value = jsonpath_get(eval_obj, op.jsonpath, default=None)
            extracted[op.variable_name] = value

        return replace(resp, extracted=extracted)
