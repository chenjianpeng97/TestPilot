"""``tuner-workspace doctor``: deterministic health check of a TestPilot workspace.

The ``health-check`` skill reads this JSON and decides what to do with each
gap: ``maintain-config`` for configuration, ``dump-ddl`` / ``maintain-wiki`` for
knowledge, ``tuner-task ask`` for decisions only a person can make (log channel),
``upgrade-framework`` for DNA drift. Nothing here writes to the workspace or
prints a secret.

Statuses: ``ok`` · ``info`` · ``warn`` · ``missing`` · ``error``.

Tiers: every check carries ``tier``. ``core`` is what any workspace needs
(layout, UI / API URLs, databases, accounts, browser channel, DNA, git hooks) and
alone decides ``ok``. ``feature`` checks (knowledge, ports, traceability) are
prerequisites of individual capabilities.

Capabilities: ``capabilities[]`` maps each thing the AI components can do (execute a
test sheet, explore the SUT, read source, query backend logs ...) to the checks it
needs, with ``ready`` and the missing checks. ``health-check`` asks the user which
capabilities they intend to use and fills only those gaps.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from tuner_testkit.catalog.front_matter import parse_front_matter

STATUSES = ("ok", "info", "warn", "missing", "error")
REQUIRED_DIRS: tuple[str, ...] = (
    "knowledge/ddl",
    "knowledge/wiki",
    "knowledge/requirements",
    "knowledge/defects",
    "assets/testcases",
    "assets/testsheet",
    "assets/testdesign",
    "assets/testreport",
    "packages/api_objects",
    "packages/page_objects",
    "packages/action_words",
    "apps",
    "data",
    "tests",
    "config",
    "work/tasks",
)
LEGACY_DIRS: tuple[str, ...] = ("assets/ddl", "assets/domain-notes", "assets/usecases", "assets/explore", "assets/design")
REQ_ID_RE = re.compile(r"\bREQ-[A-Za-z0-9][A-Za-z0-9_-]*\b")
DEFAULT_STALE_DAYS = 90
# Check-id prefixes (the part before the first dot) that belong to the feature tier.
FEATURE_GROUPS: frozenset[str] = frozenset({"knowledge", "ports", "trace"})

# capability id -> (title, skills / agents that rely on it, required check ids)
CAPABILITIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("assets", "写用例 / 测试单 / 测试设计 / 缺陷", "maintain-testcases, maintain-testsheet, derive-test-design, maintain-defectlib",
     ("layout.dirs",)),
    ("ui-run", "浏览器点击执行（测试单、测试设计）", "execute-testsheet, run-test-execution",
     ("config.ui_url", "data.accounts", "channels.browser")),
    ("explore", "探索被测系统（自学习）", "sut-self-learning, explore-sut",
     ("config.ui_url", "data.accounts", "channels.browser")),
    ("api-auto", "接口自动化（behave / pytest）", "maintain-bdd-assets, maintain-pytest, freeze-api-objects",
     ("config.api_url", "data.accounts")),
    ("db-check", "数据核对 / 造数", "maintain-pytest, create-action-word",
     ("config.databases",)),
    ("ddl", "导出表结构", "dump-ddl", ("config.databases", "knowledge.ddl")),
    ("source", "读被测系统源码生成设计知识", "sut-source-to-design", ("knowledge.source_roots",)),
    ("api-docs", "导入接口文档（OpenAPI）", "tuner-openapi-import, freeze-api-objects", ("knowledge.api_docs",)),
    ("backend-log", "查询后端日志做取证", "execute-testsheet, run-test-execution", ("ports.log-source",)),
    ("wiki", "沉淀需求与业务知识", "maintain-wiki", ("knowledge.wiki",)),
)


class _Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, check_id: str, status: str, detail: str, *, fix: str = "", group: str = "") -> None:
        assert status in STATUSES, status
        prefix = check_id.split(".", 1)[0]
        tier = "feature" if (group or prefix) in FEATURE_GROUPS or prefix in FEATURE_GROUPS else "core"
        self.checks.append(
            {"id": check_id, "group": group or prefix, "tier": tier, "status": status, "detail": detail, "fix": fix}
        )

    def summary(self, tier: str | None = None) -> dict[str, int]:
        rows = [c for c in self.checks if tier is None or c["tier"] == tier]
        return {status: sum(1 for c in rows if c["status"] == status) for status in STATUSES}


def _load_config(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """(``describe_project_config()``, ``validate_project_config()``) for *root*."""
    from tuner_testkit.config import describe_project_config, validate_project_config
    from tuner_testkit.project import reset_path_cache

    old = os.environ.get("TUNER_ROOT")
    os.environ["TUNER_ROOT"] = str(root)
    reset_path_cache()
    try:
        return describe_project_config(), validate_project_config(root)
    finally:
        if old is None:
            os.environ.pop("TUNER_ROOT", None)
        else:
            os.environ["TUNER_ROOT"] = old
        reset_path_cache()


def run_doctor(
    root: Path,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    check_db: bool = False,
    config_loader: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    report = _Report()
    _check_layout(root, report)
    try:
        view, validation = (config_loader or _load_config)(root)
    except Exception as exc:  # noqa: BLE001 -- a broken config must still produce a report
        view, validation = {"error": f"{type(exc).__name__}: {exc}"}, {"findings": [], "errors": 0}
    _check_config(view, validation, report)
    if check_db and not view.get("error"):
        _check_db(root, view, report)
    _check_accounts(root, report)
    _check_channels(view, report)
    _check_ports(root, view, report)
    _check_knowledge(root, view, report, stale_days=stale_days)
    _check_defects(root, report)
    _check_traceability(root, report)
    _check_dna(root, report)
    _check_hooks(root, report)
    summary = report.summary()
    core = report.summary("core")
    return {
        "root": str(root),
        "ok": core["error"] == 0 and core["missing"] == 0,
        "summary": summary,
        "summary_core": core,
        "summary_feature": report.summary("feature"),
        "capabilities": _capabilities(report.checks),
        "checks": report.checks,
    }


def _capabilities(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in checks}
    rows: list[dict[str, Any]] = []
    for cap_id, title, used_by, requires in CAPABILITIES:
        blockers = []
        for check_id in requires:
            row = by_id.get(check_id)
            if row is None:
                blockers.append({"id": check_id, "status": "missing", "detail": "检查项不存在", "fix": ""})
            elif row["status"] != "ok":
                blockers.append({"id": check_id, "status": row["status"], "detail": row["detail"], "fix": row["fix"]})
        rows.append({"id": cap_id, "title": title, "used_by": used_by, "requires": list(requires), "ready": not blockers, "blockers": blockers})
    return rows


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------
def _check_layout(root: Path, report: _Report) -> None:
    missing = [rel for rel in REQUIRED_DIRS if not (root / rel).is_dir()]
    legacy = [rel for rel in LEGACY_DIRS if (root / rel).is_dir() and any((root / rel).rglob("*.*"))]
    if legacy:
        report.add(
            "layout.legacy",
            "warn",
            f"知识仍在旧位置：{', '.join(legacy)}",
            fix="tuner-workspace migrate knowledge（先看计划）→ --apply",
        )
    if missing:
        report.add("layout.dirs", "warn", f"缺目录：{', '.join(missing)}", fix="tuner-workspace migrate knowledge --apply 会补齐")
    else:
        report.add("layout.dirs", "ok", "分层目录齐全")
    if not (root / "INDEX.project.md").is_file():
        report.add("layout.index", "missing", "没有 INDEX.project.md", fix="tuner-init scaffold 重新铺 stub，或从 kit stubs 复制")


def _check_config(view: dict[str, Any], validation: dict[str, Any], report: _Report) -> None:
    if view.get("error"):
        report.add("config.load", "error", f"读不了配置：{view['error']}", fix="maintain-config / tuner-config use <name>")
        return
    if not view.get("env_local"):
        report.add("config.env_local", "missing", "没有 config/env_local.py", fix="maintain-config（从 config/env_local.py.example 起）")
    else:
        report.add("config.env_local", "ok", f"mode={view.get('mode')} active={view.get('active_env')}")
    for check_id, key, label in (
        ("config.ui_url", "ui_base_url", "TEST_UI_BASE_URL（前端地址）"),
        ("config.api_url", "api_base_url", "TEST_BASE_URL（后端 / 网关地址）"),
    ):
        url = view.get(key) or ""
        if not url:
            report.add(check_id, "missing", f"{label} 为空", fix="maintain-config（只要 host，不要路径）")
        elif _looks_template(url):
            report.add(check_id, "warn", f"{label} 像模板示例：{url}", fix="maintain-config")
        else:
            report.add(check_id, "ok", f"{label}：{url}")
    placeholders = view.get("placeholders") or []
    db_placeholders = [p for p in placeholders if p.startswith("DATABASES.")]
    if db_placeholders:
        report.add("config.databases", "warn", f"数据源仍是占位：{', '.join(db_placeholders)}", fix="maintain-config")
    elif view.get("databases"):
        report.add("config.databases", "ok", f"别名：{', '.join(sorted(view['databases']))}")
    else:
        report.add("config.databases", "info", "没有配置任何数据源（数据核对、导出表结构需要）", fix="maintain-config")
    if validation.get("errors"):
        rows = [f"{f['code']}: {f['message']}" for f in validation.get("findings", []) if f.get("severity") == "error"]
        report.add("config.validate", "error", "；".join(rows), fix="tuner-config validate → maintain-config")
    else:
        report.add("config.validate", "ok", f"tuner-config validate 通过（warnings={validation.get('warnings', 0)}）")


def _looks_template(url: str) -> bool:
    return any(marker in url for marker in ("127.0.0.1:8080", "127.0.0.1:8081", "127.0.0.1:3000", "127.0.0.1:3001"))


def _check_db(root: Path, view: dict[str, Any], report: _Report) -> None:
    try:
        from tuner_testkit.db import DbClient
    except ImportError:
        report.add("config.db_connect", "info", "未安装 [db] extra，跳过连通性检查")
        return
    for alias in sorted(view.get("databases") or {}):
        try:
            with DbClient.for_datasource(alias) as db:
                db.fetch_scalar("SELECT 1", ())
            report.add(f"config.db_connect.{alias}", "ok", f"{alias} 可连接", group="config")
        except Exception as exc:  # noqa: BLE001
            report.add(f"config.db_connect.{alias}", "error", f"{alias} 连接失败：{type(exc).__name__}", fix="maintain-config", group="config")


def _check_accounts(root: Path, report: _Report) -> None:
    local = root / "data" / "sut-accounts.local.yaml"
    if not local.is_file():
        report.add("data.accounts", "missing", "没有 data/sut-accounts.local.yaml（探索与执行用账号）", fix="maintain-config（从 data/sut-accounts.example.yaml 起）")
        return
    text = local.read_text(encoding="utf-8", errors="replace")
    ids = re.findall(r"^\s*-\s*id:\s*(\S+)", text, re.M)
    roles = re.findall(r"^\s*role:\s*(\S+)", text, re.M)
    if not ids:
        report.add("data.accounts", "warn", "账号文件里没有 accounts[].id", fix="maintain-config")
    elif "replace-me" in text:
        report.add("data.accounts", "warn", f"账号 {', '.join(ids)} 仍有 replace-me 占位", fix="maintain-config")
    elif len(roles) < len(ids):
        report.add("data.accounts", "info", f"{len(ids)} 个账号，{len(ids) - len(roles)} 个没写 role（权限类用例挑不了账号）", fix="docs/spec/data-syntax.md")
    else:
        report.add("data.accounts", "ok", f"{len(ids)} 个账号：{', '.join(ids)}")


def _check_channels(view: dict[str, Any], report: _Report) -> None:
    from tuner_testkit.config_schema import BROWSER_CHANNELS

    browser = (view.get("channels") or {}).get("browser")
    if browser in BROWSER_CHANNELS:
        report.add("channels.browser", "ok", f"浏览器通道：{browser}")
    else:
        report.add("channels.browser", "missing", f"CHANNELS.browser={browser!r}，可选 {list(BROWSER_CHANNELS)}", fix="maintain-config")


def _check_ports(root: Path, view: dict[str, Any], report: _Report) -> None:
    from tuner_testkit.ports import PORT_CONTRACTS, port_status

    try:
        from tuner_testkit.tools import export_tools

        tools = export_tools(root, include_kit=False)
    except Exception as exc:  # noqa: BLE001
        report.add("ports.discover", "warn", f"apps/*/tool.py 导入失败：{type(exc).__name__}: {exc}", fix="修 apps/<name>/tool.py")
        tools = []
    for row in port_status(tools, view.get("ports") or {}):
        contract = PORT_CONTRACTS[row["port"]]
        check_id = f"ports.{row['port']}"
        if row["status"] == "bound":
            report.add(check_id, "ok", f"{row['port']} → {row['binding']}", group="ports")
        elif row["status"] == "broken":
            report.add(check_id, "error", "；".join(row["problems"]), fix="create-app / maintain-config", group="ports")
        elif contract.status == "draft":
            report.add(check_id, "info", f"{row['port']}（草案端口）未绑定", fix="需要时按 docs/spec/ports.md 写适配器", group="ports")
        else:
            hint = f"候选实现：{', '.join(row['implementers'])}；用 maintain-config 绑定" if row["implementers"] else (
                f"仓库没写明通道：tuner-task ask --topic {contract.ask_topic}，人回答后 create-app 实现端口"
            )
            report.add(check_id, "missing", f"{row['port']} 未绑定。{contract.summary}", fix=hint, group="ports")


def _git_epoch(root: Path, rel: str) -> float | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", rel], cwd=str(root), capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stdout.strip()
    return float(text) if text.isdigit() else None


def _check_knowledge(root: Path, view: dict[str, Any], report: _Report, *, stale_days: int) -> None:
    from tuner_testkit.catalog.scan import ddl_root

    ddl = ddl_root(root)
    sql_files = sorted(ddl.rglob("*.sql")) if ddl.is_dir() else []
    if not sql_files:
        report.add("knowledge.ddl", "missing", f"{ddl.relative_to(root).as_posix()} 没有表结构", fix="dump-ddl（需要数据库配置）")
    else:
        newest = _git_epoch(root, ddl.relative_to(root).as_posix()) or max(p.stat().st_mtime for p in sql_files)
        age = int((time.time() - newest) // 86400)
        if age > stale_days:
            report.add("knowledge.ddl", "warn", f"{len(sql_files)} 张表，最近更新 {age} 天前（阈值 {stale_days}）", fix="dump-ddl 重新导出")
        else:
            report.add("knowledge.ddl", "ok", f"{len(sql_files)} 张表，最近更新 {age} 天前")
    knowledge = view.get("knowledge") or {}
    roots = knowledge.get("source_roots") or []
    if roots:
        report.add("knowledge.source_roots", "ok", f"{len(roots)} 个源码根已配置")
    else:
        report.add("knowledge.source_roots", "info", "未配置源码根（sut-source-to-design 需要）", fix="maintain-config：KNOWLEDGE.source_roots（写在 env_local）")
    docs = knowledge.get("api_docs") or []
    if docs:
        report.add("knowledge.api_docs", "ok", f"{len(docs)} 份 API 文档已登记")
    else:
        report.add("knowledge.api_docs", "info", "未登记 API 文档；接口资产只能靠抓包冻结", fix="maintain-config：KNOWLEDGE.api_docs；有 OpenAPI 时 tuner-openapi-import")
    wiki = root / "knowledge" / "wiki"
    pages = [p for p in wiki.rglob("*.md") if p.name not in {"index.md", "log.md"}] if wiki.is_dir() else []
    if not (wiki / "index.md").is_file():
        report.add("knowledge.wiki", "missing", "没有 knowledge/wiki/index.md", fix="maintain-wiki")
    else:
        report.add("knowledge.wiki", "ok" if pages else "info", f"wiki 页面 {len(pages)} 个", fix="" if pages else "maintain-wiki ingest")


def _check_defects(root: Path, report: _Report) -> None:
    from tuner_testkit.defects.validate import defect_files, validate_dir

    folder = root / "knowledge" / "defects"
    files = defect_files(folder) if folder.is_dir() else []
    if not files:
        report.add("knowledge.defects", "info", "缺陷库为空", fix="maintain-defectlib（测试单出现缺陷或测试人报告缺陷时记录）")
        return
    counts: dict[str, int] = {}
    for path in files:
        status = str(parse_front_matter(path.read_text(encoding="utf-8", errors="replace")).get("status") or "?")
        counts[status] = counts.get(status, 0) + 1
    summary = " / ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    errors = validate_dir(folder)
    if errors:
        report.add("knowledge.defects", "error", f"{summary}；校验错误 {len(errors)}：{errors[0]}",
                   fix="uv run python -m tuner_testkit.defects check → maintain-defectlib")
    else:
        report.add("knowledge.defects", "ok", summary)


def _check_traceability(root: Path, report: _Report) -> None:
    cases_dir = root / "assets" / "testcases"
    cases = [p for p in cases_dir.rglob("*.md") if p.name not in {"README.md", "CHANGELOG.md"}] if cases_dir.is_dir() else []
    reqs = {p.stem for p in (root / "knowledge" / "requirements").glob("*.md") if p.name != "CHANGELOG.md"}
    if not cases:
        report.add("trace.requirements", "info", f"需求 {len(reqs)} 条，用例 0 条")
        return
    traced = 0
    unknown: set[str] = set()
    for path in cases:
        meta = parse_front_matter(path.read_text(encoding="utf-8", errors="replace"))
        ids = REQ_ID_RE.findall(" ".join(str(meta.get(k) or "") for k in ("source", "requirements")))
        if ids:
            traced += 1
            unknown.update(i for i in ids if i not in reqs)
    status = "ok" if traced == len(cases) else "info"
    detail = f"{traced}/{len(cases)} 条用例指向需求 ID；需求库 {len(reqs)} 条"
    if unknown:
        status = "warn"
        detail += f"；不存在的需求：{', '.join(sorted(unknown))}"
    report.add("trace.requirements", status, detail, fix="maintain-wiki（需求入库）/ maintain-testcases（source 指向 REQ-…）")


def _check_dna(root: Path, report: _Report) -> None:
    from tuner_testkit import __version__
    from tuner_testkit.apps.dna.cli import installed_dna_version, read_sync_record

    if (root / "tuner_testkit" / "project.py").is_file() or (root.parent / "tuner_testkit" / "project.py").is_file():
        report.add("dna.version", "info", "平台仓：DNA 即源码，跳过")
        return
    installed = installed_dna_version(root)
    if installed is None:
        report.add("dna.version", "missing", "没有 .tuner-dna.json（从没 sync 过 DNA）", fix="tuner-dna sync --prune")
        return
    if installed != __version__:
        report.add("dna.version", "warn", f"DNA {installed}，已安装 kit {__version__}", fix="upgrade-framework")
        return
    try:
        from tuner_testkit.apps.dna.source import dna_source_root
        from tuner_testkit.apps.dna.targets import drift_file_map, render_target

        recorded = (read_sync_record(root).get("targets") or {}).get("cursor") or {}
        drift = drift_file_map(root, render_target(dna_source_root(), "cursor"), recorded)
    except Exception as exc:  # noqa: BLE001
        report.add("dna.version", "info", f"DNA {installed}；漂移检查失败：{type(exc).__name__}")
        return
    if drift.any:
        report.add(
            "dna.version",
            "warn",
            f"DNA {installed}；缺 {len(drift.missing)}、待更新 {len(drift.outdated)}、本地改过 {len(drift.edited)}、上游已删 {len(drift.removed)}",
            fix="upgrade-framework",
        )
    else:
        report.add("dna.version", "ok", f"DNA {installed} 与 kit 一致")


def _check_hooks(root: Path, report: _Report) -> None:
    try:
        out = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"], cwd=str(root), capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return
    value = out.stdout.strip().replace("\\", "/")
    if value.endswith("tools/git-hooks"):
        report.add("hooks.git", "ok", "git hooks 已启用（提交规范、密钥扫描、changelog 检查）")
    else:
        report.add("hooks.git", "warn", "git hooks 未启用", fix="git config core.hooksPath tools/git-hooks")
