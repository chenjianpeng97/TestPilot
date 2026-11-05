"""Aggregate one or more parsed test sheets into report numbers and issues."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from . import mdparse
from .sheet import (
    PENDING,
    STEP_STATUSES,
    DEFECT_STATUSES,
    DEFECT_TYPES,
    EXECUTED_RESULTS,
    RESULTS,
    SEVERITIES,
    CaseRow,
    Issue,
    Sheet,
    parse_sheet,
    resolve_defect_cases,
)

LEVELS = {"致命": "1级", "严重": "2级", "一般": "3级", "轻微": "4级"}
UNGRADED = "未定级"
UNTYPED = "未分类"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _count(results: list[str]) -> dict[str, int]:
    counts = {name: 0 for name in RESULTS}
    counts[PENDING] = 0
    for result in results:
        if result in RESULTS:
            counts[result] += 1
        else:
            counts[PENDING] += 1
    counts_total = {"total": len(results)}
    counts_total.update(counts)
    return counts_total


def _fold(counts: dict[str, int]) -> dict[str, int]:
    passed = counts["通过"]
    failed = counts["失败"]
    # 阻塞、忽略、待执行都算「未执行」；分别给出数量供报告展开。
    not_run = counts["阻塞"] + counts["忽略"] + counts[PENDING]
    return {
        "designed": counts["total"],
        "executed": passed + failed,
        "passed": passed,
        "failed": failed,
        "not_run": not_run,
        "blocked": counts["阻塞"],
        "ignored": counts["忽略"],
        "pending": counts[PENDING],
    }


def _check_declared(sheet: Sheet, counts: dict[str, int]) -> None:
    if sheet.declared_total is not None and sheet.declared_total != counts["total"]:
        sheet.issues.append(
            Issue("error", "count_mismatch", sheet.name, f"开头写共 {sheet.declared_total} 条，表内 {counts['total']} 行")
        )
    if sheet.declared_total is None:
        sheet.issues.append(Issue("warn", "count_mismatch", sheet.name, "开头没有「共 N 条」"))
    for name in RESULTS:
        raw = sheet.declared_counts.get(name)
        if raw is None:
            sheet.issues.append(Issue("error", "count_mismatch", sheet.name, f"本轮信息没有「{name}」计数"))
            continue
        try:
            declared = int(raw.strip() or "0")
        except ValueError:
            sheet.issues.append(Issue("error", "count_mismatch", sheet.name, f"本轮信息「{name}」不是数字：{raw}"))
            continue
        if declared != counts[name]:
            sheet.issues.append(
                Issue("error", "count_mismatch", sheet.name, f"本轮信息「{name}」写 {declared}，表内 {counts[name]}")
            )


def _check_step_records(sheet: Sheet) -> None:
    """Execution records under the steps of a case copy (docs/spec/testsheet-step-record.md).

    * a record must use 执行 = 通过 / 失败 / 阻塞;
    * 失败 / 阻塞 need 实际 and 卡点, 阻塞 also needs 缺少;
    * a case whose result is 阻塞 / 失败 needs at least one 失败 / 阻塞 step with 卡点;
    * evidence paths (relative to the sheet directory) should exist.
    """
    for row in sheet.cases:
        if row.copy is None:
            continue
        stuck = 0
        for number, step in enumerate(row.copy.steps, start=1):
            where = f"{row.id} 第 {number} 步"
            if not step.status:
                if step.actual or step.blocker or step.missing or step.evidence:
                    sheet.issues.append(Issue("error", "step_record_status", sheet.name, f"{where} 写了执行记录但没有「执行：」", row.line))
                continue
            if step.status not in STEP_STATUSES:
                sheet.issues.append(
                    Issue("error", "step_record_status", sheet.name, f"{where} 「执行：{step.status}」只能是 {'、'.join(STEP_STATUSES)}", row.line)
                )
                continue
            if step.status in ("失败", "阻塞"):
                if step.blocker:
                    stuck += 1
                else:
                    sheet.issues.append(Issue("error", "step_record_blocker", sheet.name, f"{where} {step.status}但没有「卡点：」", row.line))
                if not step.actual:
                    sheet.issues.append(Issue("error", "step_record_actual", sheet.name, f"{where} {step.status}但没有「实际：」", row.line))
            if step.status == "阻塞" and not step.missing:
                sheet.issues.append(Issue("error", "step_record_missing", sheet.name, f"{where} 阻塞但没有「缺少：」（缺什么才能继续）", row.line))
            for raw in [p.strip() for p in step.evidence.replace("，", ",").replace("、", ",").split(",") if p.strip()]:
                if not (sheet.dir / raw).is_file():
                    sheet.issues.append(Issue("warn", "step_record_evidence", sheet.name, f"{where} 证据不存在：{raw}", row.line))
        if row.result in ("阻塞", "失败") and not stuck:
            sheet.issues.append(
                Issue(
                    "error",
                    "step_record_missing_case",
                    sheet.name,
                    f"{row.id} 结果是{row.result}，但副本里没有「执行：失败/阻塞」加「卡点：」的步骤记录",
                    row.line,
                )
            )


def _case_entry(seq: int, row: CaseRow, sheet: Sheet, root: Path) -> dict[str, Any]:
    copy = row.copy
    record_text, record_images = mdparse.strip_images(row.record)
    return {
        "seq": seq,
        "id": row.id,
        "sheet": sheet.name,
        "group": row.group,
        "subgroup": row.subgroup,
        "module": copy.module if copy else "",
        "suite": copy.suite if copy else "",
        "title": copy.title if copy else row.point,
        "type": copy.type if copy else "",
        "execution": copy.execution if copy else "",
        "preconditions": copy.preconditions if copy else "",
        "test_data": copy.test_data if copy else row.data,
        "steps": [
            {
                "action": s.action,
                "expected": s.expected,
                "status": s.status,
                "actual": s.actual,
                "blocker": s.blocker,
                "missing": s.missing,
                "evidence": s.evidence,
            }
            for s in (copy.steps if copy else [])
        ],
        "result": row.result,
        "record": record_text,
        "record_images": record_images,
        "copy": _rel(copy.path, root) if copy else "",
    }


def _defect_level(severity: str) -> str:
    return LEVELS.get(severity, UNGRADED)


def build(sheet_dirs: list[Path], *, root: Path) -> dict[str, Any]:
    sheets = [parse_sheet(Path(d)) for d in sheet_dirs]
    multi = len(sheets) > 1

    merged: "OrderedDict[str, tuple[CaseRow, Sheet]]" = OrderedDict()
    for sheet in sheets:
        for row in sheet.cases:
            merged[row.id] = (row, sheet)
    order: list[str] = []
    for sheet in sheets:
        for row in sheet.cases:
            if row.id not in order:
                order.append(row.id)
    known_ids = set(merged)

    sheet_out = []
    for sheet in sheets:
        resolve_defect_cases(sheet, known_ids)
        _check_step_records(sheet)
        per_sheet = _count([row.result for row in sheet.cases])
        _check_declared(sheet, per_sheet)
        sheet_out.append(
            {
                "dir": _rel(sheet.dir, root),
                "name": sheet.name,
                "title": sheet.title,
                "basis": sheet.basis,
                "intro": sheet.intro,
                "info": sheet.info,
                "remember": sheet.remember,
                "declared": {"total": sheet.declared_total, **sheet.declared_counts},
                "rows": per_sheet,
                "defect_columns": sheet.defect_columns,
            }
        )

    final_results = {case_id: merged[case_id][0].result for case_id in order}
    rows = _count(list(final_results.values()))
    final = _fold(rows)

    defect_items = []
    for sheet in sheets:
        for defect in sheet.defects:
            text, images = mdparse.strip_images(defect.phenomenon)
            defect_items.append(
                {
                    "key": f"{sheet.name}/{defect.id}" if multi else defect.id,
                    "sheet": sheet.name,
                    "id": defect.id,
                    "cases": defect.case_ids,
                    "phenomenon": text,
                    "images": images,
                    "severity": defect.severity,
                    "level": _defect_level(defect.severity),
                    "type": defect.type if defect.type in DEFECT_TYPES else UNTYPED,
                    "status": defect.status,
                    "blocking": defect.blocking,
                    "residual": defect.status != "关闭",
                }
            )

    referenced = {case_id for item in defect_items for case_id in item["cases"]}
    first_executed = [cid for cid in order if final_results[cid] in EXECUTED_RESULTS or cid in referenced]
    first_failed = [cid for cid in first_executed if final_results[cid] == "失败" or cid in referenced]
    first_round = {
        "designed": len(order),
        "executed": len(first_executed),
        "passed": len(first_executed) - len(first_failed),
        "failed": len(first_failed),
        "not_run": len(order) - len(first_executed),
        "failed_ids": first_failed,
    }

    fixed_ids: list[str] = []
    for cid in order:
        statuses = [item["status"] for item in defect_items if cid in item["cases"]]
        if statuses and all(status in ("已解决", "关闭") for status in statuses):
            fixed_ids.append(cid)
    regressed = [
        cid
        for cid in fixed_ids
        if all(item["status"] == "关闭" for item in defect_items if cid in item["cases"])
        and final_results[cid] in EXECUTED_RESULTS
    ]
    regression = {
        "reused": len(fixed_ids),
        "modified": 0,
        "added": 0,
        "executed": len(regressed),
        "passed": sum(1 for cid in regressed if final_results[cid] == "通过"),
        "failed": sum(1 for cid in regressed if final_results[cid] != "通过"),
        "not_run": len(fixed_ids) - len(regressed),
        "case_ids": fixed_ids,
    }

    level_names = [LEVELS[s] for s in SEVERITIES]
    if any(item["level"] == UNGRADED for item in defect_items):
        level_names.append(UNGRADED)
    type_names = list(DEFECT_TYPES) + ([UNTYPED] if any(i["type"] == UNTYPED for i in defect_items) else [])
    by_level = []
    for level in level_names:
        items = [item for item in defect_items if item["level"] == level]
        by_level.append(
            {
                "level": level,
                "types": {name: sum(1 for item in items if item["type"] == name) for name in type_names},
                "total": len(items),
                "closed": sum(1 for item in items if not item["residual"]),
                "open": sum(1 for item in items if item["residual"]),
            }
        )
    defects = {
        "total": len(defect_items),
        "closed": sum(1 for item in defect_items if not item["residual"]),
        "open": sum(1 for item in defect_items if item["residual"]),
        "statuses": {status: sum(1 for i in defect_items if i["status"] == status) for status in DEFECT_STATUSES},
        "type_names": type_names,
        "by_level": by_level,
        "items": defect_items,
    }

    cases = [_case_entry(seq, *merged[cid], root) for seq, cid in enumerate(order, start=1)]
    def blockers_of(case: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"step": i, "status": s["status"], "blocker": s["blocker"], "missing": s["missing"], "evidence": s["evidence"]}
            for i, s in enumerate(case["steps"], start=1)
            if s["status"] in ("失败", "阻塞")
        ]

    not_run_notes = [
        {"id": c["id"], "result": c["result"] or PENDING, "record": c["record"], "blockers": blockers_of(c)}
        for c in cases
        if c["result"] in ("阻塞", "忽略", "")
    ]

    modules = []
    seen_modules: set[str] = set()
    for sheet in sheets:
        for note in sheet.modules:
            if note.name in seen_modules:
                continue
            seen_modules.add(note.name)
            modules.append({"name": note.name, "title": note.title, "source": note.source, "scope": note.scope, "path": _rel(note.path, root)})

    issues = [issue.as_dict() for sheet in sheets for issue in sheet.issues]
    return {
        "sheets": sheet_out,
        "rows": rows,
        "final": final,
        "first_round": first_round,
        "regression": regression,
        "defects": defects,
        "modules": modules,
        "not_run_notes": not_run_notes,
        "cases": cases,
        "issues": issues,
        "errors": sum(1 for issue in issues if issue["level"] == "error"),
        "warnings": sum(1 for issue in issues if issue["level"] == "warn"),
    }
