"""Shared ingest path: filter → capture → freeze → optional mock write.

Used by ``apps.api_recorder`` (mitmproxy) and ``apps.recorder`` (Playwright tap).
No Playwright / mitmproxy imports here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from .capture import Capture, build_capture
from .freeze import ApiObjectFreezer, FreezeResult
from .mocks import MockSampleWriter
from .normalize import skip_api_flow

DEFAULT_TOOL = "recorder"


def _content_type(headers: Mapping[str, Any] | None) -> str:
    for key, value in (headers or {}).items():
        if str(key).lower() == "content-type":
            return str(value)
    return ""


class ApiCapturePipeline:
    """Filter one HTTP exchange and freeze it into the api_objects tree."""

    def __init__(
        self,
        *,
        outputs_dir: Path,
        include_host: Optional[str] = None,
        verbose: bool = True,
        mock_writer: Optional[MockSampleWriter] = None,
        tool: str = DEFAULT_TOOL,
        log_prefix: str | None = None,
    ) -> None:
        self.tool = (tool or DEFAULT_TOOL).strip() or DEFAULT_TOOL
        self.freezer = ApiObjectFreezer(outputs_dir, tool=self.tool)
        self.include_host = (include_host or "").strip().lower() or None
        self.verbose = verbose
        self.mock_writer = mock_writer
        self.log_prefix = log_prefix or self.tool
        self.stats = {
            "seen": 0,
            "skipped_static": 0,
            "skipped_host": 0,
            "skipped_method": 0,
            "frozen": 0,
            "mocks_written": 0,
            "mocks_skipped": 0,
        }
        self.results: list[FreezeResult] = []

    def ingest(
        self,
        *,
        method: str,
        url: str,
        request_headers: Mapping[str, Any],
        request_content: bytes | str | None,
        response_status: int,
        response_headers: Mapping[str, Any],
        response_content: bytes | str | None,
    ) -> FreezeResult | None:
        """Return a freeze result, or None when the exchange is skipped."""
        self.stats["seen"] += 1
        reason = skip_api_flow(
            method=method,
            url=url,
            request_content_type=_content_type(request_headers),
            response_content_type=_content_type(response_headers),
            include_host=self.include_host,
        )
        if reason:
            key = f"skipped_{reason}"
            self.stats[key] = self.stats.get(key, 0) + 1
            return None

        capture = build_capture(
            method=method,
            url=url,
            request_headers=request_headers,
            request_content=request_content,
            response_status=response_status,
            response_headers=response_headers,
            response_content=response_content,
            tool=self.tool,
        )
        result = self.freezer.freeze(capture)
        self.results.append(result)
        self.stats["frozen"] += 1
        self._log(
            f"[{self.log_prefix}] {result.action} {result.method} "
            f"{result.normalized_path} -> {result.path}"
        )
        self._write_mock(capture, result)
        return result

    def touched_items(self) -> list[str]:
        return [
            f"{item.method} {item.normalized_path}"
            for item in self.results
            if item.action in {"created", "updated"}
        ]

    def done(self) -> None:
        summary = (
            f"[{self.log_prefix}] done "
            f"seen={self.stats['seen']} frozen={self.stats['frozen']} "
            f"skipped_static={self.stats['skipped_static']} "
            f"skipped_host={self.stats['skipped_host']} "
            f"skipped_method={self.stats['skipped_method']}"
        )
        if self.mock_writer is not None:
            summary += (
                f" mocks_written={self.stats['mocks_written']} "
                f"mocks_skipped={self.stats['mocks_skipped']}"
            )
        self._log(summary)

    def _write_mock(self, capture: Capture, result: FreezeResult) -> None:
        if self.mock_writer is None or result.action == "skipped":
            return
        try:
            written = self.mock_writer.write(capture, version=result.major)
        except Exception as exc:  # noqa: BLE001 — a mock write must not kill the session
            self.stats["mocks_skipped"] += 1
            self._log(f"[{self.log_prefix}] mock write error: {exc}")
            return
        if written.action == "skipped":
            self.stats["mocks_skipped"] += 1
        else:
            self.stats["mocks_written"] += 1
        self._log(
            f"[{self.log_prefix}] mock {written.action} {written.path} ({written.detail})"
        )

    def _log(self, msg: str) -> None:
        if not self.verbose:
            return
        try:
            from tuner_testkit.logging import log_info

            log_info(msg)
        except Exception:  # noqa: BLE001 -- logging must never stop a recording session
            print(msg)
