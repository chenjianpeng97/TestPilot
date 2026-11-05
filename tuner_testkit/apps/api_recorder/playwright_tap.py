"""Playwright ``page.on("response")`` tap that freezes API Objects.

Does not call ``page.evaluate`` (or any other Playwright command that would
deadlock with ``expose_binding``). Reading ``response.body()`` / request
post data from the response event is allowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tuner_testkit.api_objects.recording import ApiCapturePipeline, MockSampleWriter
from tuner_testkit.api_objects.recording.freeze import FreezeResult


class PlaywrightApiTap:
    """Attach to a Playwright page and freeze eligible XHR/fetch exchanges."""

    def __init__(
        self,
        *,
        outputs_dir: Path,
        include_host: Optional[str] = None,
        verbose: bool = True,
        mock_writer: Optional[MockSampleWriter] = None,
        tool: str = "recorder",
    ) -> None:
        self.pipeline = ApiCapturePipeline(
            outputs_dir=outputs_dir,
            include_host=include_host,
            verbose=verbose,
            mock_writer=mock_writer,
            tool=tool,
            log_prefix=tool,
        )
        self.freezer = self.pipeline.freezer
        self._attached = False

    @property
    def stats(self) -> dict:
        return self.pipeline.stats

    @property
    def results(self) -> list[FreezeResult]:
        return self.pipeline.results

    def attach(self, page: Any) -> None:
        """Listen for ``response`` on this page. Safe to call once per page."""
        if self._attached:
            return
        page.on("response", self.on_response)
        self._attached = True

    def on_response(self, response: Any) -> None:
        """Handle a Playwright Response. Never call ``page.evaluate`` here."""
        try:
            request = response.request
            method = getattr(request, "method", "") or ""
            url = getattr(response, "url", None) or getattr(request, "url", "") or ""
            req_headers = _headers(request)
            resp_headers = _headers(response)
            status = int(getattr(response, "status", None) or getattr(response, "status_code", 0) or 0)
            post = _request_body(request)
            body = _response_body(response)
            self.pipeline.ingest(
                method=method,
                url=url,
                request_headers=req_headers,
                request_content=post,
                response_status=status,
                response_headers=resp_headers,
                response_content=body,
            )
        except Exception as exc:  # noqa: BLE001 — keep the browser session alive
            self.pipeline._log(f"[{self.pipeline.log_prefix}] freeze error: {exc}")

    def done(self) -> None:
        self.pipeline.done()

    def touched_items(self) -> list[str]:
        return self.pipeline.touched_items()


def _headers(obj: Any) -> dict[str, str]:
    raw = getattr(obj, "headers", None) or {}
    try:
        return {str(k): str(v) for k, v in dict(raw).items()}
    except Exception:  # noqa: BLE001 -- the tap reads live Playwright objects; any failure means no headers
        return {}


def _request_body(request: Any) -> bytes | str | None:
    try:
        buf = getattr(request, "post_data_buffer", None)
        if callable(buf):
            buf = buf()
        if buf is not None:
            return buf
    except Exception:  # noqa: BLE001 -- fall back to post_data below
        pass
    try:
        return getattr(request, "post_data", None)
    except Exception:  # noqa: BLE001 -- no body is a valid capture
        return None


def _response_body(response: Any) -> bytes:
    try:
        body = response.body()
        return body if body is not None else b""
    except Exception:  # noqa: BLE001 -- redirects / closed responses have no body
        return b""
