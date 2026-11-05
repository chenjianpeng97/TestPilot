from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Union


class JsonPathError(ValueError):
    pass


@dataclass(frozen=True)
class _Key:
    name: str


@dataclass(frozen=True)
class _Index:
    index: int


_Token = Union[_Key, _Index]


_ROOT_RE = re.compile(r"^\$\.(.+)$")
_PARTS_RE = re.compile(r"""
    (?:
        \.([A-Za-z_][A-Za-z0-9_]*)
      | \[(\d+)\]
    )
""", re.VERBOSE)


def _parse(path: str) -> List[_Token]:
    if path == "$":
        return []
    m = _ROOT_RE.match(path)
    if not m:
        raise JsonPathError(f"Unsupported jsonpath: {path!r}")

    rest = "." + m.group(1)
    pos = 0
    tokens: List[_Token] = []
    while pos < len(rest):
        m2 = _PARTS_RE.match(rest, pos)
        if not m2:
            raise JsonPathError(f"Unsupported jsonpath segment at {pos}: {path!r}")
        key, idx = m2.group(1), m2.group(2)
        if key is not None:
            tokens.append(_Key(key))
        else:
            tokens.append(_Index(int(idx)))
        pos = m2.end()
    return tokens


def get(obj: Any, path: str, *, default: Any = None) -> Any:
    """Get value by a minimal jsonpath subset.

    Supported:
    - `$`
    - `$.a.b[0].c`
    """

    try:
        tokens = _parse(path)
    except JsonPathError:
        return default

    cur = obj
    for t in tokens:
        if isinstance(t, _Key):
            if not isinstance(cur, dict) or t.name not in cur:
                return default
            cur = cur[t.name]
        else:
            if not isinstance(cur, list):
                return default
            if t.index < 0 or t.index >= len(cur):
                return default
            cur = cur[t.index]
    return cur


def exists(obj: Any, path: str) -> bool:
    sentinel = object()
    return get(obj, path, default=sentinel) is not sentinel

