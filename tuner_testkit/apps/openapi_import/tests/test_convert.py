"""OpenAPI → exchanges → frozen API objects (same freezer as the recorders)."""
from __future__ import annotations

import json
from pathlib import Path

from tuner_testkit.apps.openapi_import.cli import main
from tuner_testkit.apps.openapi_import.convert import PLACEHOLDER_BEARER, iter_exchanges, load_spec

SPEC = {
    "openapi": "3.0.3",
    "servers": [{"url": "https://api.acme.example/v1"}],
    "security": [{"bearer": []}],
    "paths": {
        "/orders": {
            "get": {
                "tags": ["order"],
                "operationId": "listOrders",
                "parameters": [{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/OrderPage"}}}}},
            },
            "post": {
                "tags": ["order"],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NewOrder"}}}},
                "responses": {"201": {"content": {"application/json": {"example": {"id": 42}}}}},
            },
        },
        "/orders/{orderId}": {
            "parameters": [{"name": "orderId", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "get": {"tags": ["order"], "responses": {"200": {"description": "ok"}}},
        },
        "/workspaces/{slug}/members": {
            "get": {
                "tags": ["team"],
                "security": [],
                "parameters": [{"name": "slug", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
    "components": {
        "schemas": {
            "NewOrder": {"type": "object", "properties": {"sku": {"type": "string", "example": "A-1"}, "qty": {"type": "integer"}}},
            "OrderPage": {"type": "object", "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/NewOrder"}}, "total": {"type": "integer"}}},
        }
    },
}


def test_iter_exchanges_builds_samples(tmp_path: Path) -> None:
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
    exchanges = {(ex.method, ex.path): ex for ex in iter_exchanges(load_spec(spec_path))}
    listing = exchanges[("GET", "/orders")]
    assert listing.url == "https://api.acme.example/v1/orders?page=1"
    assert listing.request_headers["Authorization"] == PLACEHOLDER_BEARER
    assert json.loads(listing.response_content) == {"items": [{"sku": "A-1", "qty": 0}], "total": 0}
    create = exchanges[("POST", "/orders")]
    assert json.loads(create.request_content) == {"sku": "A-1", "qty": 0}
    assert create.response_status == 201 and json.loads(create.response_content) == {"id": 42}
    assert exchanges[("GET", "/orders/{orderId}")].url.endswith("/orders/1")
    members = exchanges[("GET", "/workspaces/{slug}/members")]
    assert members.url.endswith("/workspaces/{slug}/members") and "Authorization" not in members.request_headers
    only_team = iter_exchanges(SPEC, tags=["team"])
    assert [ex.path for ex in only_team] == ["/workspaces/{slug}/members"]
    assert [ex.method for ex in iter_exchanges(SPEC, path_prefix="/orders/")] == ["GET"]


def test_cli_dry_run_and_freeze(tmp_path: Path, capsys) -> None:
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / "api_objects"
    assert main([str(spec_path), "--out", str(out), "--dry-run", "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert envelope["outputs"][0]["count"] == 4 and not out.exists()

    assert main([str(spec_path), "--out", str(out), "--path-prefix", "/orders", "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert envelope["status"] == "succeeded" and envelope["outputs"][0]["touched"] == 3
    frozen = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.py") if p.name not in {"__init__.py", "auth.py"})
    # The server base path (/v1) stays in the asset path: TEST_BASE_URL carries the host only.
    assert frozen == ["v1/orders/GET.v1.py", "v1/orders/POST.v1.py", "v1/orders/{id}/GET.v1.py"]
    assert all("openapi-import-placeholder" not in p.read_text(encoding="utf-8") for p in out.rglob("*.py"))
    changelog = (out / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "openapi_import" in changelog and "POST /v1/orders" in changelog


def test_cli_rejects_non_openapi(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "x.json"
    bad.write_text("{}", encoding="utf-8")
    assert main([str(bad)]) == 2
    assert "not an OpenAPI document" in capsys.readouterr().err
