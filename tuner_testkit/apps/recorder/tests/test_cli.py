"""合录 CLI 离线：默认双开、互斥开关、旧代理参数提示；tap 用假 response。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.apps.recorder.cli import build_parser, main, reject_legacy_proxy_argv


def test_help_exits_zero():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_main_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_defaults_freeze_both_sides():
    parser = build_parser()
    args = parser.parse_args(["--app", "plane", "--url", "/sign-in"])
    assert args.page_only is False
    assert args.api_only is False
    assert args.app == "plane"


def test_page_only_and_api_only_are_mutex():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--app", "plane", "--page-only", "--api-only"])


def test_legacy_port_tells_user_to_use_api_recorder():
    with pytest.raises(SystemExit) as exc:
        reject_legacy_proxy_argv(["--port", "8080"])
    assert "apps.api_recorder" in str(exc.value)

    with pytest.raises(SystemExit) as exc:
        main(["--app", "plane", "--port", "8888"])
    assert "apps.api_recorder" in str(exc.value)

    with pytest.raises(SystemExit) as exc:
        reject_legacy_proxy_argv(["--listen_host=0.0.0.0"])
    assert "apps.api_recorder" in str(exc.value)


def test_page_changelog_stamps_recorder(tmp_path: Path):
    from tuner_testkit.apps.recorder.cli import _write_page_changelog

    _write_page_changelog(tmp_path, app="plane", items=["plane.sign_in@v1"])
    text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "recorder" in text
    assert "record-pages" in text
    assert "plane.sign_in@v1" in text


class _FakeRequest:
    def __init__(
        self,
        *,
        method: str = "POST",
        url: str = "http://example.com/prod-api/items",
        headers: dict | None = None,
        body: bytes = b'{"pageNum":1}',
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers if headers is not None else {"content-type": "application/json"}
        self.post_data_buffer = body
        self.post_data = body.decode("utf-8") if body else None


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str = "http://example.com/prod-api/items",
        status: int = 200,
        headers: dict | None = None,
        body: bytes = b'{"code":200,"data":[]}',
        request: _FakeRequest | None = None,
        fail_body: bool = False,
    ) -> None:
        self.url = url
        self.status = status
        self.headers = headers if headers is not None else {"content-type": "application/json"}
        self.request = request or _FakeRequest(url=url)
        self._body = body
        self._fail_body = fail_body

    def body(self) -> bytes:
        if self._fail_body:
            raise RuntimeError("no body")
        return self._body


def test_tap_freezes_json_and_skips_static(tmp_path: Path):
    from tuner_testkit.apps.api_recorder.playwright_tap import PlaywrightApiTap

    tap = PlaywrightApiTap(outputs_dir=tmp_path, verbose=False, tool="recorder")
    tap.on_response(_FakeResponse())
    assert tap.stats["frozen"] == 1
    asset = tmp_path / "prod-api" / "items" / "POST.v1.py"
    assert asset.is_file()
    text = asset.read_text(encoding="utf-8")
    assert "Auto-maintained by apps.recorder" in text
    assert "SECRET" not in text

    tap.on_response(
        _FakeResponse(
            url="http://example.com/static/app.js",
            request=_FakeRequest(method="GET", url="http://example.com/static/app.js", body=b""),
            headers={"content-type": "application/javascript"},
            body=b"console.log(1)",
        )
    )
    assert tap.stats["skipped_static"] == 1

    tap.on_response(
        _FakeResponse(
            url="http://example.com/",
            request=_FakeRequest(method="GET", url="http://example.com/", body=b""),
            headers={"content-type": "text/html"},
            body=b"<html></html>",
        )
    )
    assert tap.stats["skipped_static"] == 2


def test_tap_sanitizes_authorization(tmp_path: Path):
    from tuner_testkit.apps.api_recorder.playwright_tap import PlaywrightApiTap

    tap = PlaywrightApiTap(outputs_dir=tmp_path, verbose=False)
    req = _FakeRequest(headers={"content-type": "application/json", "authorization": "Bearer SECRETTOKEN1234567890"})
    tap.on_response(_FakeResponse(request=req, body=b'{"code":200,"token":"eyJhbGciOiJIUzI1NiJ9.payload.sig"}'))
    text = (tmp_path / "prod-api" / "items" / "POST.v1.py").read_text(encoding="utf-8")
    assert "SECRETTOKEN" not in text
    assert "Bearer " not in text


def test_tap_attach_registers_response_handler(tmp_path: Path):
    from tuner_testkit.apps.api_recorder.playwright_tap import PlaywrightApiTap

    tap = PlaywrightApiTap(outputs_dir=tmp_path, verbose=False)
    seen: list[str] = []

    class FakePage:
        def on(self, event, callback):
            seen.append(event)
            assert callback == tap.on_response

    tap.attach(FakePage())
    tap.attach(FakePage())
    assert seen == ["response"]


def test_tap_survives_body_read_failure(tmp_path: Path):
    from tuner_testkit.apps.api_recorder.playwright_tap import PlaywrightApiTap

    tap = PlaywrightApiTap(outputs_dir=tmp_path, verbose=False)
    tap.on_response(_FakeResponse(fail_body=True, body=b""))
    assert tap.stats["frozen"] == 1
