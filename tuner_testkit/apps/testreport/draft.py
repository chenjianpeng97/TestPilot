"""Compose the GJB438B report Markdown from testsheet stats and the report profile.

Numbers and fixed wording are filled here. Whatever needs a person (missing profile
fields, version, testers, suggestions) is left as ``<!-- TODO ... -->`` and ``render``
refuses to run until they are gone.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import mdparse
from .profile import REQUIRED_KEYS, Profile

TODO_MARK = "<!-- TODO"
FOLD = {"通过": "通过", "失败": "未通过", "部分通过": "未通过", "未执行": "未执行", "阻塞": "未执行"}
LEVELS = ("1级", "2级", "3级", "4级")
TYPE_COLUMNS = (("需求", "需求缺陷"), ("设计", "设计缺陷"), ("编码", "编码缺陷"), ("文档", "文档缺陷"), ("其它", "其它缺陷"))
DEFAULT_CRITERIA_HINT = "画像没有「通过准则」"
_DATE_RE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_SPLIT_RE = re.compile(r"[、,，/；;]+")
_REF_SPLIT_RE = re.compile(r"[、,，；;]+")
_DOC_DATE_KEYS = ("发布日期", "建立日期", "编制日期")


def todo(hint: str) -> str:
    return f"{TODO_MARK} {hint} -->"


def cell(value: Any) -> str:
    return str(value).replace("\r", "").replace("|", "\\|").replace("\n", "<br>").strip()


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return lines


def _kv(pairs: list[tuple[str, Any]]) -> list[str]:
    return _table(["项", "内容"], [[k, v] for k, v in pairs])


def _cn_date(day: date) -> str:
    return f"{day.year}年{day.month:02d}月{day.day:02d}日"


def _sheet_dates(stats: dict[str, Any]) -> list[date]:
    found: list[date] = []
    for sheet in stats["sheets"]:
        for m in _DATE_RE.finditer(sheet["info"].get("日期", "")):
            try:
                found.append(date(int(m[1]), int(m[2]), int(m[3])))
            except ValueError:
                continue
    return sorted(found)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for part in _SPLIT_RE.split(mdparse.plain(value)):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def _levels(text: str) -> set[str]:
    return {f"{d}级" for d in re.findall(r"([1-4])\s*级", text)}


def verdict(stats: dict[str, Any], profile: Profile) -> tuple[str, str]:
    """Return (verdict, reason). Only the profile's 通过准则 decides; no criteria means 待评审."""

    criteria = profile.criteria
    if not criteria:
        return "待评审", DEFAULT_CRITERIA_HINT
    open_items = [item for item in stats["defects"]["items"] if item["residual"]]
    blocked_levels = _levels(criteria.get("不允许遗留的缺陷等级", ""))
    allow_not_run = criteria.get("允许未执行用例", "").strip() in ("是", "允许")
    final = stats["final"]
    hit = sorted({item["level"] for item in open_items if item["level"] in blocked_levels})
    if hit:
        return "未通过测试", f"遗留 {'、'.join(hit)} 缺陷"
    if final["not_run"] and not allow_not_run:
        return "未通过测试", f"未执行用例 {final['not_run']} 个"
    if any(item["level"] not in LEVELS for item in open_items):
        return "待评审", "遗留缺陷未定级"
    if final["failed"] and not open_items:
        return "待评审", "有未通过用例但缺陷表没有对应的遗留缺陷"
    return "通过测试", ""


def _module_rows(stats: dict[str, Any]) -> list[tuple[str, dict[str, int]]]:
    groups: dict[str, dict[str, int]] = {}
    for case in stats["cases"]:
        name = case["module"] or case["group"] or "未分模块"
        bucket = groups.setdefault(name, {"designed": 0, "executed": 0, "passed": 0, "failed": 0, "not_run": 0})
        folded = FOLD.get(case["result"], "未执行")
        bucket["designed"] += 1
        if folded == "未执行":
            bucket["not_run"] += 1
        else:
            bucket["executed"] += 1
            bucket["passed" if folded == "通过" else "failed"] += 1
    return list(groups.items())


def _doc_date(meta: dict[str, str], body: str) -> str:
    for line in body.split("\n"):
        if not line.lstrip().startswith("|"):
            continue
        cells = mdparse.split_row(line)
        if len(cells) >= 2 and cells[0].strip() in _DOC_DATE_KEYS:
            found = _DATE_RE.search(cells[1])
            if found:
                return found.group(0)
    for key in ("date", "created"):
        found = _DATE_RE.search(meta.get(key, ""))
        if found:
            return found.group(0)
    return ""


def _doc_ref(item: str, root: Path | None) -> tuple[str, str]:
    """A basis item naming a repo Markdown file becomes (「标题（路径）」, 发布日期)."""

    path = root / item if root and item.endswith(".md") else None
    if not path or not path.is_file():
        return item, ""
    meta, body = mdparse.split_front_matter(path.read_text(encoding="utf-8"))
    title = meta.get("title", "").strip()
    if not title:
        title = next((h[1] for h in map(mdparse.heading, body.split("\n")) if h and h[0] == 1), "")
    return (f"{title}（{item}）" if title else item), _doc_date(meta, body)


def _basis_items(sheet: dict[str, Any], root: Path | None) -> tuple[list[tuple[str, str]], str]:
    basis = mdparse.plain(sheet["basis"])
    head, _, rest = basis.partition("。")
    head = head.removeprefix("依据：").removeprefix("依据:").strip()
    items = [_doc_ref(item.strip(), root) for item in _REF_SPLIT_RE.split(head) if item.strip()]
    return items, rest.strip()


def _basis_refs(stats: dict[str, Any], root: Path | None) -> list[list[str]]:
    rows = []
    for sheet in stats["sheets"]:
        dates = [m.group(0) for m in _DATE_RE.finditer(sheet["info"].get("日期", ""))]
        rows.append(["/", f"{sheet['title']}（{sheet['dir']}/testsheet.md）", "/", dates[-1] if dates else "/"])
        for item, doc_date in _basis_items(sheet, root)[0]:
            found = _DATE_RE.search(item)
            title = _DATE_RE.sub("", item).strip() if found else item
            rows.append(["/", title or item, "/", found.group(0) if found else (doc_date or "/")])
    return rows


def _basis_note(sheet: dict[str, Any], root: Path | None) -> str:
    items, rest = _basis_items(sheet, root)
    head = f"测试单的依据是{'、'.join(item for item, _ in items)}。" if items else ""
    return head + rest


def compose(
    stats: dict[str, Any],
    profile: Profile,
    *,
    slug: str,
    sut: str,
    env: str,
    task_id: str,
    profile_rel: str,
    today: date,
    root: Path | None = None,
) -> tuple[str, list[str]]:
    hints: list[str] = []

    def need(value: str, hint: str) -> str:
        if value:
            return value
        hints.append(hint)
        return todo(hint)

    def basic(key: str) -> str:
        value = profile.get(key)
        if value:
            return value
        if key in REQUIRED_KEYS:
            return need("", f"画像「基本信息」补「{key}」")
        return "/"

    system = basic("系统名称")
    company = basic("编制单位")
    title_name = profile.get("系统名称") or sut
    dates = _sheet_dates(stats)
    last_day = dates[-1] if dates else today
    period = _cn_date(dates[0]) if dates and dates[0] == dates[-1] else (f"{_cn_date(dates[0])}～{_cn_date(dates[-1])}" if dates else "")
    period = need(period, "测试单「本轮信息」补「日期」")
    testers = need("、".join(_unique([s["info"].get("测试人", "") for s in stats["sheets"]])), "测试单「本轮信息」补「测试人」")
    version = need("、".join(_unique([s["info"].get("版本", "") for s in stats["sheets"]])), "测试单「本轮信息」补「版本」")
    test_type = profile.get("测试类型") or "功能测试"

    rows = stats["rows"]
    fr = stats["first_round"]
    rg = stats["regression"]
    final = stats["final"]
    defects = stats["defects"]
    open_items = [item for item in defects["items"] if item["residual"]]
    result, reason = verdict(stats, profile)
    if result == "待评审":
        hints.append(f"结论待评审（{reason}），在画像补「通过准则」或与评审人确认后改「结论」")
        result_cell = todo(f"结论待评审：{reason}") + "待评审"
    else:
        result_cell = result

    sheets_rel = [f"{s['dir']}/testsheet.md" for s in stats["sheets"]]
    out: list[str] = [
        "---",
        "kind: testreport",
        f"id: {slug}",
        f"title: {title_name}软件测试报告",
        "format: gjb438b",
        "version: 1.0.0",
        f"sut: {sut}",
        f"env: {env}",
        f"period: {last_day.year}-{last_day.month:02d}",
        "result:",
        f"  total: {rows['total']}",
        f"  passed: {rows['通过']}",
        f"  partial: {rows['部分通过']}",
        f"  failed: {rows['失败']}",
        f"  blocked: {rows['阻塞']}",
        f"  not_run: {rows['未执行']}",
        f"testsheets: [{', '.join(sheets_rel)}]",
        f"profile: {profile_rel}",
        "evidence: []",
        "features: []",
        f"task_id: {task_id}",
        "confidence: medium",
        f"source: {sheets_rel[0] if sheets_rel else ''}",
        "---",
        "",
        f"# {title_name}软件测试报告",
        "",
        "## 封面",
        "",
        *_kv([("系统名称", system), ("编制单位", company), ("编制日期", f"{last_day.year}年{last_day.month:02d}月")]),
        "",
        "## 修订页",
        "",
        *_table(["序号", "版本号", "修改日期", "修改内容", "修改人"], [[1, "V1.0", today.isoformat(), "首次编写", testers]]),
        "",
        "## 1 范围",
        "",
        "### 1.1 标识",
        "",
        *_kv([
            ("文档适用系统", system),
            ("文档标题", f"{title_name}软件测试报告"),
            ("文档标识号", basic("文档标识号")),
            ("文档版本号", "V1.0"),
            ("缩略语", profile.get("缩略语") or "无"),
        ]),
        "",
        "### 1.2 系统概述",
        "",
    ]
    intro = profile.intro or [need("", "画像补「系统简介」")]
    for para in intro:
        out += [para, ""]
    out += [
        "#### 1.2.1 供需方情况",
        "",
        *_kv([("需方", basic("需方")), ("开发方", basic("开发方")), ("保障机构", basic("保障机构"))]),
        "",
        "#### 1.2.2 运行现场",
        "",
    ]
    for para in profile.run_site:
        out += [para, ""]
    multi = len(stats["sheets"]) > 1
    for sheet in stats["sheets"]:
        env_text = mdparse.plain(sheet["info"].get("环境", ""))
        if env_text:
            prefix = f"「{sheet['title']}」测试环境：" if multi else "本轮测试环境："
            out += [prefix + env_text.rstrip("。") + "。", ""]
    if not profile.run_site and not any(s["info"].get("环境") for s in stats["sheets"]):
        out += [need("", "画像补「运行现场」"), ""]
    out += [
        "### 1.3 文档概述",
        "",
        f"本文档适用于{system}软件测试全过程，对软件测试过程和测试相关结果进行归纳总结。",
        "",
        "## 2 引用文档",
        "",
    ]
    refs = [[r["文档编号"] or "/", r["文档标题"], r["编写单位"] or "/", r["发布日期"] or "/"] for r in profile.references]
    refs += _basis_refs(stats, root)
    out += _table(["序号", "文档编号", "文档标题", "编写单位", "发布日期"], [[i, *r] for i, r in enumerate(refs, start=1)])

    exec_detail = f"执行的{final['executed']}个用例中通过{final['passed']}个，未通过{final['failed']}个；未执行{final['not_run']}个。"
    if not defects["total"]:
        residual_intro = "测试中未发现残留问题。"
    elif not open_items:
        residual_intro = f"测试发现的{defects['total']}个缺陷均已归零，没有残留问题。"
    else:
        residual_intro = "但在测试中还发现了以下这些残留的问题："
    out += [
        "",
        "## 3 测试结果概述",
        "",
        "### 3.1 对被测试软件的总体评估",
        "",
        *_kv([
            ("软件版本", version),
            ("结论", result_cell),
            ("结论说明", "测试结果表明该系统：" + exec_detail),
            ("残留问题说明", residual_intro),
        ]),
        "",
        "#### 残留问题",
        "",
    ]
    residual_rows = [
        ["、".join(item["cases"]) or "/", f"{item['key']}：{item['phenomenon']}（{item['level']}，{item['type']}缺陷，{item['status']}）"]
        for item in open_items
    ] or [["/", "/"]]
    out += _table(["测试用例标识", "描述"], residual_rows)

    if not defects["total"]:
        defect_clause = "未发现软件缺陷"
    elif not open_items:
        defect_clause = f"测试发现的{defects['total']}个软件缺陷均已纠正"
    else:
        defect_clause = f"测试发现软件缺陷{defects['total']}个，已归零{defects['closed']}个，遗留{defects['open']}个"
    out += ["", "#### 评估说明", "", f"{company}依据测试单对{system}进行了{test_type}，{defect_clause}，认为{system}软件（版本{version}）：", ""]
    modules = _module_rows(stats)
    for idx, (name, b) in enumerate(modules):
        end = "。" if idx == len(modules) - 1 else "；"
        out += [
            f"{chr(ord('a') + idx)}){name}：设计{b['designed']}个用例，执行{b['executed']}个，通过{b['passed']}个，"
            f"未通过{b['failed']}个，未执行{b['not_run']}个{end}",
            "",
        ]
    closing = f"综上所述，{system}软件（版本{version}）{result}。" if result != "待评审" else f"综上所述，{system}软件（版本{version}）的测试结论待评审。"
    out += [closing, "", "### 3.2 测试环境的影响", "", "#### 3.2.1 软件环境", ""]

    soft = [[i, r["支持软件名称"], r["版本号"] or "/", r["用途"] or "/", r["介质"] or "/", r["来源"] or "/", r["保密性"] or "/"] for i, r in enumerate(profile.software, start=1)]
    out += _table(["序号", "支持软件名称", "版本号", "用途", "介质", "来源", "保密性"], soft or [[1, need("", "画像补「软件环境」"), "/", "/", "/", "/", "/"]])
    out += ["", "#### 3.2.2 硬件环境", ""]
    hard = [[i, r["硬件名称"], r["配置"] or "/", r["推荐型号"] or "/", r["用途"] or "/", r["数量"] or "/", r["保密性"] or "/"] for i, r in enumerate(profile.hardware, start=1)]
    out += _table(["序号", "硬件名称", "配置", "推荐型号", "用途", "数量", "保密性"], hard or [[1, need("", "画像补「硬件环境」"), "/", "/", "/", "/", "/"]])
    out += ["", "#### 3.2.3 测试环境影响", "", "测试环境影响情况见表。", ""]
    impacts = [[i, r["测试环境"], r["实装环境"] or "/", r["影响分析"] or "/", r["解决措施"] or "/"] for i, r in enumerate(profile.impacts, start=1)]
    out += _table(["序号", "测试环境", "实装环境", "影响分析", "解决措施"], impacts or [[1, need("", "画像补「测试环境影响」"), "/", "/", "/"]])
    out += ["", "#### 3.2.4 改进建议", ""]
    if open_items or final["not_run"] or final["failed"]:
        out += [need("", "按遗留缺陷与未执行用例写改进建议，没有建议写「无。」"), ""]
    else:
        out += ["无。", ""]

    remark = "无未执行的用例" if not final["not_run"] else f"未执行用例{final['not_run']}个，见第5章注释"
    reuse = f"{rg['reused']}/{rg['modified']}/{rg['added']}"
    out += [
        "## 4 详细测试结果",
        "",
        "### 4.1 测试结果总结",
        "",
        *_kv([
            ("软件标识号", basic("软件标识号")),
            ("软件名称", profile.get("软件名称") or system),
            ("编程语言", basic("编程语言")),
            ("程序规模", basic("程序规模")),
            ("测试周期", period),
            ("测试类型", test_type),
            ("测试人员", testers),
            ("备注", remark),
        ]),
        "",
        *_table(
            ["轮次", "设计或重用/修改/新增", "执行用例", "通过用例", "未通过用例", "未执行用例"],
            [
                ["测试用例", fr["designed"], fr["executed"], fr["passed"], fr["failed"], fr["not_run"]],
                ["回归测试用例", reuse, rg["executed"], rg["passed"], rg["failed"], rg["not_run"]],
            ],
        ),
        "",
        "#### 4.1.1 测试执行情况",
        "",
        f"首轮动态测试共设计{fr['designed']}个测试用例，执行用例{fr['executed']}个，通过的测试用例{fr['passed']}个，"
        f"未通过的测试用例{fr['failed']}个，未执行用例{fr['not_run']}个，测试用例的执行情况见第6章。",
        "",
        (f"测试组对动态测试所有未通过的测试用例进行分析和整理，动态测试发现软件缺陷共{defects['total']}个。" if defects["total"] else "动态测试未发现软件缺陷。"),
        "",
        *_table(
            ["测试类型", "设计用例", "执行/未执行", "通过/未通过"],
            [[test_type, fr["designed"], f"{fr['executed']}/{fr['not_run']}", f"{fr['passed']}/{fr['failed']}"]],
        ),
        "",
    ]
    if rg["reused"]:
        out.append(
            f"回归测试情况：测试组根据缺陷处理情况进行了影响域分析，回归测试中重用首轮测试设计的{rg['reused']}个测试用例，"
            f"新增{rg['added']}个测试用例，适应性修改{rg['modified']}个测试用例。回归测试共执行测试用例{rg['executed']}个，"
            f"通过{rg['passed']}个，未通过{rg['failed']}个，未执行{rg['not_run']}个。"
        )
    else:
        out.append("回归测试情况：缺陷表没有已解决或关闭的缺陷，本轮没有回归测试。")

    by_level = {row["level"]: row for row in defects["by_level"]}
    level_counts = "、".join(f"{lvl}{by_level[lvl]['total'] if lvl in by_level else 0}个" for lvl in LEVELS)
    extra = [row for row in defects["by_level"] if row["level"] not in LEVELS and row["total"]]
    if extra:
        level_counts += "、" + "、".join(f"{row['level']}{row['total']}个" for row in extra)
    if not defects["total"]:
        defect_text = "测试未发现被测软件缺陷。"
    elif not open_items:
        defect_text = f"测试共发现被测软件缺陷{defects['total']}个，其中{level_counts}。所有提交的软件缺陷都经过研制方的确认，测试发现的所有软件缺陷都已归零。"
    else:
        defect_text = f"测试共发现被测软件缺陷{defects['total']}个，其中{level_counts}。已归零{defects['closed']}个，遗留{defects['open']}个，见3.1残留问题。"

    matrix = []
    totals = {name: 0 for name, _ in TYPE_COLUMNS}
    for lvl in [*LEVELS, *(row["level"] for row in extra)]:
        row = by_level.get(lvl, {"types": {}, "closed": 0, "open": 0})
        counts = [row["types"].get(name, 0) for name, _ in TYPE_COLUMNS]
        for (name, _), n in zip(TYPE_COLUMNS, counts, strict=True):
            totals[name] += n
        matrix.append([lvl, *counts, row["closed"], row["open"]])
    matrix.append(["合计", *totals.values(), defects["closed"], defects["open"]])
    out += [
        "",
        "",
        "#### 4.1.2 缺陷归零情况",
        "",
        defect_text,
        "",
        *_table(["严重性等级", *(label for _, label in TYPE_COLUMNS), "归零缺陷数", "遗留缺陷数"], matrix),
        "",
        "## 5 注释",
        "",
    ]
    notes: list[str] = []
    for sheet in stats["sheets"]:
        notes.append(f"本报告依据测试单「{sheet['title']}」（{sheet['dir']}/testsheet.md）。")
        basis_note = _basis_note(sheet, root)
        if basis_note:
            notes.append(basis_note)
    for label, items in (("未执行或阻塞", stats["not_run_notes"]), ("部分通过", stats["partial_notes"])):
        if items:
            parts = [f"{n['id']}（{mdparse.plain(n['record']) or '测试单未写原因'}）" for n in items]
            notes.append(f"{label}用例{len(items)}个：" + "；".join(parts) + "。")
    for para in notes or ["无。"]:
        out += [para, ""]

    out += ["## 6 测试用例", ""]
    case_rows = []
    for case in stats["cases"]:
        pre = re.sub(r"\n\s*\n+", "\n", mdparse.plain(case["preconditions"]))
        data = re.sub(r"\n\s*\n+", "\n", mdparse.plain(case["test_data"]))
        if data:
            pre = (pre + "\n" if pre else "") + "测试数据：" + data
        steps = case["steps"]
        actions = "\n".join(f"{i}、{mdparse.plain(s['action'])}" for i, s in enumerate(steps, start=1) if s["action"])
        expected = "\n".join(f"{i}、{mdparse.plain(s['expected'])}" for i, s in enumerate(steps, start=1) if s["expected"])
        case_rows.append([
            case["seq"], case["module"] or case["group"] or "/", case["suite"] or case["subgroup"] or "/", case["id"], case["title"],
            pre or "无", actions or "/", expected or "/", FOLD.get(case["result"], "未执行"),
        ])
    out += _table(["序号", "模块", "子模块", "用例编号（测试标识）", "测试用例名称", "前置条件", "测试步骤", "预期结果", "结果"], case_rows)
    out.append("")
    return "\n".join(out), hints
