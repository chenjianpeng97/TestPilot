"""Allocate defect ids and write a new defect file from the fixed template."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tuner_testkit.catalog.front_matter import dump_front_matter
from tuner_testkit.defects.validate import DEFECT_ID, PLACEHOLDER, SEVERITIES, STATUSES, TYPES, defect_files


def next_id(root: Path, day: date | None = None) -> str:
    """``DEF-<yyyymmdd>-<nnn>``: the next free sequence number for *day* (default today)."""
    stamp = (day or date.today()).strftime("%Y%m%d")
    used = [
        int(m.group("seq"))
        for p in defect_files(root)
        if (m := DEFECT_ID.match(p.stem)) and m.group("day") == stamp
    ]
    return f"DEF-{stamp}-{max(used, default=0) + 1:03d}"


def render(
    defect_id: str,
    *,
    title: str,
    severity: str,
    defect_type: str,
    found: str,
    status: str = "激活",
    blocking: bool = False,
    found_in: str = "/",
    testcase: str = "/",
    round_name: str = "/",
    requirements: list[str] | None = None,
    sut_version: str | None = None,
    env: str | None = None,
) -> str:
    meta: dict[str, object] = {
        "kind": "defect",
        "id": defect_id,
        "title": title,
        "severity": severity,
        "type": defect_type,
        "status": status,
        "blocking": blocking,
        "found": found,
        "found_in": found_in,
        "testcase": testcase,
    }
    if requirements:
        meta["requirements"] = requirements
    if sut_version:
        meta["sut_version"] = sut_version
    if env:
        meta["env"] = env
    meta["version"] = "1.0.0"
    body = (
        f"\n# {defect_id} {title}\n\n"
        f"## 现象\n\n{PLACEHOLDER}\n\n"
        f"## 复现步骤\n\n1. {PLACEHOLDER}\n\n"
        f"## 预期结果\n\n{PLACEHOLDER}\n\n"
        f"## 实际结果\n\n{PLACEHOLDER}\n\n"
        "## 证据\n\n<!-- 截图、日志、接口响应的路径；没有就删掉本节 -->\n\n"
        "## 历史\n\n"
        "| 日期 | 轮次 | 状态 | 说明 |\n"
        "| --- | --- | --- | --- |\n"
        f"| {found} | {round_name} | {status} | 首次记录 |\n"
    )
    return dump_front_matter(meta) + body


def create(root: Path, *, day: date | None = None, **fields: object) -> Path:
    """Write ``knowledge/defects/<next id>.md`` from the template; returns the path."""
    for key, allowed in (("severity", SEVERITIES), ("defect_type", TYPES), ("status", STATUSES)):
        value = fields.get(key, "激活" if key == "status" else None)
        if value not in allowed:
            raise ValueError(f"{key} must be one of {' / '.join(allowed)}")
    root.mkdir(parents=True, exist_ok=True)
    found_day = day or date.today()
    defect_id = next_id(root, found_day)
    path = root / f"{defect_id}.md"
    path.write_text(render(defect_id, found=found_day.isoformat(), **fields), encoding="utf-8", newline="\n")  # type: ignore[arg-type]
    return path
