from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.apps.testreport import cli
from tuner_testkit.apps.testreport.stats import build

NEW_DEFECTS = """| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Login-Fixed-frozen | 冻结账号被放行 ![](a.png) | 严重 | 编码 | 关闭 | 否 |
| D2 | Login-Open-locked | 锁定提示不对 | 一般 | 需求 | 激活 | 否 |
| D3 | Login-Wait-deleted | 已删除账号可登录 | 致命 | 编码 | 已解决![](b.png) | 是 |
| D4 | / | 登录页图片未替换 | 轻微 | 文档 | 关闭 | 否 |
"""

NEW_ROWS = [
    ("Login-Fixed-frozen", "冻结账号拒绝", "通过"),
    ("Login-Open-locked", "锁定账号拒绝", "失败"),
    ("Login-Wait-deleted", "已删除账号拒绝", "失败"),
    ("Login-Plain-valid", "正确账号登录", "通过"),
    ("Login-Skip-expired", "过期账号", "阻塞"),
]
NEW_COUNTS = {"通过": 2, "失败": 2, "阻塞": 1}


def _codes(data: dict) -> set[str]:
    return {issue["code"] for issue in data["issues"] if issue["level"] == "error"}


def test_clean_sheet_has_no_errors(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    data = build([sheet], root=tmp_path)
    assert data["errors"] == 0, data["issues"]
    assert data["rows"] == {"total": 5, "通过": 2, "失败": 2, "阻塞": 1, "忽略": 0, "待执行": 0}
    assert data["final"] == {
        "designed": 5, "executed": 4, "passed": 2, "failed": 2, "not_run": 1, "blocked": 1, "ignored": 0, "pending": 0
    }


def test_first_round_and_regression_from_defects(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    data = build([sheet], root=tmp_path)
    first = data["first_round"]
    assert first["executed"] == 4
    assert set(first["failed_ids"]) == {"Login-Fixed-frozen", "Login-Open-locked", "Login-Wait-deleted"}
    assert first["passed"] == 1 and first["failed"] == 3 and first["not_run"] == 1
    regression = data["regression"]
    assert regression["case_ids"] == ["Login-Fixed-frozen", "Login-Wait-deleted"]
    assert regression["executed"] == 1 and regression["passed"] == 1
    assert regression["not_run"] == 1


def test_defect_matrix_and_residuals(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    defects = build([sheet], root=tmp_path)["defects"]
    assert defects["total"] == 4 and defects["closed"] == 2 and defects["open"] == 2
    levels = {row["level"]: row for row in defects["by_level"]}
    assert set(levels) == {"1级", "2级", "3级", "4级"}
    assert levels["1级"]["types"]["编码"] == 1 and levels["1级"]["open"] == 1
    assert levels["2级"]["closed"] == 1
    assert levels["4级"]["types"]["文档"] == 1
    items = {item["id"]: item for item in defects["items"]}
    assert items["D1"]["images"] == ["a.png"] and items["D1"]["phenomenon"] == "冻结账号被放行"
    assert items["D3"]["status"] == "已解决" and items["D3"]["residual"] is True
    assert items["D4"]["cases"] == []


def test_legacy_sheet_reports_drift(sheet_factory, tmp_path: Path) -> None:
    legacy = """| 编号 | 用例 | 现象 | 是否阻塞后续 |状态|
| --- | --- | --- | --- |--|
| 无 | Login-Fixed-frozen | 冻结账号被放行 | 否 |关闭|
"""
    sheet = sheet_factory(
        rows=[("Login-Fixed-frozen", "冻结账号拒绝", "通过"), ("Login-Plain-valid", "正确账号登录", "")],
        counts={"通过": 0, "失败": 1},
        total=3,
        defects=legacy,
        info_extra="",
    )
    data = build([sheet], root=tmp_path)
    codes = _codes(data)
    assert {"count_mismatch", "defect_columns_missing", "defect_id_invalid"} <= codes
    assert "defect_severity_invalid" not in codes and "defect_type_invalid" not in codes
    details = " ".join(issue["detail"] for issue in data["issues"])
    assert "共 3 条，表内 2 行" in details and "「通过」写 0，表内 1" in details
    assert any(issue["code"] == "info_missing" for issue in data["issues"])
    assert data["defects"]["by_level"][-1]["level"] == "未定级"


def test_placeholder_defect_row_is_ignored(sheet_factory, tmp_path: Path) -> None:
    empty = """| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |
| --- | --- | --- | --- | --- | --- | --- |
| 无 | | | | | | |
"""
    sheet = sheet_factory(rows=[("Login-Plain-valid", "正确账号登录", "通过")], counts={"通过": 1}, total=1, defects=empty)
    data = build([sheet], root=tmp_path)
    assert data["errors"] == 0 and data["defects"]["total"] == 0


def test_later_sheet_wins_for_same_case(sheet_factory, tmp_path: Path) -> None:
    first = sheet_factory(
        "261027登录",
        rows=[("Login-Plain-valid", "正确账号登录", "失败"), ("Login-Only-first", "首轮独有", "通过")],
        counts={"通过": 1, "失败": 1},
        total=2,
        defects=NEW_DEFECTS.split("| D2")[0].replace("Login-Fixed-frozen", "Login-Plain-valid"),
    )
    second = sheet_factory(
        "261029登录",
        rows=[("Login-Plain-valid", "正确账号登录", "通过")],
        counts={"通过": 1},
        total=1,
        defects="| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |\n| --- | --- | --- | --- | --- | --- | --- |\n| 无 | | | | | | |\n",
    )
    data = build([first, second], root=tmp_path)
    assert [case["id"] for case in data["cases"]] == ["Login-Plain-valid", "Login-Only-first"]
    assert data["cases"][0]["result"] == "通过" and data["cases"][0]["sheet"] == "261029登录"
    assert data["defects"]["items"][0]["key"] == "261027登录/D1"
    assert data["regression"]["passed"] == 1


def test_case_copy_fields_feed_the_appendix(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    data = build([sheet], root=tmp_path)
    case = data["cases"][0]
    assert case["module"] == "账号" and case["suite"] == "登录"
    assert case["preconditions"] == "账号已存在。"
    assert [step["action"] for step in case["steps"]] == ["输入账号和口令，点击登录", "刷新页面"]
    assert data["modules"][0]["scope"] == "账号登录与锁定。"
    assert data["not_run_notes"] == [
        {
            "id": "Login-Skip-expired",
            "result": "阻塞",
            "record": "记录Login-Skip-expired",
            "blockers": [{"step": 2, "status": "阻塞", "blocker": "后端服务不可用", "missing": "后端恢复", "evidence": ""}],
        }
    ]
    failed = next(c for c in data["cases"] if c["id"] == "Login-Open-locked")
    assert failed["steps"][1]["actual"] == "仍然进入了页面"


def test_cli_check_exit_codes(sheet_factory) -> None:
    clean = sheet_factory("clean", rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    drift = sheet_factory("drift", rows=NEW_ROWS, counts={"通过": 5}, total=5, defects=NEW_DEFECTS)
    assert cli.main(["stats", str(clean), "--check"]) == 0
    assert cli.main(["stats", str(drift), "--check"]) == 1
    assert cli.main(["stats", str(drift)]) == 0


def _copy_of(sheet: Path, case_id: str) -> Path:
    return sheet / "testcase" / "账号" / "登录" / f"{case_id}.md"


def test_blocked_case_without_step_record_is_an_error(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    copy = _copy_of(sheet, "Login-Skip-expired")
    text = copy.read_text(encoding="utf-8")
    copy.write_text(text[: text.index("- 执行：")], encoding="utf-8")
    data = build([sheet], root=tmp_path)
    assert any(i["code"] == "step_record_missing_case" and "Login-Skip-expired" in i["detail"] for i in data["issues"])


def test_step_record_field_rules(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    copy = _copy_of(sheet, "Login-Skip-expired")
    text = copy.read_text(encoding="utf-8")
    copy.write_text(text.replace("- 缺少：后端恢复\n", "").replace("- 执行：阻塞", "- 执行：卡住"), encoding="utf-8")
    codes = {i["code"] for i in build([sheet], root=tmp_path)["issues"]}
    assert "step_record_status" in codes
    copy.write_text(text.replace("- 缺少：后端恢复\n", ""), encoding="utf-8")
    codes = {i["code"] for i in build([sheet], root=tmp_path)["issues"]}
    assert "step_record_missing" in codes
    copy.write_text(text.replace("- 卡点：后端服务不可用\n", ""), encoding="utf-8")
    codes = {i["code"] for i in build([sheet], root=tmp_path)["issues"]}
    assert {"step_record_blocker", "step_record_missing_case"} <= codes


def test_step_record_evidence_path_is_checked(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    copy = _copy_of(sheet, "Login-Skip-expired")
    copy.write_text(copy.read_text(encoding="utf-8") + "- 证据：evidence/missing.png\n", encoding="utf-8")
    issues = build([sheet], root=tmp_path)["issues"]
    assert any(i["code"] == "step_record_evidence" and i["level"] == "warn" for i in issues)
    (sheet / "evidence").mkdir()
    (sheet / "evidence" / "missing.png").write_bytes(b"x")
    issues = build([sheet], root=tmp_path)["issues"]
    assert not any(i["code"] == "step_record_evidence" for i in issues)


def test_only_four_states_and_blank_means_pending(sheet_factory, tmp_path: Path) -> None:
    rows = [
        ("Login-Fixed-frozen", "冻结账号拒绝", "通过"),
        ("Login-Open-locked", "锁定账号拒绝", "失败"),
        ("Login-Skip-expired", "过期账号", "阻塞"),
        ("Login-Skip-ignored", "旧入口", "忽略"),
        ("Login-Plain-valid", "正确账号登录", ""),
    ]
    sheet = sheet_factory(rows=rows, counts={"通过": 1, "失败": 1, "阻塞": 1, "忽略": 1}, total=5, defects=NEW_DEFECTS.split("\n| D1")[0] + "\n| 无 | | | | | | |\n")
    data = build([sheet], root=tmp_path)
    assert data["errors"] == 0, data["issues"]
    assert data["rows"] == {"total": 5, "通过": 1, "失败": 1, "阻塞": 1, "忽略": 1, "待执行": 1}
    assert data["final"]["not_run"] == 3 and data["final"]["ignored"] == 1 and data["final"]["pending"] == 1
    assert {n["result"] for n in data["not_run_notes"]} == {"阻塞", "忽略", "待执行"}


def test_retired_result_words_are_rejected_with_a_hint(sheet_factory, tmp_path: Path) -> None:
    rows = [("Login-Fixed-frozen", "冻结账号拒绝", "部分通过"), ("Login-Plain-valid", "正确账号登录", "未执行")]
    sheet = sheet_factory(rows=rows, counts={}, total=2, defects="| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |\n| --- | --- | --- | --- | --- | --- | --- |\n| 无 | | | | | | |\n")
    issues = [i for i in build([sheet], root=tmp_path)["issues"] if i["code"] == "result_invalid"]
    assert len(issues) == 2
    assert "记「失败」" in issues[0]["detail"] and "留空" in issues[1]["detail"]


def test_ignored_case_needs_a_reason(sheet_factory, tmp_path: Path) -> None:
    sheet = sheet_factory(rows=[("Login-Skip-ignored", "旧入口", "忽略")], counts={"忽略": 1}, total=1, defects="| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |\n| --- | --- | --- | --- | --- | --- | --- |\n| 无 | | | | | | |\n")
    path = sheet / "testsheet.md"
    path.write_text(path.read_text(encoding="utf-8").replace("记录Login-Skip-ignored", ""), encoding="utf-8")
    codes = _codes(build([sheet], root=tmp_path))
    assert "ignore_reason" in codes


NO_DEFECTS = "| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |\n| --- | --- | --- | --- | --- | --- | --- |\n| 无 | | | | | | |\n"


def test_archive_moves_finished_round_and_logs(tmp_path: Path) -> None:
    from tuner_testkit.apps.testreport.archive import archive_sheet
    from tuner_testkit.apps.testreport.tests.conftest import write_sheet

    write_sheet(tmp_path / "assets" / "testsheet", "261028登录", rows=NEW_ROWS, counts=NEW_COUNTS, total=5, defects=NEW_DEFECTS)
    result = archive_sheet(tmp_path, "261028登录", author="qa@example.com")
    assert result["path"] == "assets/testsheet/archived/261028登录"
    assert not (tmp_path / "assets" / "testsheet" / "261028登录").exists()
    assert (tmp_path / "assets" / "testsheet" / "archived" / "261028登录" / "testsheet.md").is_file()
    log = (tmp_path / "assets" / "testsheet" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "archive" in log and "archived/261028登录" in log
    with pytest.raises(ValueError, match="already archived"):
        archive_sheet(tmp_path, "261028登录")


def test_archive_warns_about_pending_rows_but_still_moves(tmp_path: Path) -> None:
    from tuner_testkit.apps.testreport.archive import archive_sheet
    from tuner_testkit.apps.testreport.tests.conftest import write_sheet

    rows = [("Login-Plain-valid", "正确账号登录", "")]
    write_sheet(tmp_path / "assets" / "testsheet", "261028登录", rows=rows, counts={}, total=1, defects=NO_DEFECTS)
    preview = archive_sheet(tmp_path, "261028登录", dry_run=True)
    assert preview["moved"] is False and any("待执行" in w for w in preview["warnings"])
    assert (tmp_path / "assets" / "testsheet" / "261028登录" / "testsheet.md").is_file()
    result = archive_sheet(tmp_path, "261028登录")
    assert result["moved"] is True and result["path"].startswith("assets/testsheet/archived/")
    assert "待执行" in (tmp_path / "assets" / "testsheet" / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="round must be"):
        archive_sheet(tmp_path, "archived")
