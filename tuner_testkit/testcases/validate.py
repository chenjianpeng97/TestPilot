"""Structural checks for the functional testcase tree."""

from __future__ import annotations

import re
from pathlib import Path

from tuner_testkit.catalog.front_matter import parse_front_matter, split_front_matter

ID_PREFIX = re.compile(r"^[A-Z][A-Za-z]*(?:-[A-Z][A-Za-z]*)*$")
CASE_ID = re.compile(
    r"^(?P<prefix>[A-Z][A-Za-z]*(?:-[A-Z][A-Za-z]*)*)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+){1,4})$"
)
ACTION_BULLET = re.compile(r"^- 操作：\S")
EXPECT_BULLET = re.compile(r"^- 预期：\S")
STEP_HEADING = re.compile(r"^### (\d+)$")
SECTION_HEADING = re.compile(r"^## (.+)$")
H1 = re.compile(r"^# (.+)$", re.M)
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SECTION_ORDER = ("摘要", "前置条件", "测试数据", "步骤", "备注")
TYPES = {"正向", "反向"}
STATUSES = {"就绪", "废弃"}
EXECUTIONS = {"手工", "自动"}
IMPORTANCES = {"低", "中", "高"}
STAGES = {"冒烟", "系统测试"}
REQ_ID = re.compile(r"^REQ-[A-Za-z0-9][A-Za-z0-9_-]*$")
ROOT_FILES = {"README.md", "CHANGELOG.md"}


def validate_tree(root: Path) -> list[str]:
    """Return human-readable errors. Empty list means the tree matches the spec."""
    root = root.resolve()
    errors: list[str] = []
    if not root.is_dir():
        return [f"{root}: assets/testcases directory is missing"]
    errors.extend(_check_trace_links(root))

    index = root / "README.md"
    if not index.is_file():
        errors.append(f"{_rel(index)}: module index README.md is required")
    else:
        errors.extend(_check_kind(index, "testcase-index"))

    seen: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    modules = sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    for module in modules:
        if module.name not in index_text:
            errors.append(f"{_rel(index)}: module table must mention {module.name}")
        errors.extend(_check_module(module, seen, prefixes))
    for path in root.iterdir():
        if path.is_file() and path.name not in ROOT_FILES:
            errors.append(f"{_rel(path)}: only README.md and CHANGELOG.md belong at the testcases root")
    return errors


def _check_trace_links(root: Path) -> list[str]:
    """Optional ``requirements`` / ``data`` front-matter fields must point at real things.

    ``root`` is ``<workspace>/assets/testcases``; requirements live in
    ``<workspace>/knowledge/requirements/<REQ-ID>.md``, data files under ``<workspace>/data/``.
    """
    workspace = root.parent.parent
    req_dir = workspace / "knowledge" / "requirements"
    errors: list[str] = []
    for path in sorted(root.rglob("*.md")):
        if path.name in ROOT_FILES:
            continue
        meta = parse_front_matter(path.read_text(encoding="utf-8"))
        if meta.get("kind") != "testcase":
            continue
        rel = _rel(path)
        reqs = meta.get("requirements")
        if reqs is not None:
            if not isinstance(reqs, list) or not all(isinstance(r, str) for r in reqs):
                errors.append(f"{rel}: requirements must be a list of REQ-… ids")
            else:
                for req in reqs:
                    if not REQ_ID.match(req):
                        errors.append(f"{rel}: requirement id {req!r} must look like REQ-<slug>")
                    elif req_dir.is_dir() and not (req_dir / f"{req}.md").is_file():
                        errors.append(f"{rel}: requirement {req} not found in knowledge/requirements/")
        data = meta.get("data")
        if data is not None:
            if not isinstance(data, list) or not all(isinstance(d, str) for d in data):
                errors.append(f"{rel}: data must be a list of data/… paths or account:<id>")
                continue
            for ref in data:
                if ref.startswith("account:"):
                    if not ref.split(":", 1)[1].strip():
                        errors.append(f"{rel}: data entry {ref!r} needs an account id")
                elif not ref.startswith("data/"):
                    errors.append(f"{rel}: data entry {ref!r} must start with data/ or account:")
                elif ".local." in ref:
                    errors.append(f"{rel}: data entry {ref!r} points at a local secret file")
                elif not (workspace / ref).exists():
                    errors.append(f"{rel}: data file {ref} does not exist")
    return errors


def _check_module(module: Path, seen: dict[str, str], prefixes: dict[str, str]) -> list[str]:
    errors: list[str] = []
    readme = module / "README.md"
    if not readme.is_file():
        errors.append(f"{_rel(readme)}: module README.md is required")
    else:
        errors.extend(_check_kind(readme, "testcase-module"))
        meta = parse_front_matter(readme.read_text(encoding="utf-8"))
        if meta.get("title") != module.name:
            errors.append(f"{_rel(readme)}: front-matter title must be {module.name}")

    suite_names: list[str] = []
    for path in sorted(module.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_dir():
            suite_names.append(path.name)
            errors.extend(_check_suite(path, module.name, seen, prefixes))
            continue
        if path.name == "README.md":
            continue
        errors.append(f"{_rel(path)}: a module holds README.md and suite directories only")

    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        for name in suite_names:
            if name not in text:
                errors.append(f"{_rel(readme)}: suite list must mention {name}")
    return errors


def _check_suite(
    suite: Path, module_name: str, seen: dict[str, str], prefixes: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    readme = suite / "README.md"
    rel = _rel(readme)
    prefix = ""
    if not readme.is_file():
        errors.append(f"{rel}: suite README.md is required")
    else:
        text = readme.read_text(encoding="utf-8")
        meta = parse_front_matter(text)
        errors.extend(_check_kind(readme, "testcase-suite"))
        if meta.get("title") != suite.name:
            errors.append(f"{rel}: front-matter title must be {suite.name}")
        if meta.get("module") != module_name:
            errors.append(f"{rel}: front-matter module must be {module_name}")
        prefix = str(meta.get("id_prefix") or "")
        if not ID_PREFIX.match(prefix):
            errors.append(f"{rel}: front-matter id_prefix must look like User-Login")
        elif prefix in prefixes:
            errors.append(f"{rel}: id_prefix {prefix} already used by {prefixes[prefix]}")
        else:
            prefixes[prefix] = rel
        _, body = split_front_matter(text)
        h1 = H1.findall(body)
        if h1 != [suite.name]:
            errors.append(f"{rel}: H1 must be exactly {suite.name}")

    case_files = [
        path
        for path in sorted(suite.iterdir())
        if path.is_file() and path.name != "README.md" and not path.name.startswith(".")
    ]
    for path in suite.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            errors.append(f"{_rel(path)}: do not nest directories under a suite")

    cases: dict[str, dict] = {}
    for path in case_files:
        if path.suffix.lower() != ".md":
            errors.append(f"{_rel(path)}: suite files must be README.md or <Case-ID>.md")
            continue
        case_meta = _check_case(path, module_name, suite.name, prefix, seen)
        errors.extend(case_meta[0])
        if case_meta[1]:
            cases[path.stem] = case_meta[1]

    if readme.is_file():
        errors.extend(_check_case_table(readme, cases))
    return errors


def _check_case(
    path: Path,
    module_name: str,
    suite_name: str,
    suite_prefix: str,
    seen: dict[str, str],
) -> tuple[list[str], dict | None]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    meta = parse_front_matter(text)
    rel = _rel(path)
    if meta.get("kind") != "testcase":
        errors.append(f"{rel}: front-matter kind must be testcase")
    case_id = str(meta.get("id") or "")
    if case_id != path.stem:
        errors.append(f"{rel}: front-matter id must be {path.stem}")
    matched = CASE_ID.match(case_id)
    if not matched:
        errors.append(
            f"{rel}: id must look like User-Login-valid-credentials (prefix plus 2-5 word slug)"
        )
    elif suite_prefix and matched.group("prefix") != suite_prefix:
        errors.append(f"{rel}: {case_id} must use id_prefix {suite_prefix}")
    if suite_prefix and str(meta.get("id_prefix") or "") != suite_prefix:
        errors.append(f"{rel}: front-matter id_prefix must be {suite_prefix}")
    if meta.get("suite") != suite_name:
        errors.append(f"{rel}: front-matter suite must be {suite_name}")
    if meta.get("module") != module_name:
        errors.append(f"{rel}: front-matter module must be {module_name}")
    title = str(meta.get("title") or "")
    if not title or title.endswith("（废弃）"):
        errors.append(f"{rel}: front-matter title must be set and must not end with （废弃）")
    if meta.get("type") not in TYPES:
        errors.append(f"{rel}: type must be 正向 or 反向")
    if meta.get("status") not in STATUSES:
        errors.append(f"{rel}: status must be 就绪 or 废弃")
    if "execution" in meta and meta.get("execution") not in EXECUTIONS:
        errors.append(f"{rel}: execution must be 手工 or 自动")
    if "importance" in meta and meta.get("importance") not in IMPORTANCES:
        errors.append(f"{rel}: importance must be 低, 中, or 高")
    if "stages" in meta:
        stages = meta.get("stages")
        if not isinstance(stages, list) or not stages:
            errors.append(f"{rel}: stages must be a non-empty list")
        else:
            seen_stages: set[str] = set()
            for item in stages:
                if not isinstance(item, str) or item not in STAGES:
                    errors.append(
                        f"{rel}: stages items must be one of {', '.join(sorted(STAGES))}"
                    )
                    break
                if item in seen_stages:
                    errors.append(f"{rel}: stages must not repeat {item}")
                    break
                seen_stages.add(item)

    if case_id:
        previous = seen.get(case_id)
        if previous:
            errors.append(f"{rel}: duplicate {case_id} (also in {previous})")
        else:
            seen[case_id] = rel

    _, body = split_front_matter(text)
    h1 = H1.findall(body)
    expected_h1 = f"{case_id} {title}".strip()
    if h1 != [expected_h1]:
        errors.append(f"{rel}: H1 must be exactly {expected_h1}")
    errors.extend(_check_sections(body, rel, case_id))
    return errors, meta


def _check_sections(body: str, rel: str, case_id: str) -> list[str]:
    errors: list[str] = []
    lines = body.splitlines()
    sections: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        matched = SECTION_HEADING.match(line)
        if matched:
            sections.append((matched.group(1).strip(), index))
    names = [name for name, _ in sections]
    unknown = [name for name in names if name not in SECTION_ORDER]
    if unknown:
        errors.append(f"{rel}: unknown section {unknown[0]}")
    positions = [SECTION_ORDER.index(name) for name in names if name in SECTION_ORDER]
    if positions != sorted(positions) or len(positions) != len(set(positions)):
        errors.append(f"{rel}: sections must follow 摘要, 前置条件, 测试数据, 步骤, 备注")
    if "步骤" not in names:
        errors.append(f"{rel}: {case_id or path_label(rel)} needs '## 步骤'")
        return errors

    for offset, (name, start) in enumerate(sections):
        end = sections[offset + 1][1] if offset + 1 < len(sections) else len(lines)
        block = lines[start + 1 : end]
        if name != "步骤" and not any(line.strip() for line in block):
            errors.append(f"{rel}: omit empty section {name}")
        if name == "步骤":
            errors.extend(_check_steps(block, rel, case_id))
    return errors


def _check_steps(block: list[str], rel: str, case_id: str) -> list[str]:
    errors: list[str] = []
    starts = [index for index, line in enumerate(block) if line.startswith("### ")]
    if not starts:
        errors.append(f"{rel}: {case_id} needs '### 1'")
        return errors
    numbers: list[int] = []
    for offset, start in enumerate(starts):
        heading = block[start]
        matched = STEP_HEADING.match(heading)
        if not matched:
            errors.append(f"{rel}: step heading must be '### N' ({heading})")
            continue
        numbers.append(int(matched.group(1)))
        end = starts[offset + 1] if offset + 1 < len(starts) else len(block)
        step = block[start + 1 : end]
        if not any(ACTION_BULLET.match(line) for line in step):
            errors.append(f"{rel}: {case_id} step {matched.group(1)} needs '- 操作：'")
        if not any(EXPECT_BULLET.match(line) for line in step):
            errors.append(f"{rel}: {case_id} step {matched.group(1)} needs '- 预期：'")
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"{rel}: {case_id} steps must be numbered 1..N without gaps")
    return errors


def _check_case_table(readme: Path, cases: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    rel = _rel(readme)
    _, body = split_front_matter(readme.read_text(encoding="utf-8"))
    listed: dict[str, tuple[str, str, str]] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"ID", "---"} or set(cells[0]) <= {"-"}:
            continue
        linked = LINK.search(cells[0])
        if not linked:
            errors.append(f"{rel}: case table ID must link to a case file ({cells[0]})")
            continue
        case_id, href = linked.group(1), linked.group(2)
        if href != f"{case_id}.md":
            errors.append(f"{rel}: {case_id} must link to {case_id}.md")
        if case_id in listed:
            errors.append(f"{rel}: duplicate table row {case_id}")
        listed[case_id] = (cells[1], cells[2], cells[3])

    for case_id, meta in cases.items():
        row = listed.get(case_id)
        if row is None:
            errors.append(f"{rel}: case table must list {case_id}")
            continue
        title, case_type, status = row
        if title != str(meta.get("title") or ""):
            errors.append(f"{rel}: {case_id} table title must be {meta.get('title')}")
        if case_type != meta.get("type"):
            errors.append(f"{rel}: {case_id} table type must be {meta.get('type')}")
        if status != meta.get("status"):
            errors.append(f"{rel}: {case_id} table status must be {meta.get('status')}")
    for case_id in listed:
        if case_id not in cases:
            errors.append(f"{rel}: case table lists {case_id} but the file is missing")
    return errors


def _check_kind(path: Path, kind: str) -> list[str]:
    meta = parse_front_matter(path.read_text(encoding="utf-8"))
    if meta.get("kind") != kind:
        return [f"{_rel(path)}: front-matter kind must be {kind}"]
    return []


def path_label(rel: str) -> str:
    return Path(rel).stem or rel


def _rel(path: Path) -> str:
    return path.as_posix()
