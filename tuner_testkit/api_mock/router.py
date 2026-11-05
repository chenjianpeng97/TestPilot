"""Match an incoming request path against mock route patterns.

Patterns use the same dynamic-segment vocabulary that
``tuner_testkit.api_objects.recording.normalize_path`` emits when it freezes assets
(``{id}`` for integer segments, ``{uuid}`` for UUIDs). That function normalises
a concrete path into a pattern; this module does the inverse — deciding whether
a concrete path satisfies a pattern — so the two are complementary rather than
duplicated. The vocabulary must stay in sync with the recorder.

Literal patterns always win over parameterised ones, and among parameterised
matches the one with the fewest placeholders wins, so
``/users/me`` never gets shadowed by ``/users/{id}``.
"""
from __future__ import annotations

import re
from typing import Callable, Generic, Iterable, TypeVar

__all__ = ["PathPattern", "RouteTable", "path_matches"]

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_INT_RE = re.compile(r"^\d+$")
_PLACEHOLDER_RE = re.compile(r"^\{([^{}]*)\}$")

T = TypeVar("T")


class PathPattern:
    """A compiled route path such as ``/users/{id}/orders``."""

    __slots__ = ("raw", "_segments", "placeholder_count")

    def __init__(self, pattern: str) -> None:
        self.raw = pattern if pattern.startswith("/") else "/" + pattern
        self._segments = tuple(seg for seg in self.raw.split("/") if seg)
        self.placeholder_count = sum(1 for seg in self._segments if _PLACEHOLDER_RE.match(seg))

    @property
    def is_literal(self) -> bool:
        return self.placeholder_count == 0

    def matches(self, path: str) -> bool:
        actual = path if path.startswith("/") else "/" + path
        actual_segments = [seg for seg in actual.split("/") if seg]
        if len(actual_segments) != len(self._segments):
            return False
        return all(
            _segment_matches(pattern_seg, actual_seg)
            for pattern_seg, actual_seg in zip(self._segments, actual_segments, strict=True)
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PathPattern({self.raw!r})"


def _segment_matches(pattern_seg: str, actual_seg: str) -> bool:
    placeholder = _PLACEHOLDER_RE.match(pattern_seg)
    if placeholder is None:
        return pattern_seg == actual_seg
    name = placeholder.group(1).strip().lower()
    if name == "id":
        return bool(_INT_RE.match(actual_seg))
    if name == "uuid":
        return bool(_UUID_RE.match(actual_seg))
    # Any other {name} accepts a single non-empty segment.
    return bool(actual_seg)


def path_matches(pattern: str, path: str) -> bool:
    return PathPattern(pattern).matches(path)


class RouteTable(Generic[T]):
    """Method-scoped lookup returning the most specific matching entry."""

    def __init__(
        self,
        entries: Iterable[T],
        *,
        method_of: Callable[[T], str],
        path_of: Callable[[T], str],
    ) -> None:
        self._by_method: dict[str, list[tuple[PathPattern, T]]] = {}
        for entry in entries:
            method = str(method_of(entry)).strip().upper()
            self._by_method.setdefault(method, []).append((PathPattern(path_of(entry)), entry))
        for candidates in self._by_method.values():
            # Literal first, then fewest placeholders; ties keep insertion order.
            candidates.sort(key=lambda item: (item[0].placeholder_count, item[0].raw))

    def match(self, method: str, path: str) -> T | None:
        for pattern, entry in self._by_method.get(str(method).strip().upper(), ()):
            if pattern.matches(path):
                return entry
        return None

    def __len__(self) -> int:
        return sum(len(items) for items in self._by_method.values())
