"""FastAPI application for the local workbench."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tuner_testkit.catalog.build import build_catalog
from tuner_testkit.catalog.directory import build_directory
from tuner_testkit.project import project_root
from tuner_testkit.tools.runner import DestructiveNotConfirmed, RunRequest, run_tool
from tuner_testkit.apps.index_ai.registry import (
    KIND_META,
    collect_catalog,
    find_component,
    read_component_intro,
)
from tuner_testkit.workbench.dashboard import PAGES, DashboardStore
from tuner_testkit.workbench.kinds import known_word_kind

PACKAGE_DIR = Path(__file__).resolve().parent


def _static_version() -> str:
    """Cache-bust token for ``/static/*`` (mtime; falls back to kit version).

    Browsers cache ``/static/app.css`` across kit upgrades. Without a changing
    query string, an old stylesheet keeps applying and the new layout/sidebar
    classes look unstyled.
    """
    css = PACKAGE_DIR / "static" / "app.css"
    try:
        return str(int(css.stat().st_mtime))
    except OSError:
        from tuner_testkit import __version__

        return __version__


def create_app(*, root: Path | None = None) -> FastAPI:
    repo = Path(root).resolve() if root is not None else project_root()
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app = FastAPI(title="tuner workbench", docs_url=None, redoc_url=None)
    static = PACKAGE_DIR / "static"
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=str(static)), name="static")
    app.state.root = repo
    static_v = _static_version()
    os.environ["TUNER_ROOT"] = str(repo)

    def directory(*, refresh: bool = False) -> dict[str, Any]:
        return build_directory(repo, include_kit_tools=True, refresh=refresh)

    catalog_lock = threading.Lock()
    catalog_cache: dict[str, Any] = {}

    def catalog(*, refresh: bool = False) -> dict[str, Any]:
        # Full catalog is slow (scan + git log per asset): build once per process, rebuild on ?refresh=1.
        with catalog_lock:
            if refresh or "payload" not in catalog_cache:
                catalog_cache["payload"] = build_catalog(repo, include_kit_tools=True)
            return catalog_cache["payload"]

    dashboard = DashboardStore(repo)
    app.state.dashboard = dashboard

    def _render(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        return templates.TemplateResponse(
            request, name, {"root": str(repo), "dash_pages": PAGES, "static_v": static_v, **ctx}
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return _render(request, "dashboard/home.html", dash=dashboard.view())

    @app.get("/dashboard/{page}", response_class=HTMLResponse)
    def dashboard_page(request: Request, page: str) -> HTMLResponse:
        meta = next((p for p in PAGES if p[0] == page), None)
        if meta is None:
            raise HTTPException(404, f"unknown dashboard page {page}")
        dash = dashboard.view()
        return _render(
            request,
            f"dashboard/{page}.html",
            dash=dash,
            page=meta,
            section=(dash.get("sections") or {}).get(page) or {},
        )

    @app.get("/api/dashboard")
    def api_dashboard() -> JSONResponse:
        return JSONResponse(dashboard.load())

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(request: Request, q: str = "", refresh: bool = False) -> HTMLResponse:
        items = [it for it in _directory(directory(refresh=refresh), q) if it["kind"] == "tool"]
        return _render(request, "tools.html", items=items, q=q)

    @app.get("/tools/{item_id}", response_class=HTMLResponse)
    def tool_detail(request: Request, item_id: str, refresh: bool = False) -> HTMLResponse:
        item = _find_item(directory(refresh=refresh), item_id)
        if item is None:
            raise HTTPException(404, f"unknown tool {item_id}")
        if item["kind"] == "action_word":
            return RedirectResponse(url=item["href"], status_code=302)
        readme = _readme_text(repo, item)
        return _render(request, "tool.html", item=item, readme=readme, form_action=f"/tools/{item['id']}/run")

    @app.post("/tools/{item_id}/run")
    async def tool_run(request: Request, item_id: str) -> RedirectResponse:
        return await _run_from_form(request, repo, item_id)

    @app.get("/words/{kind}", response_class=HTMLResponse)
    def words_page(request: Request, kind: str, q: str = "", refresh: bool = False) -> HTMLResponse:
        spec = known_word_kind(kind)
        if spec is None:
            raise HTTPException(404, f"unknown kind {kind}")
        items = [
            it
            for it in _directory(directory(refresh=refresh), q)
            if it["kind"] == "action_word" and it.get("category") == kind
        ]
        return _render(request, spec.list_template, items=items, q=q, kind=spec)

    @app.get("/words/{kind}/{word_id}", response_class=HTMLResponse)
    def word_detail(request: Request, kind: str, word_id: str, refresh: bool = False) -> HTMLResponse:
        spec = known_word_kind(kind)
        if spec is None:
            raise HTTPException(404, f"unknown kind {kind}")
        item = _find_item(directory(refresh=refresh), word_id)
        if item is None or item.get("kind") != "action_word" or item.get("category") != kind:
            raise HTTPException(404, f"unknown word {word_id}")
        return _render(
            request,
            spec.detail_template,
            item=item,
            kind=spec,
            form_action=f"/tools/{item['id']}/run",
        )

    @app.post("/words/{kind}/{word_id}/run")
    async def word_run(request: Request, kind: str, word_id: str) -> RedirectResponse:
        spec = known_word_kind(kind)
        if spec is None:
            raise HTTPException(404, f"unknown kind {kind}")
        return await _run_from_form(request, repo, word_id)

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request) -> HTMLResponse:
        return _render(request, "history.html", runs=_list_runs(repo))

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: str) -> HTMLResponse:
        run = _load_run(repo, run_id)
        if run is None:
            raise HTTPException(404, f"unknown run {run_id}")
        return _render(request, "run.html", run=run)

    @app.get("/env", response_class=HTMLResponse)
    def env_page(request: Request) -> HTMLResponse:
        return _render(request, "env.html", env_state=_env_view(repo))

    @app.post("/env")
    async def env_switch(request: Request) -> RedirectResponse:
        form = await _parse_urlencoded(request)
        name = (form.get("name") or "").strip()
        error = _switch_env(repo, name)
        if error:
            raise HTTPException(400, error)
        return RedirectResponse(url="/env", status_code=303)

    @app.get("/ai", response_class=HTMLResponse)
    def ai_page(request: Request, kind: str = "", q: str = "") -> HTMLResponse:
        catalog = _ai_catalog(repo, kind=kind, q=q)
        return _render(
            request,
            "ai.html",
            catalog=catalog,
            kind=kind,
            q=q,
            kind_tabs=KIND_META,
        )

    @app.get("/ai/{kind}/{name}", response_class=HTMLResponse)
    def ai_detail(request: Request, kind: str, name: str) -> HTMLResponse:
        item = find_component(kind, name, root=repo)
        if item is None:
            raise HTTPException(404, f"unknown AI component {kind}:{name}")
        intro = read_component_intro(repo, item.get("path") or "")
        return _render(request, "ai_detail.html", item=item, intro=intro)

    @app.get("/knowledge", response_class=HTMLResponse)
    def knowledge(request: Request, refresh: bool = False) -> HTMLResponse:
        payload = catalog(refresh=refresh)
        return _render(
            request,
            "knowledge.html",
            assets=payload.get("knowledge", {}).get("assets", []),
            inbox=payload.get("artifacts", {}).get("inbox", {}),
            features=payload.get("tests", {}).get("features", []),
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "root": str(repo)}

    @app.get("/api/catalog")
    def api_catalog(refresh: bool = Query(False)) -> JSONResponse:
        return JSONResponse(catalog(refresh=refresh))

    @app.get("/api/directory")
    def api_directory(refresh: bool = Query(False)) -> JSONResponse:
        return JSONResponse(directory(refresh=refresh))

    @app.get("/api/tools")
    def api_tools(q: str = Query(""), kind: str = Query(""), refresh: bool = Query(False)) -> JSONResponse:
        items = _directory(directory(refresh=refresh), q)
        if kind == "tool":
            items = [it for it in items if it["kind"] == "tool"]
        elif kind:
            items = [it for it in items if it.get("category") == kind or it.get("group") == kind]
        return JSONResponse({"items": items})

    @app.get("/api/words")
    def api_words(category: str = Query(""), q: str = Query(""), refresh: bool = Query(False)) -> JSONResponse:
        items = [it for it in _directory(directory(refresh=refresh), q) if it["kind"] == "action_word"]
        if category:
            items = [it for it in items if it.get("category") == category]
        return JSONResponse({"items": items})

    @app.post("/api/tools/{item_id}/run")
    def api_run(item_id: str, body: dict[str, Any] | None = None) -> JSONResponse:
        body = body or {}
        params = body.get("params") if isinstance(body.get("params"), dict) else {
            k: v for k, v in body.items() if k not in {"confirm", "params"}
        }
        confirm = bool(body.get("confirm"))
        try:
            result = run_tool(RunRequest(tool_id=item_id, params=params, confirm=confirm), root=repo)
        except DestructiveNotConfirmed as exc:
            raise HTTPException(400, str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(result.to_dict())

    @app.get("/api/runs")
    def api_runs() -> JSONResponse:
        return JSONResponse({"runs": _list_runs(repo)})

    @app.get("/api/ai")
    def api_ai(kind: str = Query(""), q: str = Query("")) -> JSONResponse:
        return JSONResponse(_ai_catalog(repo, kind=kind, q=q))

    @app.get("/api/env")
    def api_env() -> JSONResponse:
        return JSONResponse(_env_view(repo))

    @app.post("/api/env")
    def api_env_switch(body: dict[str, Any] | None = None) -> JSONResponse:
        body = body or {}
        name = str(body.get("name") or "").strip()
        error = _switch_env(repo, name)
        if error:
            raise HTTPException(400, error)
        return JSONResponse(_env_view(repo))

    return app


async def _run_from_form(request: Request, repo: Path, item_id: str) -> RedirectResponse:
    form = await _parse_urlencoded(request)
    try:
        params = json.loads(form.get("params_json") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"invalid params JSON: {exc}") from exc
    if not isinstance(params, dict):
        raise HTTPException(400, "params must be a JSON object")
    confirm = bool(form.get("confirm"))
    try:
        result = run_tool(RunRequest(tool_id=item_id, params=params, confirm=confirm), root=repo)
    except DestructiveNotConfirmed as exc:
        raise HTTPException(400, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(url=f"/runs/{result.run_id}", status_code=303)


def _directory(payload: dict[str, Any], q: str) -> list[dict[str, Any]]:
    needle = (q or "").strip().lower()
    items: list[dict[str, Any]] = []
    for row in payload.get("tools", []):
        if row.get("visibility") == "local":
            continue
        items.append(_tool_item(row))
    for row in payload.get("action_words", []):
        if "word_id" not in row or row.get("visibility") == "local":
            continue
        items.append(_word_item(row))
    if needle:
        items = [it for it in items if needle in it["id"].lower() or needle in (it.get("name") or "").lower()]
    return items


def _tool_item(row: dict[str, Any]) -> dict[str, Any]:
    schema = row.get("params_schema") or {}
    props = schema.get("properties") or {}
    return {
        "id": row["tool_id"],
        "kind": "tool",
        "name": row.get("name") or row["tool_id"],
        "group": row.get("group") or "general",
        "category": None,
        "summary": row.get("summary") or "",
        "doc": row.get("summary") or "",
        "datasource": "",
        "tags": [],
        "example_params": {},
        "destructive": bool(row.get("destructive")),
        "params_schema": schema,
        "has_dry_run": "dry_run" in props,
        "visibility": row.get("visibility") or "workbench",
        "readme_path": row.get("readme_path"),
        "origin": row.get("origin"),
        "href": f"/tools/{row['tool_id']}",
    }


def _word_item(row: dict[str, Any]) -> dict[str, Any]:
    doc = (row.get("doc") or row.get("description") or "").strip()
    schema = row.get("params_schema") or {}
    props = schema.get("properties") or {}
    category = str(row.get("category") or "action")
    word_id = row["word_id"]
    return {
        "id": word_id,
        "kind": "action_word",
        "name": row.get("name") or word_id,
        "group": category,
        "category": category,
        "summary": doc.splitlines()[0][:200] if doc else "",
        "doc": doc,
        "datasource": row.get("datasource") or "",
        "tags": list(row.get("tags") or []),
        "example_params": dict(row.get("example_params") or {}),
        "destructive": bool(row.get("destructive")),
        "params_schema": schema,
        "has_dry_run": "dry_run" in props,
        "visibility": row.get("visibility") or "workbench",
        "readme_path": None,
        "origin": "workspace",
        "href": f"/words/{category}/{word_id}",
    }


def _find_item(payload: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for it in _directory(payload, ""):
        if it["id"] == item_id:
            return it
    return None


def _ai_catalog(root: Path, *, kind: str = "", q: str = "") -> dict[str, Any]:
    payload = collect_catalog(root)
    needle = (q or "").strip().lower()
    wanted = (kind or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in payload.get("items") or []:
        if wanted and row.get("kind") != wanted:
            continue
        if needle:
            hay = " ".join(
                str(row.get(key) or "")
                for key in ("name", "kind", "version", "trigger", "scope", "description", "path")
            ).lower()
            if needle not in hay:
                continue
        filtered.append(row)
    groups: list[dict[str, Any]] = []
    for meta in KIND_META:
        kid, title, blurb = meta
        if wanted and kid != wanted:
            continue
        items = [row for row in filtered if row.get("kind") == kid]
        groups.append({"kind": kid, "title": title, "blurb": blurb, "entries": items})
    payload["groups"] = groups
    payload["items"] = filtered
    payload["shown"] = len(filtered)
    return payload


def _env_view(root: Path) -> dict[str, Any]:
    """Named environments only — never include credentials or URLs."""
    from tuner_testkit.config import (
        EnvProfileError,
        environments_of,
        load_env_local,
        read_active_env_file,
        resolve_active_name,
    )

    os.environ["TUNER_ROOT"] = str(root)
    local = load_env_local()
    envs = environments_of(local) if local is not None else None
    if not envs:
        return {"mode": "missing", "available": [], "active": None}
    names = sorted(str(k) for k in envs)
    try:
        active = resolve_active_name(
            available=names,
            module_default=str(getattr(local, "ACTIVE_ENV", None) or "") or None,
            active_file_text=read_active_env_file(),
        )
    except EnvProfileError:
        active = None
    return {"mode": "named", "available": names, "active": active}


def _switch_env(root: Path, name: str) -> str | None:
    from tuner_testkit.config import environments_of, load_env_local, write_active_env

    os.environ["TUNER_ROOT"] = str(root)
    if not name:
        return "environment name is required"
    local = load_env_local()
    if local is None:
        return "no config/env_local.py — copy the example and fill values on this machine"
    envs = environments_of(local)
    if envs is None:
        return "env_local.py has no ENVIRONMENTS map"
    if name not in envs:
        return f"unknown environment {name!r}; available: {sorted(envs)}"
    write_active_env(name)
    return None


async def _parse_urlencoded(request: Request) -> dict[str, str]:
    """Parse application/x-www-form-urlencoded without python-multipart."""
    from urllib.parse import parse_qs

    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _readme_text(root: Path, item: dict[str, Any]) -> str:
    rel = item.get("readme_path")
    if not rel:
        return ""
    path = root / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _list_runs(root: Path) -> list[dict[str, Any]]:
    base = root / "artifacts" / "runs"
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for child in sorted(base.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        manifest = child / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data["dir"] = str(child)
        rows.append(data)
    return rows


def _load_run(root: Path, run_id: str) -> dict[str, Any] | None:
    for row in _list_runs(root):
        if row.get("run_id") == run_id:
            run_dir = Path(row["dir"])
            stdout = run_dir / "stdout.log"
            stderr = run_dir / "stderr.log"
            envelope = run_dir / "envelope.json"
            row["stdout"] = stdout.read_text(encoding="utf-8", errors="replace") if stdout.is_file() else ""
            row["stderr"] = stderr.read_text(encoding="utf-8", errors="replace") if stderr.is_file() else ""
            if envelope.is_file():
                try:
                    row["envelope"] = json.loads(envelope.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    row["envelope"] = None
            row["result"] = _action_result(row)
            return row
    return None


def _action_result(run: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort Result dict (cleanup / detail) from envelope or pretty-printed stdout."""
    envelope = run.get("envelope")
    if isinstance(envelope, dict) and ("cleanup" in envelope or "ok" in envelope or "detail" in envelope):
        return envelope
    text = (run.get("stdout") or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and ("cleanup" in data or "ok" in data or "detail" in data):
        return data
    return None
