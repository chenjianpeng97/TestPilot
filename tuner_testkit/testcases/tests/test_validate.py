from pathlib import Path

from tuner_testkit.testcases.validate import validate_tree

_INDEX = """---
kind: testcase-index
title: 测试用例模块索引
version: 1.0.0
---

# 测试用例模块索引

## 模块

| 模块 | 目录 | 范围 | 状态 |
| --- | --- | --- | --- |
| 用户系统 | `assets/testcases/用户系统/` | 登录 | 在用 |
"""

_MODULE = """---
kind: testcase-module
id: user-system
title: 用户系统
module: 用户系统
version: 1.0.0
---

# 用户系统

## 套件

| 套件 | 目录 |
| --- | --- |
| 用户登录 | [用户登录](用户登录/README.md) |
"""

_SUITE = """---
kind: testcase-suite
id: user-login
id_prefix: User-Login
title: 用户登录
module: 用户系统
version: 1.0.0
---

# 用户登录

## 用例

| ID | 名称 | 类型 | 状态 |
| --- | --- | --- | --- |
| [User-Login-valid-credentials](User-Login-valid-credentials.md) | 正确账号密码 | 正向 | 就绪 |
| [User-Login-wrong-password](User-Login-wrong-password.md) | 错误密码 | 反向 | 就绪 |
"""

_CASE = """---
kind: testcase
id: User-Login-valid-credentials
title: 正确账号密码
suite: 用户登录
module: 用户系统
id_prefix: User-Login
type: 正向
status: 就绪
execution: 手工
version: 1.0.0
---

# User-Login-valid-credentials 正确账号密码

## 前置条件

账号已注册。

## 步骤

### 1

- 操作：输入已注册账号与正确密码，点击登录
- 预期：进入首页或个人中心
"""

_CASE_NEGATIVE = """---
kind: testcase
id: User-Login-wrong-password
title: 错误密码
suite: 用户登录
module: 用户系统
id_prefix: User-Login
type: 反向
status: 就绪
execution: 手工
version: 1.0.0
---

# User-Login-wrong-password 错误密码

## 步骤

### 1

- 操作：输入已注册账号与错误密码，点击登录
- 预期：停留在登录页并提示账号或密码错误
"""


def _tree(root: Path, case: str = _CASE, suite: str = _SUITE) -> Path:
    base = root / "assets" / "testcases"
    suite_dir = base / "用户系统" / "用户登录"
    suite_dir.mkdir(parents=True)
    (base / "README.md").write_text(_INDEX, encoding="utf-8")
    (base / "用户系统" / "README.md").write_text(_MODULE, encoding="utf-8")
    (suite_dir / "README.md").write_text(suite, encoding="utf-8")
    (suite_dir / "User-Login-valid-credentials.md").write_text(case, encoding="utf-8")
    (suite_dir / "User-Login-wrong-password.md").write_text(_CASE_NEGATIVE, encoding="utf-8")
    return base


def test_valid_tree(tmp_path: Path) -> None:
    base = _tree(tmp_path)
    assert validate_tree(base) == []


def test_duplicate_id_and_bad_slug(tmp_path: Path) -> None:
    broken = _CASE.replace("id: User-Login-valid-credentials", "id: User-Login-wrong-password")
    broken = broken.replace(
        "# User-Login-valid-credentials 正确账号密码",
        "# User-Login-wrong-password 正确账号密码",
    )
    base = _tree(tmp_path, broken)
    numbered = base / "用户系统" / "用户登录" / "User-Login0001.md"
    numbered.write_text(
        _CASE.replace("User-Login-valid-credentials", "User-Login0001"),
        encoding="utf-8",
    )
    errors = validate_tree(base)
    assert any("duplicate User-Login-wrong-password" in item for item in errors)
    assert any("id must look like User-Login-valid-credentials" in item for item in errors)


def test_table_must_match_files(tmp_path: Path) -> None:
    suite = _SUITE.replace(
        "| [User-Login-wrong-password](User-Login-wrong-password.md) | 错误密码 | 反向 | 就绪 |\n",
        "",
    )
    base = _tree(tmp_path, suite=suite)
    errors = validate_tree(base)
    assert any("case table must list User-Login-wrong-password" in item for item in errors)


def test_stages_list_ok_and_rejects_unknown(tmp_path: Path) -> None:
    ok = _CASE.replace("execution: 手工\n", "execution: 手工\nstages: [冒烟, 系统测试]\n")
    base = _tree(tmp_path, ok)
    assert validate_tree(base) == []

    bad = _CASE.replace("execution: 手工\n", "execution: 手工\nstages: [回归]\n")
    base_bad = _tree(tmp_path / "bad", bad)
    errors = validate_tree(base_bad)
    assert any("stages items must be one of" in item for item in errors)
