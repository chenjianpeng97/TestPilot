from __future__ import annotations

import pytest

from tuner_testkit.api_objects.auth import assert_recorded_response, materialize_payload
from tuner_testkit.api_test.model import ApiResponse


def test_materialize_password_placeholder(monkeypatch):
    monkeypatch.setenv("TEST_PASSWORD", "secret-pass")
    monkeypatch.setenv("TEST_USERNAME", "alice")
    out = materialize_payload({"username": "alice", "password": "***"})
    assert out["password"] == "secret-pass"
    assert out["username"] == "alice"


def test_assert_recorded_response_stable_fields():
    resp = ApiResponse(
        ok=True,
        status_code=200,
        headers={},
        json={"code": 200, "msg": "ok", "rows": [{"id": 1}], "total": 1},
        text="",
        content=b"",
    )
    recorded = {
        "http_status": 200,
        "is_json": True,
        # rows/total may differ across E2E runs; still kept as reference in the sample
        "json": {"code": 200, "msg": "ok", "rows": [{"id": 9}], "total": 99},
    }
    assert_recorded_response(resp, recorded)


def test_assert_recorded_response_code_mismatch():
    resp = ApiResponse(
        ok=True,
        status_code=200,
        headers={},
        json={"code": 500, "msg": "err"},
        text="",
        content=b"",
    )
    recorded = {"http_status": 200, "is_json": True, "json": {"code": 200, "msg": "ok"}}
    with pytest.raises(AssertionError, match=r"\$\.code"):
        assert_recorded_response(resp, recorded)
