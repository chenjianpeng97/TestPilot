from __future__ import annotations

from pathlib import Path

import pytest

CASE_TEMPLATE = """---
kind: testcase
id: {id}
title: {title}
suite: 登录
module: 账号
id_prefix: Login
type: {type}
status: 就绪
execution: 手工
version: 1.0.0
confidence: medium
---

# {id} {title}

## 前置条件

账号已存在。

## 测试数据

`account_id` `demo-user`。

## 步骤

### 1

- 操作：输入账号和口令，点击登录
- 预期：{expected}

### 2

- 操作：刷新页面
- 预期：仍停留在当前页
"""

# Execution record appended under step 2 of a copy (docs/spec/testsheet-step-record.md).
STEP_RECORDS = {
    "失败": "- 执行：失败\n- 实际：仍然进入了页面\n- 卡点：锁定后第 6 次登录没有被拒绝\n",
    "阻塞": "- 执行：阻塞\n- 实际：登录接口返回 502\n- 卡点：后端服务不可用\n- 缺少：后端恢复\n",
}

MODULE_README = """---
kind: testcase-module
id: account
title: 账号
module: 账号
source: 用户说明 2026-10-28
version: 1.0.0
confidence: medium
---

# 账号

## 范围

账号登录与锁定。

## 套件

| 套件 | 目录 |
| --- | --- |
| 登录 | [登录](登录/README.md) |
"""


def write_sheet(root: Path, name: str, rows: list[tuple[str, str, str]], *, counts: dict[str, int] | None, total: int | None, defects: str, info_extra: str = "| 版本 | 1.2.3 |\n") -> Path:
    """rows: (case_id, title, result)."""

    sheet_dir = root / name
    suite_dir = sheet_dir / "testcase" / "账号" / "登录"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (sheet_dir / "testcase" / "账号" / "README.md").write_text(MODULE_README, encoding="utf-8")
    table_rows = []
    for case_id, title, result in rows:
        text = CASE_TEMPLATE.format(id=case_id, title=title, type="反向", expected=f"{title}的预期")
        if result in STEP_RECORDS:
            text += STEP_RECORDS[result]
        (suite_dir / f"{case_id}.md").write_text(text, encoding="utf-8")
        table_rows.append(
            f"| [{case_id}](testcase/账号/登录/{case_id}.md) | 反向-{title} | 账号 | {title}的预期 | {result} | 记录{case_id} |"
        )
    counts = counts or {}
    intro = f"共 {total} 条。步骤在本目录 `testcase/`。\n\n" if total is not None else ""
    text = f"""# 登录测试单

{intro}依据：用户说明 2026-10-28。

## 怎么填

- 「结果」只写：通过、失败、阻塞、忽略；还没测就留空。

## 本轮信息

| 项 | 填写 |
| --- | --- |
| 测试人 | 测试员 |
| 日期 | 2026-10-28 ~ 2026-10-29 |
{info_extra}| 环境 | dev |
| 证据 | 本目录 `evidence/` |
| 通过 | {counts.get('通过', 0)} |
| 失败 | {counts.get('失败', 0)} |
| 阻塞 | {counts.get('阻塞', 0)} |
| 忽略 | {counts.get('忽略', 0)} |

## 测的时候先记住

- 锁定账号提示「用户已锁定」。

## 账号登录

| 用例 | 测试点 | 数据 | 预期要点 | 结果 | 实测记录 |
| --- | --- | --- | --- | --- | --- |
{chr(10).join(table_rows)}

## 缺陷

{defects}
"""
    (sheet_dir / "testsheet.md").write_text(text, encoding="utf-8")
    return sheet_dir


@pytest.fixture(autouse=True)
def _project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUNER_ROOT", str(tmp_path))


@pytest.fixture
def sheet_factory(tmp_path: Path):
    def _make(name: str = "261028登录", **kwargs):
        return write_sheet(tmp_path, name, **kwargs)

    return _make
