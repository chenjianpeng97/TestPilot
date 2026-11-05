"""Structural checks for the defect library (docs/spec/defect-syntax.md)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from tuner_testkit.catalog.front_matter import parse_front_matter, split_front_matter

DEFECT_ID = re.compile(r"^DEF-(?P<day>\d{8})-(?P<seq>\d{3})$")
REQ_ID = re.compile(r"^REQ-[A-Za-z0-9][A-Za-z0-9_-]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEVERITIES = ("致命", "严重", "一般", "轻微")
TYPES = ("需求", "设计", "编码", "文档", "其它")
STATUSES = ("激活", "已解决", "关闭")
SECTIONS = ("现象", "环境", "前置条件", "复现步骤", "预期结果", "实际结果", "证据", "历史")
REQUIRED_SECTIONS = ("现象", "复现步骤", "预期结果", "实际结果", "历史")
HISTORY_HEADER = ("日期", "轮次", "状态", "说明")
PLACEHOLDER = "（待填）"
ALLOWED_OTHER_FILES = {"CHANGELOG.md", "README.md", ".gitkeep"}
SECTION_HEADING = re.compile(r"^## (.+?)\s*$")
H1 = re.compile(r"^# (.+?)\s*$", re.M)
STEP = re.compile(r"^\d+\. \S")


def defect_files(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("DEF-*.md") if p.is_file())


def parse_sections(body: str) -> list[tuple[str, str]]:
    """``[(heading, text), ...]`` for every ``## `` section, in order."""
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        match = SECTION_HEADING.match(line)
        if match:
            sections.append((match.group(1), []))
        elif sections:
            sections[-1][1].append(line)
    return [(name, "\n".join(lines).strip()) for name, lines in sections]


def history_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def validate_dir(root: Path) -> list[str]:
    """Human-readable errors for ``knowledge/defects``. Empty list means the library matches the spec."""
    root = root.resolve()
    if not root.is_dir():
        return [f"{root}: knowledge/defects directory is missing"]
    workspace = root.parent.parent
    errors: list[str] = []
    for path in sorted(root.iterdir()):
        if path.is_dir():
            errors.append(f"{_rel(path, workspace)}: no sub-directories in knowledge/defects")
        elif path.name not in ALLOWED_OTHER_FILES and not DEFECT_ID.match(path.stem):
            errors.append(f"{_rel(path, workspace)}: only DEF-<yyyymmdd>-<nnn>.md, CHANGELOG.md and README.md belong here")
    found_in_owner: dict[str, str] = {}
    for path in defect_files(root):
        file_errors, meta = check_defect(path, workspace)
        errors.extend(file_errors)
        anchor = str(meta.get("found_in") or "")
        if anchor and anchor != "/":
            if anchor in found_in_owner:
                errors.append(f"{_rel(path, workspace)}: found_in {anchor} already recorded by {found_in_owner[anchor]}")
            else:
                found_in_owner[anchor] = path.stem
    return errors


def check_defect(path: Path, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    rel = _rel(path, workspace)
    text = path.read_text(encoding="utf-8")
    meta = parse_front_matter(text)
    errors: list[str] = []
    if meta.get("kind") != "defect":
        errors.append(f"{rel}: front-matter kind must be defect")
    defect_id = str(meta.get("id") or "")
    if defect_id != path.stem:
        errors.append(f"{rel}: front-matter id must be {path.stem}")
    match = DEFECT_ID.match(path.stem)
    if not match:
        errors.append(f"{rel}: file name must look like DEF-20261104-001")
    elif not _valid_day(match.group("day")):
        errors.append(f"{rel}: {path.stem} has an impossible date")
    title = str(meta.get("title") or "").strip()
    if not title:
        errors.append(f"{rel}: title is required")
    for key, allowed in (("severity", SEVERITIES), ("type", TYPES), ("status", STATUSES)):
        if meta.get(key) not in allowed:
            errors.append(f"{rel}: {key} must be one of {' / '.join(allowed)}")
    if not isinstance(meta.get("blocking"), bool):
        errors.append(f"{rel}: blocking must be true or false")
    found = str(meta.get("found") or "")
    if not DATE.match(found):
        errors.append(f"{rel}: found must be a YYYY-MM-DD date")
    if not str(meta.get("version") or "").strip():
        errors.append(f"{rel}: version is required")
    errors.extend(_check_links(meta, rel, workspace))

    _, body = split_front_matter(text)
    if H1.findall(body) != [f"{defect_id} {title}".strip()]:
        errors.append(f"{rel}: H1 must be exactly {defect_id} {title}")
    errors.extend(_check_sections(parse_sections(body), rel, str(meta.get("status") or "")))
    if PLACEHOLDER in body:
        errors.append(f"{rel}: replace every {PLACEHOLDER} before saving")
    return errors, meta


def _check_links(meta: dict[str, Any], rel: str, workspace: Path) -> list[str]:
    errors: list[str] = []
    found_in = str(meta.get("found_in") or "")
    if not found_in:
        errors.append(f"{rel}: found_in is required (testsheet path#D<n>, or / when not found in a testsheet)")
    elif found_in != "/":
        target, _, anchor = found_in.partition("#")
        if not target.startswith("assets/testsheet/"):
            errors.append(f"{rel}: found_in must point into assets/testsheet/ or be /")
        elif not (workspace / target).is_file():
            errors.append(f"{rel}: found_in {target} does not exist")
        if anchor and not re.fullmatch(r"D\d+", anchor):
            errors.append(f"{rel}: found_in anchor must be the testsheet defect number, e.g. #D1")
    testcase = str(meta.get("testcase") or "")
    if not testcase:
        errors.append(f"{rel}: testcase is required (case ID, or / when no case applies)")
    elif testcase != "/":
        cases = workspace / "assets" / "testcases"
        if cases.is_dir() and not any(cases.rglob(f"{testcase}.md")):
            errors.append(f"{rel}: testcase {testcase} not found in assets/testcases/")
    reqs = meta.get("requirements")
    if reqs is not None:
        if not isinstance(reqs, list):
            errors.append(f"{rel}: requirements must be a list of REQ-… ids")
        else:
            req_dir = workspace / "knowledge" / "requirements"
            for req in reqs:
                if not isinstance(req, str) or not REQ_ID.match(req):
                    errors.append(f"{rel}: requirement id {req!r} must look like REQ-<slug>")
                elif req_dir.is_dir() and not (req_dir / f"{req}.md").is_file():
                    errors.append(f"{rel}: requirement {req} not found in knowledge/requirements/")
    return errors


def _check_sections(sections: list[tuple[str, str]], rel: str, status: str) -> list[str]:
    errors: list[str] = []
    names = [name for name, _ in sections]
    unknown = [name for name in names if name not in SECTIONS]
    if unknown:
        errors.append(f"{rel}: unknown sections {unknown}; allowed: {' / '.join(SECTIONS)}")
    known = [name for name in names if name in SECTIONS]
    if known != sorted(known, key=SECTIONS.index) or len(set(known)) != len(known):
        errors.append(f"{rel}: sections must appear once each, in order {' / '.join(SECTIONS)}")
    content = dict(sections)
    for name in REQUIRED_SECTIONS:
        if name not in content:
            errors.append(f"{rel}: section ## {name} is required")
        elif not _has_text(content[name]):
            errors.append(f"{rel}: section ## {name} is empty")
    steps = content.get("复现步骤", "")
    if "复现步骤" in content and not any(STEP.match(line.strip()) for line in steps.splitlines()):
        errors.append(f"{rel}: ## 复现步骤 needs numbered steps (1. …)")
    if "历史" in content:
        rows = history_rows(content["历史"])
        if not rows or tuple(rows[0]) != HISTORY_HEADER:
            errors.append(f"{rel}: ## 历史 must be a table with header | 日期 | 轮次 | 状态 | 说明 |")
        else:
            data = [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
            if not data:
                errors.append(f"{rel}: ## 历史 needs at least one row")
            else:
                for row in data:
                    if len(row) != 4 or not DATE.match(row[0]) or row[2] not in STATUSES:
                        errors.append(f"{rel}: ## 历史 row {row} must be | YYYY-MM-DD | 轮次 | 激活/已解决/关闭 | 说明 |")
                        break
                else:
                    if data[-1][2] != status:
                        errors.append(f"{rel}: last ## 历史 row says {data[-1][2]}, front-matter status is {status}")
    return errors


def _has_text(text: str) -> bool:
    stripped = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    return bool(stripped)


def _valid_day(day: str) -> bool:
    try:
        date(int(day[:4]), int(day[4:6]), int(day[6:]))
    except ValueError:
        return False
    return True


def _rel(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
