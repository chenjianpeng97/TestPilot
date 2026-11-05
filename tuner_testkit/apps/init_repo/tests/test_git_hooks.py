"""Deterministic git hooks (tools/git-hooks) — run as plain scripts."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOKS = REPO_ROOT / "tools" / "git-hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_secret_scan_flags_values_not_words(tmp_path: Path) -> None:
    scan = _load("secret_scan")
    clean = tmp_path / "clean.py"
    clean.write_text(
        'PASSWORD = "{{password}}"\n'
        'token = os.environ["TEST_TOKEN"]\n'
        "# the password field is masked as ***\n"
        'api_key = "CHANGE_ME"\n',
        encoding="utf-8",
    )
    assert scan.scan_paths([str(clean)]) == []
    dirty = tmp_path / "dirty.yaml"
    dirty.write_text(
        "password: Sup3rSecretValue!\n"  # fake fixture — secret-scan: allow
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n"  # fake fixture — secret-scan: allow
        "jwt: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U\n"  # secret-scan: allow
        "allowed: Sup3rSecretValue!  # secret-scan: allow\n",
        encoding="utf-8",
    )
    findings = scan.scan_paths([str(dirty)])
    assert len(findings) == 3
    assert not any("Sup3rSecretValue!" in f for f in findings)  # masked output


def test_secret_scan_cli_uses_injected_staged_list(tmp_path: Path) -> None:
    bad = tmp_path / "config.py"
    bad.write_text('DB_PASSWORD = "p@ssw0rd-real"\n', encoding="utf-8")  # fake fixture — secret-scan: allow
    env = {**os.environ, "TUNER_COMMIT_STAGED": str(bad), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, str(HOOKS / "secret_scan.py")], env=env, capture_output=True, text=True, encoding="utf-8", cwd=str(tmp_path))
    assert proc.returncode == 1
    assert "credential-looking assignment `PASSWORD`" in proc.stderr
    assert "p@ssw0rd-real" not in proc.stderr  # never echo the secret


def test_hooks_read_staged_non_ascii_paths(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=str(tmp_path), check=True, capture_output=True)

    git("init", "-q")
    sheet = tmp_path / "assets" / "testsheet" / "260101登录" / "testsheet.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")  # fake fixture — secret-scan: allow
    git("add", ".")
    env = {key: value for key, value in os.environ.items() if key not in {"TUNER_COMMIT_STAGED", "GIT_CONFIG_PARAMETERS"}}
    env.update(PYTHONIOENCODING="utf-8", GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.quotepath", GIT_CONFIG_VALUE_0="true")

    scan = subprocess.run([sys.executable, str(HOOKS / "secret_scan.py")], env=env, capture_output=True, cwd=str(tmp_path))
    assert scan.returncode == 1
    assert "260101登录/testsheet.md" in scan.stderr.decode("utf-8")

    msg = tmp_path / "msg.txt"
    msg.write_text("feat(index): add sheet\n", encoding="utf-8")
    check = subprocess.run([sys.executable, str(HOOKS / "validate_commit_msg.py"), str(msg)], env=env, capture_output=True, cwd=str(tmp_path))
    assert check.returncode == 1
    assert "assets" in check.stderr.decode("utf-8")


def test_validate_commit_msg_scope_coverage(tmp_path: Path) -> None:
    validate = _load("validate_commit_msg")
    msg = tmp_path / "msg.txt"
    msg.write_text("feat(dogfood): add sample tool\n", encoding="utf-8")
    os.environ["TUNER_COMMIT_STAGED"] = "dogfood/apps/sample_tool/cli.py"
    try:
        assert validate.main(["x", str(msg)]) == 0
        os.environ["TUNER_COMMIT_STAGED"] = "dogfood/apps/sample_tool/cli.py\ntuner_testkit/tools/manifest.py"
        assert validate.main(["x", str(msg)]) == 1  # packages layer not covered
        msg.write_text("feat(dogfood,packages): add sample tool\n", encoding="utf-8")
        assert validate.main(["x", str(msg)]) == 0
        msg.write_text("added stuff\n", encoding="utf-8")
        assert validate.main(["x", str(msg)]) == 1
        os.environ["TUNER_COMMIT_STAGED"] = "work/tasks/TASK-20260924-001.md"
        msg.write_text("feat(work): record order test task\n", encoding="utf-8")
        assert validate.main(["x", str(msg)]) == 0
        os.environ["TUNER_COMMIT_STAGED"] = "knowledge/requirements/REQ-a.md\nassets/testcases/m/s/X.md"
        msg.write_text("feat(knowledge): ingest PRD\n", encoding="utf-8")
        assert validate.main(["x", str(msg)]) == 1  # assets layer not covered
        msg.write_text("feat(knowledge,assets): ingest PRD and add cases\n", encoding="utf-8")
        assert validate.main(["x", str(msg)]) == 0
    finally:
        os.environ.pop("TUNER_COMMIT_STAGED", None)
