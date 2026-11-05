"""Object-level changelog: append writes one line; check enforces changelog + version bump."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tuner_testkit.workspace import changelog as cl


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)


def _case(version: str, body: str = "步骤") -> str:
    return f"---\nkind: testcase\nid: User-Login-ok\nversion: {version}\n---\n\n# User-Login-ok 登录\n\n{body}\n"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.delenv(cl.SKIP_ENV, raising=False)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "qa")
    case = tmp_path / "assets" / "testcases" / "用户" / "登录" / "User-Login-ok.md"
    case.parent.mkdir(parents=True)
    case.write_text(_case("1.0.0"), encoding="utf-8")
    (tmp_path / "packages" / "api_objects").mkdir(parents=True)
    (tmp_path / "packages" / "api_objects" / "__init__.py").write_text("", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_area_ownership() -> None:
    assert cl.area_for("assets/testcases/m/s/X.md").name == "testcases"
    assert cl.area_for("knowledge/wiki/domain-notes/a/b.md").name == "wiki"
    assert cl.area_for("knowledge/wiki/log.md") is None  # the changelog itself
    assert cl.area_for("packages/api_objects/__init__.py") is None  # infra
    assert cl.area_for("packages/action_words/_internal/db.py") is None
    assert cl.area_for("packages/tests/test_x.py") is None
    assert cl.area_for("tests/features/a.feature") is None


def test_append_writes_header_and_line(repo: Path) -> None:
    out = cl.append(repo, area="testcases", skill="maintain-testcases", action="更新", items=["User-Login-ok"],
                    version="1.0.0->1.1.0", reason="补充预期 | 第二步")
    text = (repo / "assets" / "testcases" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# CHANGELOG — maintained object library")
    assert "maintain-testcases | 更新 | items=User-Login-ok | version=1.0.0->1.1.0" in out["line"]
    assert "reason=补充预期 / 第二步" in out["line"]  # pipes cannot break the line format
    assert "author=qa@example.com" in out["line"]
    with pytest.raises(KeyError):
        cl.append(repo, area="nope", skill="x", action="y", items=[])


def test_check_requires_changelog_and_bump(repo: Path) -> None:
    case = repo / "assets" / "testcases" / "用户" / "登录" / "User-Login-ok.md"
    case.write_text(_case("1.0.0", "新步骤"), encoding="utf-8")
    _git(repo, "add", ".")
    result = cl.check(repo)
    assert not result["ok"]
    assert any("version` is still 1.0.0" in e for e in result["errors"])
    assert any("without a changelog line" in e for e in result["errors"])

    case.write_text(_case("1.1.0", "新步骤"), encoding="utf-8")
    cl.append(repo, area="testcases", skill="maintain-testcases", action="更新", items=["User-Login-ok"], version="1.0.0->1.1.0")
    _git(repo, "add", ".")
    result = cl.check(repo)
    assert result["ok"], result["errors"]
    assert result["areas"]["testcases"]["changelog_changed"] is True


def test_check_ignores_infra_and_honours_skip(repo: Path, monkeypatch) -> None:
    (repo / "packages" / "api_objects" / "__init__.py").write_text("# touched\n", encoding="utf-8")
    _git(repo, "add", ".")
    assert cl.check(repo)["ok"]
    (repo / "packages" / "api_objects" / "orders.py").write_text("method = 'GET'\n", encoding="utf-8")
    _git(repo, "add", ".")
    assert not cl.check(repo)["ok"]
    monkeypatch.setenv(cl.SKIP_ENV, "1")
    assert cl.check(repo)["skipped"] is True


def test_platform_repo_checks_only_nested_workspaces(tmp_path: Path) -> None:
    (tmp_path / "tuner_testkit").mkdir()
    (tmp_path / "tuner_testkit" / "project.py").write_text("", encoding="utf-8")
    (tmp_path / "dogfood").mkdir()
    (tmp_path / "dogfood" / "INDEX.project.md").write_text("# x\n", encoding="utf-8")
    assert cl.workspace_roots(tmp_path) == [tmp_path / "dogfood"]
