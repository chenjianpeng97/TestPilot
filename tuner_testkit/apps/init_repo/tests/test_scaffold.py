"""scaffold must work from a blank cwd (uv tool install, no SUT yet)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit import __version__
from tuner_testkit.apps.init_repo.__main__ import main
from tuner_testkit.apps.init_repo.scaffold import scaffold

_REPO_ROOT = Path(__file__).resolve().parents[4]
_STUB_ENV = Path(__file__).resolve().parents[1] / "stubs" / "config" / "env.py"


def _forbid_project_root(*_args, **_kwargs):
    raise AssertionError("scaffold must not call project_root()")


def test_scaffold_from_non_project_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tuner_testkit.project.project_root", _forbid_project_root)
    dest = tmp_path / "new-sut"
    actions = scaffold(dest, with_ai=True, overwrite=False)
    assert dest.is_dir()
    assert (dest / "pyproject.toml").is_file()
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "new-sut"' in pyproject
    assert f'"tuner-testkit[db,api]>={__version__}"' in pyproject
    assert "[tool.tuner-testkit]" in pyproject
    assert 'report = ["tuner-testkit[report]"]' in pyproject
    assert 'requires-python = ">=3.12,<3.14"' in (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert (dest / ".python-version").read_text(encoding="utf-8") == "3.12\n"
    assert (dest / "config" / "env.py").is_file()
    assert (dest / "packages" / "action_words" / "__init__.py").is_file()
    assert (dest / ".cursor" / "rules").is_dir()
    assert (dest / "artifacts" / "inbox").is_dir()
    assert (dest / "data" / "sut-accounts.example.yaml").is_file()
    assert "replace-me" in (dest / "data" / "sut-accounts.example.yaml").read_text(encoding="utf-8")
    assert any(line.startswith("copy config/env.py") for line in actions)
    assert any("dna sync (exit 0)" in line for line in actions)
    # 5.x stubs: gitignore, project index with auto fences, behave environments + G/W/T steps, pytest conftest
    assert "artifacts/runs/" in (dest / ".gitignore").read_text(encoding="utf-8")
    assert "<!-- auto:begin:apps -->" in (dest / "INDEX.project.md").read_text(encoding="utf-8")
    for stage in ("api", "ui"):
        assert "report_run_begin" in (dest / "tests" / "features" / f"{stage}_environment.py").read_text(encoding="utf-8")
        for kind in ("given", "when", "then"):
            assert (dest / "tests" / "features" / f"{stage}_steps" / f"{kind}.py").is_file()
    assert (dest / "tests" / "pytest" / "conftest.py").is_file()
    assert not (dest / "packages" / "api_objects" / "plane.py").exists()
    assert (dest / "workbench.cmd").is_file()
    assert (dest / "workbench.sh").is_file()
    assert (dest / ".cursor" / "REGISTRY.md").is_file()
    assert any(line.startswith("write .cursor/REGISTRY.md") for line in actions)
    # 7.0 layout: knowledge layer, asset layer, tasks, run dirs, config template, workspace DNA view
    for rel in ("knowledge/ddl", "knowledge/raw", "knowledge/wiki/domain-notes", "knowledge/requirements",
                "knowledge/defects", "assets/testdesign", "assets/testcases", "work/tasks", "artifacts/runs",
                "artifacts/reports"):
        assert (dest / rel).is_dir(), rel
    assert not (dest / "assets" / "ddl").exists()
    assert (dest / "knowledge" / "wiki" / "index.md").is_file()
    assert (dest / "config" / "env_local.py.example").is_file()
    assert "CHANNELS" in (dest / "config" / "env.py").read_text(encoding="utf-8")
    assert "role: admin" in (dest / "data" / "sut-accounts.example.yaml").read_text(encoding="utf-8")
    assert "auto:begin:knowledge" in (dest / "INDEX.project.md").read_text(encoding="utf-8")
    assert not (dest / ".cursor" / "skills" / "release-template").exists()
    assert (dest / ".cursor" / "skills" / "health-check" / "SKILL.md").is_file()
    assert "本仓不是 workspace" not in (dest / "AGENTS.md").read_text(encoding="utf-8")
    assert (dest / ".tuner-dna.json").is_file()


def test_scaffold_project_name_follows_folder(tmp_path: Path):
    dest = tmp_path / "Acme"
    actions = scaffold(dest, with_ai=False)
    text = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "acme"' in text
    assert any(line == "write pyproject.toml (acme)" for line in actions)


def test_scaffold_name_override(tmp_path: Path):
    dest = tmp_path / "clients"
    scaffold(dest, with_ai=False, project_name="Hospital-Billing")
    text = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "Hospital-Billing"' in text


def test_scaffold_rejects_invalid_name_before_creating_the_folder(tmp_path: Path):
    dest = tmp_path / "acme"
    with pytest.raises(ValueError, match="invalid project name"):
        scaffold(dest, with_ai=False, project_name="bad name")
    assert not dest.exists()


def test_cli_name_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dest = tmp_path / "Acme"
    code = main(["scaffold", str(dest), "--name", "acme", "--no-ai"])
    captured = capsys.readouterr()
    assert code == 0
    assert "write pyproject.toml (acme)" in captured.out
    assert 'name = "acme"' in (dest / "pyproject.toml").read_text(encoding="utf-8")


def test_cli_rejects_invalid_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dest = tmp_path / "acme"
    code = main(["scaffold", str(dest), "--name", "bad name", "--no-ai"])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid project name" in captured.err
    assert not dest.exists()


def test_scaffold_uses_packaged_stubs_when_not_editable(tmp_path: Path, monkeypatch):
    """Simulate `uv tool install` (no template checkout beside site-packages)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tuner_testkit.project.template_source_root", lambda: None)
    monkeypatch.setattr("tuner_testkit.project.project_root", _forbid_project_root)
    monkeypatch.setenv("TUNER_DNA_ROOT", str(_REPO_ROOT))
    dest = tmp_path / "from-wheel"
    actions = scaffold(dest, with_ai=True, overwrite=False)
    assert _STUB_ENV.is_file()
    assert (dest / "config" / "env.py").read_text(encoding="utf-8") == _STUB_ENV.read_text(
        encoding="utf-8"
    )
    assert (dest / "artifacts" / "inbox").is_dir()
    assert (dest / "data" / "sut-accounts.example.yaml").is_file()
    assert any(line.startswith("copy config/env.py") for line in actions)
    assert any("dna sync (exit 0)" in line for line in actions)
