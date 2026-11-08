"""Turn collected sections into ``DASHBOARD.md`` (committed) and ``dashboard.json`` (local).

``DASHBOARD.md`` only carries flat counts, so it changes only when a number
changes; its ``updated`` field is the time of that last change. The JSON keeps
every section (doctor, config, per-round progress) plus ``checked_at``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tuner_testkit.catalog.front_matter import parse_front_matter

MARKDOWN_NAME = "DASHBOARD.md"
JSON_REL = Path("artifacts") / "catalogs" / "dashboard.json"
SCHEMA = 1

# (table, key, label): table order and labels for DASHBOARD.md.
COUNT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("测试资产", "testcases", "测试用例"),
    ("测试资产", "testsheets_active", "进行中测试单"),
    ("测试资产", "testsheets_archived", "已归档测试单"),
    ("测试资产", "requirements", "需求"),
    ("测试资产", "defects", "缺陷"),
    ("自动化覆盖", "api_objects", "API 对象"),
    ("自动化覆盖", "page_objects", "UI 页面对象"),
    ("自动化覆盖", "action_words", "动作词"),
    ("自动化覆盖", "db_seeds", "其中 db_seed"),
    ("自动化覆盖", "bdd_features", "BDD feature 文件"),
    ("自动化覆盖", "bdd_scenarios", "BDD 场景"),
    ("自动化覆盖", "pytest_files", "pytest 文件"),
    ("自动化覆盖", "pytest_tests", "pytest 用例"),
    ("工具", "kit_commands", "工作台通用命令（tuner-*）"),
    ("工具", "workspace_tools", "项目自建工具（apps/ 带 tool.py）"),
    ("工具", "workspace_apps_without_tool", "项目自建工具（apps/ 无 tool.py）"),
)
COUNT_KEYS: tuple[str, ...] = tuple(key for _, key, _ in COUNT_ROWS)


def flat_counts(sections: dict[str, Any]) -> dict[str, int]:
    """Counts from sections that collected cleanly; failed sections contribute nothing."""
    out: dict[str, int] = {}
    assets = sections.get("assets") or {}
    if assets and "error" not in assets:
        out.update(
            testcases=assets["testcases"]["total"],
            testsheets_active=len(assets["testsheets"]["active"]),
            testsheets_archived=len(assets["testsheets"]["archived"]),
            requirements=assets["requirements"],
            defects=assets["defects"]["total"],
        )
    auto = sections.get("automation") or {}
    if auto and "error" not in auto:
        out.update(
            api_objects=auto["api_objects"]["total"],
            page_objects=auto["page_objects"]["total"],
            action_words=auto["action_words"]["total"],
            db_seeds=auto["action_words"]["by_category"].get("db_seed", 0),
            bdd_features=auto["bdd"]["features"],
            bdd_scenarios=auto["bdd"]["scenarios"],
            pytest_files=auto["pytest"]["files"],
            pytest_tests=auto["pytest"]["tests"],
        )
    tools = sections.get("tools") or {}
    if tools and "error" not in tools:
        out.update(
            kit_commands=len(tools["kit_commands"]),
            workspace_tools=len(tools["workspace"]),
            workspace_apps_without_tool=len(tools["workspace_without_tool"]),
        )
    return out


def read_markdown(path: Path) -> dict[str, Any]:
    """Front-matter of an existing ``DASHBOARD.md`` (``{}`` when absent or unreadable)."""
    try:
        return parse_front_matter(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def render_markdown(counts: dict[str, int], *, updated: str, kit_version: str | None) -> str:
    lines = ["---", f'updated: "{updated}"', f'kit_version: "{kit_version or ""}"']
    lines += [f"{key}: {counts[key]}" for key in COUNT_KEYS if key in counts]
    lines += [
        "---",
        "",
        "# 工作台看板计数",
        "",
        "> 由 `tuner-dashboard refresh`（skill `refresh-dashboard`）生成，请勿手改。",
        f"> `updated` 是计数最后一次变化的时间：{updated}。",
        "> 逐轮进度、工作台自检与环境配置只在本机 `artifacts/catalogs/dashboard.json`，在工作台首页查看。",
    ]
    table = None
    for name, key, label in COUNT_ROWS:
        if key not in counts:
            continue
        if name != table:
            table = name
            lines += ["", f"## {name}", "", "| 指标 | 数量 |", "| --- | ---: |"]
        lines.append(f"| {label} | {counts[key]} |")
    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, Any], *, root: Path, out_dir: Path | None = None) -> dict[str, Any]:
    """Write both outputs; ``DASHBOARD.md`` only when counts or kit version changed."""
    md_path = (out_dir or root) / MARKDOWN_NAME
    json_path = out_dir / JSON_REL.name if out_dir else root / JSON_REL
    sections = result["sections"]
    kit_version = (sections.get("tools") or {}).get("kit_version")
    previous = read_markdown(md_path)
    old_counts = {key: int(previous[key]) for key in COUNT_KEYS if isinstance(previous.get(key), int)}
    counts = {**old_counts, **flat_counts(sections)}
    old_kit = str(previous.get("kit_version") or "") or None
    changed = counts != old_counts or (kit_version or None) != old_kit or not md_path.is_file()
    updated = result["checked_at"] if changed else str(previous.get("updated") or result["checked_at"])
    if changed:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(counts, updated=updated, kit_version=kit_version), encoding="utf-8", newline="\n")
    payload = {
        "schema": SCHEMA,
        "checked_at": result["checked_at"],
        "updated": updated,
        "kit_version": kit_version,
        "counts": counts,
        "timings": result["timings"],
        "sections": sections,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    delta = {key: f"{old_counts.get(key)} -> {value}" for key, value in counts.items() if old_counts and old_counts.get(key) != value}
    return {
        "changed": changed,
        "markdown": str(md_path),
        "json": str(json_path),
        "checked_at": result["checked_at"],
        "updated": updated,
        "counts": counts,
        "delta": delta,
        "errors": {name: sec["error"] for name, sec in sections.items() if isinstance(sec, dict) and sec.get("error")},
    }
