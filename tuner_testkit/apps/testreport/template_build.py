"""Turn the sample GJB438B test report docx into a docxtpl template.

Anchors are the sample's own texts and table headers, so a re-styled copy of the
same layout can be converted again with ``tuner-testreport build-template``.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

W_P = qn("w:p")
W_R = qn("w:r")
W_T = qn("w:t")
W_TR = qn("w:tr")
W_TC = qn("w:tc")
W_PPR = qn("w:pPr")
W_SECTPR = qn("w:sectPr")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_SETTINGS_AFTER_UPDATE_FIELDS = {
    "hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr",
    "attachedSchema", "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
    "doNotAutoCompressPictures", "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType",
    "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator",
}


class TemplateLayoutError(RuntimeError):
    pass


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(W_T))


def _set_text(p_el, text: str) -> None:
    runs = [r for r in p_el.iter(W_R) if r.find(W_T) is not None]
    if not runs:
        run = OxmlElement("w:r")
        p_el.append(run)
        runs = [run]
    first = runs[0]
    for extra in runs[1:]:
        extra.getparent().remove(extra)
    for child in list(first):
        if child.tag != qn("w:rPr"):
            first.remove(child)
    t = OxmlElement("w:t")
    t.set(XML_SPACE, "preserve")
    t.text = text
    first.append(t)


def _set_cell(tc, text: str) -> None:
    paras = tc.findall(W_P)
    if not paras:
        raise TemplateLayoutError("table cell without paragraph")
    _set_text(paras[0], text)
    for extra in paras[1:]:
        tc.remove(extra)


def _rows(tbl):
    return tbl.findall(W_TR)


def _cells(tr):
    return tr.findall(W_TC)


def _expect(cond: bool, message: str) -> None:
    if not cond:
        raise TemplateLayoutError(message)


def _loop_rows(tbl, body_index: int, loop: str, fields: list[str], *, keep_after: int = 0) -> None:
    rows = _rows(tbl)
    body = rows[body_index]
    tail_end = len(rows) - keep_after
    for tr in rows[body_index + 1:tail_end]:
        tbl.remove(tr)
    cells = _cells(body)
    _expect(len(cells) == len(fields), f"loop row has {len(cells)} cells, expected {len(fields)}")
    for tc, expr in zip(cells, fields, strict=True):
        _set_cell(tc, expr)
    opener = deepcopy(body)
    closer = deepcopy(body)
    for row, tag in ((opener, "{%tr for " + loop + " %}"), (closer, "{%tr endfor %}")):
        for idx, tc in enumerate(_cells(row)):
            _set_cell(tc, tag if idx == 0 else "")
    body.addprevious(opener)
    body.addnext(closer)


def _find_table(doc, predicate, label: str):
    for table in doc.tables:
        if predicate([_text(tc) for tc in _cells(_rows(table._tbl)[0])]):
            return table._tbl
    raise TemplateLayoutError(f"table not found: {label}")


def _body_paragraphs(doc):
    return [el for el in doc.element.body if el.tag == W_P]


def _find_para(doc, predicate, label: str, *, after=None):
    started = after is None
    for p in _body_paragraphs(doc):
        if not started:
            started = p is after
            continue
        if predicate(_text(p).strip()):
            return p
    raise TemplateLayoutError(f"paragraph not found: {label}")


def _heading(doc, title: str):
    for p in _body_paragraphs(doc):
        style = p.find(f"{W_PPR}/{qn('w:pStyle')}")
        if style is not None and _text(p).strip() == title:
            return p
    raise TemplateLayoutError(f"heading not found: {title}")


def _enable_update_fields(doc) -> None:
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is not None:
        return
    flag = OxmlElement("w:updateFields")
    flag.set(qn("w:val"), "true")
    for child in settings:
        if child.tag.split("}")[-1] in _SETTINGS_AFTER_UPDATE_FIELDS:
            child.addprevious(flag)
            return
    settings.append(flag)


def build_template(source: Path, out: Path) -> Path:
    doc = Document(str(source))

    revision_page = _find_para(doc, lambda t: t == "修订页", "修订页")
    _set_text(_find_para(doc, lambda t: t.endswith("系统") and len(t) < 30, "封面系统名"), "{{ system_name }}")
    _set_text(_find_para(doc, lambda t: t.endswith("公司") and len(t) < 40, "封面公司"), "{{ company }}")
    _set_text(_find_para(doc, lambda t: re.fullmatch(r"\d{4}年\d{1,2}月", t) is not None, "封面日期"), "{{ report_month }}")
    _expect(revision_page is not None, "修订页 missing")

    rev = _find_table(doc, lambda h: h[:2] == ["序号", "版本号"], "修订页")
    _loop_rows(rev, 1, "r in revisions", ["{{ r.seq }}", "{{ r.version }}", "{{ r.date }}", "{{ r.change }}", "{{ r.author }}"])

    for prefix, expr in (
        ("a)文档适用系统", "a)文档适用系统：{{ system_name }}；"),
        ("b)文档标题", "b)文档标题：{{ doc_title }}；"),
        ("c)文档标识号", "c)文档标识号：{{ doc_no }}；"),
        ("d)文档版本号", "d)文档版本号：{{ doc_version }}；"),
        ("e)缩略语", "e)缩略语：{{ abbreviations }}。"),
        ("a)需方", "a)需方：{{ buyer }}"),
        ("b)开发方", "b)开发方：{{ developer }}"),
        ("c)保障机构", "c)保障机构：{{ support }}"),
    ):
        _set_text(_find_para(doc, lambda t, p=prefix: t.startswith(p), prefix), expr)

    for title, expr in (("系统概述", "{{ overview }}"), ("运行现场", "{{ run_site }}"), ("文档概述", "{{ doc_overview }}"), ("改进建议", "{{ suggestions }}")):
        _set_text(_find_para(doc, bool, f"{title} 正文", after=_heading(doc, title)), expr)

    refs = _find_table(doc, lambda h: h[:2] == ["序号", "文档编号"], "引用文档")
    _loop_rows(refs, 1, "r in references", ["{{ r.seq }}", "{{ r.code }}", "{{ r.title }}", "{{ r.org }}", "{{ r.date }}"])

    evaluation = _find_table(doc, lambda h: h and h[0].startswith("被测软件评价"), "总体评估")
    head_paras = _cells(_rows(evaluation)[0])[0].findall(W_P)
    _expect(len(head_paras) >= 3, "总体评估表第一格应有三段")
    _set_text(head_paras[0], "被测软件评价：（版本{{ version }}）{{ verdict }}")
    _set_text(head_paras[1], "{{ verdict_detail }}")
    _set_text(head_paras[2], "{{ residual_intro }}")
    _loop_rows(evaluation, 3, "r in residuals", ["{{ r.case }}", "{{ r.desc }}"])

    eval_first = _find_para(doc, bool, "总体评估正文", after=_heading(doc, "对被测试软件的总体评估"))
    stop = _heading(doc, "测试环境的影响")
    _set_text(eval_first, "{{ evaluation }}")
    sibling = eval_first.getnext()
    while sibling is not None and sibling is not stop:
        nxt = sibling.getnext()
        if sibling.tag == W_P:
            sibling.getparent().remove(sibling)
        sibling = nxt

    software = _find_table(doc, lambda h: "支持软件名称" in h, "软件环境")
    _loop_rows(software, 1, "r in software", ["{{ r.seq }}", "{{ r.name }}", "{{ r.version }}", "{{ r.purpose }}", "{{ r.media }}", "{{ r.source }}", "{{ r.secrecy }}"])
    hardware = _find_table(doc, lambda h: "硬件名称" in h, "硬件环境")
    _loop_rows(hardware, 1, "r in hardware", ["{{ r.seq }}", "{{ r.name }}", "{{ r.config }}", "{{ r.model }}", "{{ r.purpose }}", "{{ r.qty }}", "{{ r.secrecy }}"])
    impact = _find_table(doc, lambda h: "实装环境" in h, "测试环境影响")
    _loop_rows(impact, 1, "r in env_impacts", ["{{ r.seq }}", "{{ r.test_env }}", "{{ r.real_env }}", "{{ r.analysis }}", "{{ r.measure }}"])

    summary = _find_table(doc, lambda h: h and h[0] == "被测软件", "测试结果总结")
    rows = _rows(summary)
    _expect(len(rows) == 11, f"测试结果总结 has {len(rows)} rows, expected 11")
    labels = {9: "测试人员", 10: "备注", 3: "测试周期", 4: "测试类型"}
    for idx, label in labels.items():
        _expect(_text(_cells(rows[idx])[0]).strip() == label, f"测试结果总结第 {idx + 1} 行应为 {label}")
    plan = {
        0: {2: "{{ s.software_id }}"},
        1: {2: "{{ s.software_name }}"},
        2: {2: "{{ s.language }}", 4: "{{ s.size }}"},
        3: {1: "{{ s.period }}"},
        4: {1: "{{ s.test_type }}"},
        6: {1: "{{ fr.designed }}", 2: "{{ fr.executed }}", 3: "{{ fr.passed }}", 4: "{{ fr.failed }}", 5: "{{ fr.not_run }}"},
        8: {1: "{{ rg.reuse }}", 2: "{{ rg.executed }}", 3: "{{ rg.passed }}", 4: "{{ rg.failed }}", 5: "{{ rg.not_run }}"},
        9: {1: "{{ s.testers }}"},
        10: {1: "{{ s.remark }}"},
    }
    for row_idx, cells in plan.items():
        tcs = _cells(rows[row_idx])
        for cell_idx, expr in cells.items():
            _set_cell(tcs[cell_idx], expr)

    exec_first = _find_para(doc, bool, "测试执行情况正文", after=_heading(doc, "测试执行情况"))
    _set_text(exec_first, "{{ execution }}")
    nxt = exec_first.getnext()
    if nxt is not None and nxt.tag == W_P and _text(nxt).strip() and not _text(nxt).strip() == "测试执行情况":
        nxt.getparent().remove(nxt)
    exec_table = _find_table(doc, lambda h: h and h[0] == "测试类型", "测试执行情况")
    _loop_rows(exec_table, 2, "r in exec_rows", ["{{ r.type }}", "{{ r.designed }}", "{{ r.run }}", "{{ r.passed }}"])
    _set_text(_find_para(doc, lambda t: t.startswith("回归测试情况"), "回归测试情况"), "{{ regression }}")
    _set_text(_find_para(doc, lambda t: t.startswith("测试共发现被测软件缺陷"), "缺陷归零正文"), "{{ defect_summary }}")

    defects = _find_table(doc, lambda h: h and h[0] == "严重性等级", "缺陷归零情况")
    total_row = _rows(defects)[-1]
    _expect(_text(_cells(total_row)[0]).strip() == "合计", "缺陷归零表最后一行应为合计")
    _loop_rows(
        defects, 2, "r in defect_rows",
        ["{{ r.level }}", "{{ r.req }}", "{{ r.design }}", "{{ r.code }}", "{{ r.doc }}", "{{ r.other }}", "{{ r.closed }}", "{{ r.open }}"],
        keep_after=1,
    )
    total_fields = ["{{ dt.req }}", "{{ dt.design }}", "{{ dt.code }}", "{{ dt.doc }}", "{{ dt.other }}", "{{ dt.closed }}", "{{ dt.open }}"]
    total_cells = _cells(total_row)[1:]
    _expect(len(total_cells) == len(total_fields), f"defect total row has {len(total_cells) + 1} cells, expected {len(total_fields) + 1}")
    for tc, expr in zip(total_cells, total_fields, strict=True):
        _set_cell(tc, expr)

    notes = _find_para(doc, bool, "注释正文", after=_heading(doc, "注释"))
    notes_copy = deepcopy(notes)
    ppr = notes_copy.find(W_PPR)
    if ppr is not None and ppr.find(W_SECTPR) is not None:
        ppr.remove(ppr.find(W_SECTPR))
    _set_text(notes_copy, "{{ notes }}")
    notes.addprevious(notes_copy)
    _set_text(notes, "")

    cases = _find_table(doc, lambda h: "用例编号（测试标识）" in h, "测试用例")
    _loop_rows(
        cases, 1, "c in cases",
        ["{{ c.seq }}", "{{ c.module }}", "{{ c.suite }}", "{{ c.id }}", "{{ c.title }}", "{{ c.pre }}", "{{ c.action }}", "{{ c.expected }}", "{{ c.result }}"],
    )

    _enable_update_fields(doc)
    props = doc.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.title = ""
    props.comments = ""
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
