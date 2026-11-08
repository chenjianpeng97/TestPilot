"""Collect dashboard numbers for one workspace, section by section.

Runs offline (``tuner-dashboard refresh``), never inside a workbench request.
Every section is timed and isolated: a failing section records ``error`` and the
others still land. Scans are bounded and static — no ``build_catalog``, no
per-file ``git log``, no imports of workspace ``apps`` or action words.
"""
from __future__ import annotations

import ast
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from tuner_testkit.catalog.front_matter import parse_front_matter
from tuner_testkit.catalog.scan import (
    MAX_PARSE_BYTES,
    MAX_SCAN_FILES,
    SKIP_DIR_NAMES,
    scan_api_objects,
    scan_features,
    scan_page_objects,
)

SECTIONS: tuple[str, ...] = ("assets", "automation", "tools", "doctor", "config")
WORD_CATEGORIES: tuple[str, ...] = ("db_seed", "db_assert", "api_request", "api_assert", "ui_action", "ui_assert")
ARCHIVE_DIRS = frozenset({"archived", "_archive"})
HEAD_BYTES = 8192
TEST_FN_RE = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.M)

# One line per kit console script; tests assert every installed tuner-* command is listed.
KIT_COMMANDS: dict[str, str] = {
    "tuner-workspace": "catalog / index 渲染 / doctor 体检 / changelog / 布局迁移",
    "tuner-workbench": "本机 127.0.0.1 工作台：看板、工具目录、表单运行、运行历史",
    "tuner-dashboard": "统计看板数字，写 DASHBOARD.md 与 artifacts/catalogs/dashboard.json",
    "tuner-config": "查看、切换、校验环境配置（密钥打码）",
    "tuner-task": "入库任务、阻塞提问与回答",
    "tuner-testreport": "测试单计数与一致性检查，出 GJB438B 报告",
    "tuner-evidence": "网络 dump 脱敏落盘，挂截图、日志、接口 JSON",
    "tuner-action-words": "列出与运行动作词（db_seed 等）",
    "tuner-fake": "业务假数据（UDI、社信码、金额等）",
    "tuner-dump-ddl": "拉取表结构到 knowledge/ddl",
    "tuner-openapi-import": "从 OpenAPI / Swagger 冻结 API 对象",
    "tuner-recorder": "headed 合录页面与接口",
    "tuner-api-recorder": "mitmproxy 代理冻结 API 对象",
    "tuner-page-recorder": "headed 录制冻结页面对象",
    "tuner-page-test": "页面对象运行时与定位体检",
    "tuner-mock-server": "按 data/mocks 回放接口",
    "tuner-dna": "同步 kit 所带 DNA（rules / skills / specs / hooks）",
    "tuner-index-ai": "生成 .cursor/REGISTRY.md",
    "tuner-init": "新仓骨架 scaffold",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def collect(
    root: Path,
    *,
    sections: Iterable[str] | None = None,
    doctor_config_loader: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Return ``{"checked_at", "root", "sections": {name: payload}, "timings": {name: ms}}``."""
    root = Path(root).resolve()
    wanted = [s for s in (sections or SECTIONS) if s in SECTIONS]
    runners: dict[str, Callable[[], dict[str, Any]]] = {
        "assets": lambda: collect_assets(root),
        "automation": lambda: collect_automation(root),
        "tools": lambda: collect_tools(root),
        "doctor": lambda: collect_doctor(root, config_loader=doctor_config_loader),
        "config": lambda: collect_config(root),
    }
    out: dict[str, Any] = {}
    timings: dict[str, int] = {}
    for name in wanted:
        started = time.perf_counter()
        try:
            out[name] = runners[name]()
        except Exception as exc:  # noqa: BLE001 -- one broken section must not hide the others
            out[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        timings[name] = int((time.perf_counter() - started) * 1000)
    return {"checked_at": now_iso(), "root": str(root), "sections": out, "timings": timings}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class _Walk:
    """Bounded ``os.walk`` that skips cache / venv folders and remembers truncation."""

    def __init__(self) -> None:
        self.truncated: list[str] = []

    def files(self, base: Path, suffixes: tuple[str, ...]) -> list[Path]:
        found: list[Path] = []
        if not base.is_dir():
            return found
        seen = 0
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
            for name in sorted(filenames):
                seen += 1
                if seen > MAX_SCAN_FILES:
                    self.truncated.append(base.name)
                    return found
                if name.lower().endswith(suffixes):
                    found.append(Path(dirpath) / name)
        return found


def _head(path: Path, size: int = HEAD_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(size).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_PARSE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _ranked(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


# ---------------------------------------------------------------------------
# assets: testcases, testsheets, defects, requirements
# ---------------------------------------------------------------------------
def collect_assets(root: Path) -> dict[str, Any]:
    walk = _Walk()
    cases_dir = root / "assets" / "testcases"
    by_module: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for path in walk.files(cases_dir, (".md",)):
        if path.name in {"README.md", "CHANGELOG.md"}:
            continue
        parts = path.relative_to(cases_dir).parts
        module = parts[0] if len(parts) > 1 else "(根目录)"
        by_module[module] = by_module.get(module, 0) + 1
        status = str(parse_front_matter(_head(path)).get("status") or "未标注")
        by_status[status] = by_status.get(status, 0) + 1

    active, archived = _testsheets(root)
    defects: dict[str, int] = {}
    defect_dir = root / "knowledge" / "defects"
    if defect_dir.is_dir():
        for path in sorted(defect_dir.glob("DEF-*.md")):
            status = str(parse_front_matter(_head(path)).get("status") or "?")
            defects[status] = defects.get(status, 0) + 1
    req_dir = root / "knowledge" / "requirements"
    requirements = sum(1 for p in req_dir.glob("*.md") if p.name != "CHANGELOG.md") if req_dir.is_dir() else 0
    return {
        "testcases": {
            "total": sum(by_module.values()),
            "by_module": _ranked(by_module),
            "by_status": _ranked(by_status),
        },
        "testsheets": {"active": active, "archived": archived},
        "defects": {"total": sum(defects.values()), "by_status": _ranked(defects)},
        "requirements": requirements,
        "truncated": walk.truncated,
    }


def _testsheets(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    base = root / "assets" / "testsheet"
    active: list[dict[str, Any]] = []
    archived: list[str] = []
    if not base.is_dir():
        return active, archived
    for child in sorted(p for p in base.iterdir() if p.is_dir()):
        if child.name in ARCHIVE_DIRS:
            archived.extend(sorted(sheet.parent.name for sheet in child.rglob("testsheet.md")))
            continue
        if child.name.startswith((".", "_")) or not (child / "testsheet.md").is_file():
            continue
        active.append(_round_stats(root, child))
    return active, archived


def _round_stats(root: Path, folder: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"round": folder.name, "path": _rel(root, folder)}
    try:
        from tuner_testkit.apps.testreport.stats import build

        data = build([folder], root=root)
    except Exception as exc:  # noqa: BLE001 -- a malformed sheet still shows up as a round
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return row
    rows = data["rows"]
    row.update(
        {
            "total": rows["total"],
            "passed": rows.get("通过", 0),
            "failed": rows.get("失败", 0),
            "blocked": rows.get("阻塞", 0),
            "ignored": rows.get("忽略", 0),
            "pending": data["final"]["pending"],
            "defects": data["defects"]["total"],
            "defects_open": data["defects"]["open"],
            "issues": data["errors"],
        }
    )
    return row


# ---------------------------------------------------------------------------
# automation: api / page objects, action words, behave, pytest
# ---------------------------------------------------------------------------
def collect_automation(root: Path) -> dict[str, Any]:
    walk = _Walk()
    api = scan_api_objects(root)
    api_base = root / "packages" / "api_objects"
    by_group: dict[str, int] = {}
    methods: dict[str, int] = {}
    for row in api:
        parts = Path(row["file"]).relative_to("packages/api_objects").parts if row["file"].startswith("packages/api_objects/") else ()
        group = parts[0] if len(parts) > 1 else "(根目录)"
        by_group[group] = by_group.get(group, 0) + 1
        methods[row["method"]] = methods.get(row["method"], 0) + 1
    pages = [{"page_id": p["page_id"], "app": p["app"], "path": p["path"]} for p in scan_page_objects(root)]
    words = _static_words(root, walk)
    by_category = {cat: sum(1 for w in words if w["category"] == cat) for cat in WORD_CATEGORIES}
    features = [
        {"path": f["path"], "name": f["name"], "scenarios": len(f["scenarios"]), "tags": list(f.get("tags") or [])}
        for f in scan_features(root)
    ]
    pytest_rows = []
    for path in walk.files(root / "tests" / "pytest", (".py",)):
        if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            continue
        pytest_rows.append({"path": _rel(root, path), "tests": len(TEST_FN_RE.findall(_text(path)))})
    return {
        "api_objects": {"total": len(api), "by_group": _ranked(by_group), "by_method": _ranked(methods), "dir_exists": api_base.is_dir()},
        "page_objects": {"total": len(pages), "items": pages},
        "action_words": {"total": len(words), "by_category": by_category, "items": words},
        "bdd": {"features": len(features), "scenarios": sum(f["scenarios"] for f in features), "items": features},
        "pytest": {"files": len(pytest_rows), "tests": sum(r["tests"] for r in pytest_rows), "items": pytest_rows},
        "truncated": walk.truncated,
    }


def _static_words(root: Path, walk: _Walk) -> list[dict[str, Any]]:
    """``@register`` classes with literal ``word_id`` / ``name`` (no import of workspace code)."""
    base = root / "packages" / "action_words"
    rows: list[dict[str, Any]] = []
    for category in WORD_CATEGORIES:
        for path in walk.files(base / category, (".py",)):
            if path.name.startswith("_") or any(part.startswith("_") for part in path.relative_to(base).parts[:-1]):
                continue
            try:
                tree = ast.parse(_text(path))
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or not any(_decorator_name(d) == "register" for d in node.decorator_list):
                    continue
                attrs = _class_literals(node)
                word_id = str(attrs.get("word_id") or f"{category}.{node.name}")
                rows.append(
                    {
                        "id": word_id,
                        "name": str(attrs.get("name") or ""),
                        "category": word_id.split(".", 1)[0] if word_id.split(".", 1)[0] in WORD_CATEGORIES else category,
                        "path": _rel(root, path),
                    }
                )
    return sorted(rows, key=lambda r: r["id"])


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _class_literals(node: ast.ClassDef) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            if isinstance(stmt.value, ast.Constant):
                out[stmt.targets[0].id] = stmt.value.value
    return out


# ---------------------------------------------------------------------------
# tools: kit commands + workspace apps (static @tool parse)
# ---------------------------------------------------------------------------
def collect_tools(root: Path) -> dict[str, Any]:
    from importlib.metadata import PackageNotFoundError, distribution

    kit_apps = Path(__file__).resolve().parent.parent
    runnable_modules = {
        f"tuner_testkit.apps.{child.name}" for child in kit_apps.iterdir() if child.is_dir() and (child / "tool.py").is_file()
    }
    try:
        eps = [ep for ep in distribution("tuner-testkit").entry_points if ep.group == "console_scripts"]
        kit_version = distribution("tuner-testkit").version
    except PackageNotFoundError:
        eps, kit_version = [], None
    commands = []
    for ep in sorted(eps, key=lambda e: e.name):
        module = ep.value.split(":", 1)[0]
        commands.append(
            {
                "command": ep.name,
                "summary": KIT_COMMANDS.get(ep.name, ""),
                "workbench": any(module == m or module.startswith(m + ".") for m in runnable_modules),
            }
        )
    apps_dir = root / "apps"
    workspace: list[dict[str, Any]] = []
    without_tool: list[str] = []
    if apps_dir.is_dir():
        for child in sorted(apps_dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            tool_file = child / "tool.py"
            if not tool_file.is_file():
                without_tool.append(child.name)
                continue
            workspace.append(_static_tool(child.name, tool_file))
    return {"kit_version": kit_version, "kit_commands": commands, "workspace": workspace, "workspace_without_tool": without_tool}


def _static_tool(dir_name: str, path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"id": dir_name, "name": dir_name, "summary": "", "group": "general", "port": None,
                           "destructive": False, "visibility": "workbench"}
    try:
        tree = ast.parse(_text(path))
    except SyntaxError as exc:
        row["error"] = f"SyntaxError: {exc.msg}"
        return row
    for node in ast.walk(tree):
        # Both ``@tool(...)`` and ``build_parser = tool(...)(_build_parser)``.
        if isinstance(node, ast.Call) and _decorator_name(node) == "tool" and any(kw.arg == "tool_id" for kw in node.keywords):
            for kw in node.keywords:
                if kw.arg and isinstance(kw.value, ast.Constant):
                    key = "id" if kw.arg == "tool_id" else kw.arg
                    if key in row:
                        row[key] = kw.value.value
            return row
    row["error"] = "tool.py 里没有找到 @tool(...)"
    return row


# ---------------------------------------------------------------------------
# doctor + config
# ---------------------------------------------------------------------------
def collect_doctor(root: Path, *, config_loader: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    from tuner_testkit.workspace.doctor import run_doctor

    result = run_doctor(root, config_loader=config_loader)
    return {
        "ok": result["ok"],
        "summary_core": result["summary_core"],
        "summary_feature": result["summary_feature"],
        "checks": result["checks"],
        "capabilities": result["capabilities"],
    }


def collect_config(root: Path) -> dict[str, Any]:
    from tuner_testkit.config import describe_environments, describe_project_config
    from tuner_testkit.project import reset_path_cache

    old = os.environ.get("TUNER_ROOT")
    os.environ["TUNER_ROOT"] = str(root)
    reset_path_cache()
    try:
        envs = describe_environments()
        view = describe_project_config()
    finally:
        if old is None:
            os.environ.pop("TUNER_ROOT", None)
        else:
            os.environ["TUNER_ROOT"] = old
        reset_path_cache()
    knowledge = view.get("knowledge") or {}
    return {
        **envs,
        "error": view.get("error"),
        "channels": {k: v for k, v in (view.get("channels") or {}).items() if isinstance(v, str)},
        "ports": {k: v for k, v in (view.get("ports") or {}).items() if isinstance(v, str)},
        "knowledge": {
            "source_roots": len(knowledge.get("source_roots") or []),
            "api_docs": len(knowledge.get("api_docs") or []),
        },
    }
