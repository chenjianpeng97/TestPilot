"""Defect library: fixed template, id allocation, structural validation."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tuner_testkit.defects import create, next_id, validate_dir
from tuner_testkit.defects.__main__ import main

DAY = date(2026, 11, 4)

FILLED = """---
kind: defect
id: DEF-20261104-001
title: 部分退款后库存未回填
severity: 严重
type: 编码
status: 已解决
blocking: false
found: 2026-11-04
found_in: assets/testsheet/261104订单/testsheet.md#D1
testcase: Order-Refund-partial-amount
requirements: [REQ-order-refund-partial]
version: 1.1.0
---

# DEF-20261104-001 部分退款后库存未回填

## 现象

部分退款成功后库存没有加回。

## 复现步骤

1. 对订单 42 发起部分退款 1 件
2. 查看商品 A-1 库存

## 预期结果

库存回到 11。

## 实际结果

库存仍为 10。

## 历史

| 日期 | 轮次 | 状态 | 说明 |
| --- | --- | --- | --- |
| 2026-11-04 | 261104订单 | 激活 | 首次发现（D1） |
| 2026-11-06 | 261106订单回归 | 已解决 | 开发已修复，待回归 |
"""


def _workspace(root: Path) -> Path:
    (root / "assets" / "testsheet" / "261104订单").mkdir(parents=True)
    (root / "assets" / "testsheet" / "261104订单" / "testsheet.md").write_text("# 测试单\n", encoding="utf-8")
    case = root / "assets" / "testcases" / "订单" / "退款" / "Order-Refund-partial-amount.md"
    case.parent.mkdir(parents=True)
    case.write_text("---\nkind: testcase\n---\n", encoding="utf-8")
    (root / "knowledge" / "requirements").mkdir(parents=True)
    (root / "knowledge" / "requirements" / "REQ-order-refund-partial.md").write_text("---\n---\n", encoding="utf-8")
    defects = root / "knowledge" / "defects"
    defects.mkdir(parents=True)
    return defects


def test_valid_library(tmp_path: Path) -> None:
    defects = _workspace(tmp_path)
    (defects / "DEF-20261104-001.md").write_text(FILLED, encoding="utf-8")
    (defects / "CHANGELOG.md").write_text("# c\n", encoding="utf-8")
    assert validate_dir(defects) == []


def test_next_id_and_new_template_must_be_filled(tmp_path: Path) -> None:
    defects = _workspace(tmp_path)
    assert next_id(defects, DAY) == "DEF-20261104-001"
    (defects / "DEF-20261104-001.md").write_text(FILLED, encoding="utf-8")
    path = create(defects, day=DAY, title="退款单重复提交", severity="一般", defect_type="编码",
                  found_in="assets/testsheet/261104订单/testsheet.md#D2", round_name="261104订单",
                  testcase="Order-Refund-partial-amount", requirements=["REQ-order-refund-partial"])
    assert path.name == "DEF-20261104-002.md"
    assert next_id(defects, DAY) == "DEF-20261104-003"
    errors = validate_dir(defects)
    assert any("（待填）" in e for e in errors)  # template placeholders block the check until filled
    text = path.read_text(encoding="utf-8").replace("（待填）", "已填写")
    path.write_text(text, encoding="utf-8")
    assert validate_dir(defects) == []
    with pytest.raises(ValueError):
        create(defects, day=DAY, title="x", severity="严重严重", defect_type="编码")


def test_broken_defect_reports_each_rule(tmp_path: Path) -> None:
    defects = _workspace(tmp_path)
    broken = (
        FILLED.replace("severity: 严重", "severity: 高")
        .replace("type: 编码", "type: bug")
        .replace("blocking: false", "blocking: maybe")
        .replace("testcase: Order-Refund-partial-amount", "testcase: Order-Missing-case")
        .replace("requirements: [REQ-order-refund-partial]", "requirements: [REQ-missing]")
        .replace("## 预期结果\n\n库存回到 11。\n\n", "")
        .replace("1. 对订单 42 发起部分退款 1 件\n2. 查看商品 A-1 库存", "先退款再看库存")
        .replace("| 2026-11-06 | 261106订单回归 | 已解决 | 开发已修复，待回归 |\n", "")
    )
    (defects / "DEF-20261104-001.md").write_text(broken, encoding="utf-8")
    dup = FILLED.replace("DEF-20261104-001", "DEF-20261104-002")
    (defects / "DEF-20261104-002.md").write_text(dup, encoding="utf-8")
    (defects / "notes.md").write_text("x\n", encoding="utf-8")
    errors = "\n".join(validate_dir(defects))
    for needle in ("severity must be one of", "type must be one of", "blocking must be true or false",
                   "testcase Order-Missing-case not found", "requirement REQ-missing not found",
                   "section ## 预期结果 is required", "needs numbered steps", "front-matter status is 已解决",
                   "already recorded by DEF-20261104-001", "only DEF-<yyyymmdd>-<nnn>.md"):
        assert needle in errors, needle


def test_section_order_and_unknown_sections(tmp_path: Path) -> None:
    defects = _workspace(tmp_path)
    swapped = FILLED.replace("## 现象\n\n部分退款成功后库存没有加回。\n\n", "").replace(
        "## 历史", "## 现象\n\n部分退款成功后库存没有加回。\n\n## 备注\n\nx\n\n## 历史"
    )
    (defects / "DEF-20261104-001.md").write_text(swapped, encoding="utf-8")
    errors = "\n".join(validate_dir(defects))
    assert "unknown sections ['备注']" in errors
    assert "in order" in errors


def test_cli(tmp_path: Path, capsys) -> None:
    defects = _workspace(tmp_path)
    assert main(["next-id", "--date", "2026-11-04", "--dir", str(defects)]) == 0
    assert capsys.readouterr().out.strip() == "DEF-20261104-001"
    assert main(["new", "--title", "库存未回填", "--severity", "严重", "--type", "编码", "--date", "2026-11-04",
                 "--dir", str(defects)]) == 0
    assert '"id": "DEF-20261104-001"' in capsys.readouterr().out
    assert main(["check", str(defects)]) == 1  # placeholders still there
    assert main(["check", str(tmp_path / "nope")]) == 1


def test_found_in_survives_testsheet_archiving(tmp_path: Path) -> None:
    defects = _workspace(tmp_path)
    (defects / "DEF-20261104-001.md").write_text(FILLED, encoding="utf-8")
    (defects / "CHANGELOG.md").write_text("# c\n", encoding="utf-8")
    sheets = tmp_path / "assets" / "testsheet"
    (sheets / "archived").mkdir()
    (sheets / "261104订单").rename(sheets / "archived" / "261104订单")
    assert validate_dir(defects) == []  # found_in 仍写原路径
