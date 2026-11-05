"""Parse assets/testsheet/<round>/testsheet.md plus the testcase copies it links."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from . import mdparse

RESULTS = ("通过", "失败", "部分通过", "未执行", "阻塞")
EXECUTED_RESULTS = ("通过", "失败", "部分通过")
SEVERITIES = ("致命", "严重", "一般", "轻微")
DEFECT_TYPES = ("需求", "设计", "编码", "文档", "其它")
DEFECT_STATUSES = ("激活", "已解决", "关闭")
DEFECT_COLUMNS = ("编号", "用例", "现象", "严重程度", "类型", "状态", "是否阻塞后续")
INFO_KEYS = ("测试人", "日期", "版本", "环境", "证据")

_TOTAL_RE = re.compile(r"共\s*(\d+)\s*条")
_STEP_FIELD_RE = re.compile(r"^-\s*(操作|预期)\s*[：:]\s*(.*)$")


@dataclass
class Issue:
    level: str
    code: str
    sheet: str
    detail: str
    line: int | None = None

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "sheet": self.sheet, "detail": self.detail, "line": self.line}


@dataclass
class Step:
    action: str
    expected: str


@dataclass
class CaseCopy:
    path: Path
    id: str
    title: str
    module: str
    suite: str
    type: str
    execution: str
    summary: str
    preconditions: str
    test_data: str
    steps: list[Step]


@dataclass
class CaseRow:
    id: str
    link: str
    point: str
    data: str
    expected: str
    result: str
    record: str
    group: str
    subgroup: str
    line: int
    copy: CaseCopy | None = None


@dataclass
class DefectRow:
    id: str
    case_cell: str
    case_ids: list[str]
    phenomenon: str
    severity: str
    type: str
    status: str
    blocking: str
    line: int


@dataclass
class ModuleNote:
    name: str
    path: Path
    title: str
    source: str
    scope: str


@dataclass
class Sheet:
    dir: Path
    title: str
    intro: list[str]
    basis: str
    info: dict[str, str]
    declared_total: int | None
    declared_counts: dict[str, str]
    remember: list[str]
    cases: list[CaseRow]
    defects: list[DefectRow]
    defect_columns: list[str]
    modules: list[ModuleNote]
    issues: list[Issue] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.dir.name


def parse_case_copy(path: Path) -> CaseCopy:
    meta, body = mdparse.split_front_matter(path.read_text(encoding="utf-8"))
    parts = {sec.title: sec for sec in mdparse.sections(body, 2)}
    steps: list[Step] = []
    if "步骤" in parts:
        for step_sec in mdparse.sections(parts["步骤"].text, 3):
            steps.append(_parse_step(step_sec.text))
    return CaseCopy(
        path=path,
        id=meta.get("id", path.stem),
        title=meta.get("title", ""),
        module=meta.get("module", ""),
        suite=meta.get("suite", ""),
        type=meta.get("type", ""),
        execution=meta.get("execution", ""),
        summary=parts["摘要"].text if "摘要" in parts else "",
        preconditions=parts["前置条件"].text if "前置条件" in parts else "",
        test_data=parts["测试数据"].text if "测试数据" in parts else "",
        steps=steps,
    )


def _parse_step(text: str) -> Step:
    fields: dict[str, list[str]] = {"操作": [], "预期": []}
    current: str | None = None
    for line in text.split("\n"):
        match = _STEP_FIELD_RE.match(line.strip())
        if match:
            current = match.group(1)
            fields[current].append(match.group(2).strip())
        elif current and line.strip():
            fields[current].append(line.strip())
    return Step(action=" ".join(fields["操作"]).strip(), expected=" ".join(fields["预期"]).strip())


def _module_notes(sheet_dir: Path) -> list[ModuleNote]:
    notes: list[ModuleNote] = []
    root = sheet_dir / "testcase"
    if not root.is_dir():
        return notes
    for readme in sorted(root.glob("*/README.md")):
        meta, body = mdparse.split_front_matter(readme.read_text(encoding="utf-8"))
        scope = next((sec.text for sec in mdparse.sections(body, 2) if sec.title == "范围"), "")
        notes.append(
            ModuleNote(
                name=readme.parent.name,
                path=readme,
                title=meta.get("title", readme.parent.name),
                source=meta.get("source", ""),
                scope=scope,
            )
        )
    return notes


def _case_link(cell: str) -> tuple[str, str] | None:
    found = mdparse.links(cell)
    if not found:
        return None
    label, target = found[0]
    return label.strip().strip("`"), unquote(target.strip())


def parse_sheet(sheet_dir: Path) -> Sheet:
    sheet_dir = Path(sheet_dir)
    path = sheet_dir / "testsheet.md"
    _, body = mdparse.split_front_matter(path.read_text(encoding="utf-8"))
    name = sheet_dir.name
    issues: list[Issue] = []

    title = ""
    intro_lines: list[str] = []
    for line in body.split("\n"):
        head = mdparse.heading(line)
        if head and head[0] == 1 and not title:
            title = head[1]
            continue
        if head and head[0] >= 2:
            break
        if title:
            intro_lines.append(line)
    intro = mdparse.paragraphs("\n".join(intro_lines))
    basis = next((p for p in intro if p.startswith("依据")), "")
    total_match = next((m for m in (_TOTAL_RE.search(p) for p in intro) if m), None)
    declared_total = int(total_match.group(1)) if total_match else None

    remember: list[str] = []
    for sec in mdparse.sections(body, 2):
        if sec.title == "测的时候先记住":
            remember = mdparse.bullets(sec.text)

    info: dict[str, str] = {}
    declared_counts: dict[str, str] = {}
    cases: list[CaseRow] = []
    defects: list[DefectRow] = []
    defect_columns: list[str] = []

    for table in mdparse.tables(body):
        header = table.header
        if header[:2] == ["项", "填写"]:
            for row in table.rows:
                if not row or not row[0]:
                    continue
                value = row[1] if len(row) > 1 else ""
                if row[0] in RESULTS:
                    declared_counts[row[0]] = value
                else:
                    info[row[0]] = value
            continue
        if header and header[0] == "编号" and "现象" in header:
            defect_columns = header
            defects.extend(_parse_defects(table, name, issues))
            continue
        if "用例" in header and "结果" in header:
            cases.extend(_parse_case_rows(table, sheet_dir, name, issues))

    for key in ("测试人", "日期", "环境"):
        if not info.get(key, "").strip():
            issues.append(Issue("warn", "info_missing", name, f"本轮信息「{key}」为空"))
    if "版本" not in info:
        issues.append(Issue("warn", "info_missing", name, "本轮信息没有「版本」行"))
    elif not info["版本"].strip():
        issues.append(Issue("warn", "info_missing", name, "本轮信息「版本」为空"))

    return Sheet(
        dir=sheet_dir,
        title=title,
        intro=intro,
        basis=basis,
        info=info,
        declared_total=declared_total,
        declared_counts=declared_counts,
        remember=remember,
        cases=cases,
        defects=defects,
        defect_columns=defect_columns,
        modules=_module_notes(sheet_dir),
        issues=issues,
    )


def _parse_case_rows(table: mdparse.Table, sheet_dir: Path, name: str, issues: list[Issue]) -> list[CaseRow]:
    out: list[CaseRow] = []
    group = table.headings.get(2, "")
    subgroup = table.headings.get(3, "")
    for record, line in zip(table.records(), table.row_lines, strict=True):
        cell = record.get("用例", "")
        link = _case_link(cell)
        if link is None:
            issues.append(Issue("error", "case_link_missing", name, f"用例列不是指向副本的链接：{cell}", line))
            continue
        case_id, target = link
        result = record.get("结果", "").strip()
        if result not in RESULTS:
            issues.append(Issue("error", "result_invalid", name, f"{case_id} 结果「{result}」不在 {'/'.join(RESULTS)}", line))
        copy: CaseCopy | None = None
        copy_path = (sheet_dir / target).resolve()
        if target.startswith(("http://", "https://")) or not copy_path.is_file():
            issues.append(Issue("error", "case_copy_missing", name, f"{case_id} 的副本不存在：{target}", line))
        else:
            copy = parse_case_copy(copy_path)
            if copy.id != case_id:
                issues.append(Issue("warn", "case_id_mismatch", name, f"表内 {case_id}，副本 id 为 {copy.id}", line))
        out.append(
            CaseRow(
                id=case_id,
                link=target,
                point=record.get("测试点", ""),
                data=record.get("数据", ""),
                expected=record.get("预期要点", ""),
                result=result,
                record=record.get("实测记录", ""),
                group=group,
                subgroup=subgroup,
                line=line,
                copy=copy,
            )
        )
    return out


def _parse_defects(table: mdparse.Table, name: str, issues: list[Issue]) -> list[DefectRow]:
    missing = [col for col in DEFECT_COLUMNS if col not in table.header]
    if missing:
        issues.append(Issue("error", "defect_columns_missing", name, "缺陷表缺列：" + "、".join(missing), table.line))
    out: list[DefectRow] = []
    seen: set[str] = set()
    for record, line in zip(table.records(), table.row_lines, strict=True):
        defect_id = record.get("编号", "").strip()
        others = [v for k, v in record.items() if k != "编号" and v.strip()]
        if defect_id in ("", "无") and not others:
            continue
        if defect_id in ("", "无"):
            issues.append(Issue("error", "defect_id_invalid", name, f"缺陷编号为「{defect_id or '空'}」，应为 D1、D2……", line))
        elif defect_id in seen:
            issues.append(Issue("error", "defect_id_invalid", name, f"缺陷编号 {defect_id} 重复", line))
        seen.add(defect_id)
        severity = mdparse.strip_images(record.get("严重程度", ""))[0]
        dtype = mdparse.strip_images(record.get("类型", ""))[0]
        status = mdparse.strip_images(record.get("状态", ""))[0]
        label = defect_id or f"第 {line} 行"
        if "严重程度" not in missing and severity not in SEVERITIES:
            issues.append(Issue("error", "defect_severity_invalid", name, f"{label} 严重程度「{severity}」不在 {'/'.join(SEVERITIES)}", line))
        if "类型" not in missing and dtype not in DEFECT_TYPES:
            issues.append(Issue("error", "defect_type_invalid", name, f"{label} 类型「{dtype}」不在 {'/'.join(DEFECT_TYPES)}", line))
        if "状态" not in missing and status not in DEFECT_STATUSES:
            issues.append(Issue("error", "defect_status_invalid", name, f"{label} 状态「{status}」不在 {'/'.join(DEFECT_STATUSES)}", line))
        out.append(
            DefectRow(
                id=defect_id,
                case_cell=record.get("用例", "").strip(),
                case_ids=[],
                phenomenon=record.get("现象", "").strip(),
                severity=severity,
                type=dtype,
                status=status,
                blocking=record.get("是否阻塞后续", "").strip(),
                line=line,
            )
        )
    return out


def resolve_defect_cases(sheet: Sheet, known_ids: set[str]) -> None:
    """Fill ``DefectRow.case_ids`` from the 用例 cell; report cells that name no known case."""

    for defect in sheet.defects:
        cell = defect.case_cell
        if cell in ("/", ""):
            if cell == "":
                sheet.issues.append(
                    Issue("error", "defect_case_missing", sheet.name, f"{defect.id or '缺陷'} 用例列为空，没有对应用例写 /", defect.line)
                )
            continue
        ids = [case_id for case_id in sorted(known_ids, key=len, reverse=True) if case_id in cell]
        ids = [case_id for case_id in ids if not any(case_id != other and case_id in other for other in ids)]
        if not ids:
            sheet.issues.append(Issue("error", "defect_case_unknown", sheet.name, f"{defect.id} 用例「{cell}」不在本单", defect.line))
        defect.case_ids = sorted(ids, key=cell.find)
