"""Named env-local profiles: resolve / apply / pointer file / CLI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tuner_testkit.config import (
    EnvProfileError,
    apply_selected_environment,
    environments_of,
    main,
    read_active_env_file,
    resolve_active_name,
    write_active_env,
)


def _target() -> SimpleNamespace:
    return SimpleNamespace(
        DATABASES={
            "main": {
                "type": "mysql",
                "host": "placeholder",
                "port": 3306,
                "user": "root",
                "password": "CHANGE_ME",
                "database": "example",
            }
        },
        TEST_BASE_URL="",
        ACTIVE_ENV=None,
    )


def _catalog(**profiles: dict) -> SimpleNamespace:
    return SimpleNamespace(ACTIVE_ENV=None, ENVIRONMENTS=dict(profiles))


_DEV = {
    "DATABASES": {"main": {"host": "dev.example", "database": "devdb"}},
    "TEST_BASE_URL": "http://dev.example:8000",
}
_UAT = {
    "DATABASES": {"main": {"host": "uat.example", "database": "uatdb"}},
    "TEST_BASE_URL": "http://uat.example:8000",
}


class TestResolveActiveName:
    def test_tuner_env_wins_over_file_and_default(self):
        name = resolve_active_name(
            available=("dev", "uat"),
            module_default="dev",
            environ={"TUNER_ENV": "uat"},
            active_file_text="dev",
        )
        assert name == "uat"

    def test_active_file_wins_over_module_default(self):
        name = resolve_active_name(
            available=("dev", "uat"),
            module_default="dev",
            environ={},
            active_file_text="uat",
        )
        assert name == "uat"

    def test_module_default_used_when_no_file_or_env(self):
        name = resolve_active_name(
            available=("dev", "uat"),
            module_default="dev",
            environ={},
            active_file_text=None,
        )
        assert name == "dev"

    def test_sole_key_when_nothing_selected(self):
        name = resolve_active_name(
            available=("dev",),
            module_default=None,
            environ={},
            active_file_text=None,
        )
        assert name == "dev"

    def test_multiple_keys_with_no_pointer_raises(self):
        with pytest.raises(EnvProfileError, match="未选择环境"):
            resolve_active_name(
                available=("dev", "uat"),
                module_default=None,
                environ={},
                active_file_text=None,
            )

    def test_unknown_tuner_env_raises(self):
        with pytest.raises(EnvProfileError, match="未知环境"):
            resolve_active_name(
                available=("dev", "uat"),
                module_default="dev",
                environ={"TUNER_ENV": "prd"},
                active_file_text=None,
            )

    def test_empty_available_raises(self):
        with pytest.raises(EnvProfileError, match="为空"):
            resolve_active_name(available=(), environ={})


class TestApplySelectedEnvironment:
    def test_returns_none_without_environments(self):
        target = _target()
        source = SimpleNamespace(DATABASES={"main": {"host": "flat"}}, TEST_BASE_URL="http://flat")
        assert apply_selected_environment(target, source, environ={}) is None
        assert target.DATABASES["main"]["host"] == "placeholder"

    def test_empty_environments_is_flat_fallback(self):
        target = _target()
        source = SimpleNamespace(ENVIRONMENTS={})
        assert environments_of(source) is None
        assert apply_selected_environment(target, source, environ={}) is None

    def test_applies_selected_profile_and_preserves_unspecified_fields(self):
        target = _target()
        source = _catalog(dev=_DEV, uat=_UAT)
        source.ACTIVE_ENV = "dev"
        applied = apply_selected_environment(
            target, source, environ={}, active_file_text=None
        )
        assert applied == "dev"
        assert target.ACTIVE_ENV == "dev"
        assert target.DATABASES["main"]["host"] == "dev.example"
        assert target.DATABASES["main"]["type"] == "mysql"
        assert target.DATABASES["main"]["database"] == "devdb"
        assert target.TEST_BASE_URL == "http://dev.example:8000"

    def test_applies_test_ui_base_url(self):
        target = _target()
        source = _catalog(
            dev={
                **_DEV,
                "TEST_UI_BASE_URL": "http://dev-ui.example:3000",
            }
        )
        source.ACTIVE_ENV = "dev"
        apply_selected_environment(target, source, environ={}, active_file_text=None)
        assert target.TEST_UI_BASE_URL == "http://dev-ui.example:3000"

    def test_file_pointer_selects_uat(self, tmp_path):
        target = _target()
        source = _catalog(dev=_DEV, uat=_UAT)
        source.ACTIVE_ENV = "dev"
        pointer = tmp_path / ".active_env"
        pointer.write_text("uat\n", encoding="utf-8")
        applied = apply_selected_environment(
            target, source, environ={}, active_file_path=pointer
        )
        assert applied == "uat"
        assert target.TEST_BASE_URL == "http://uat.example:8000"

    def test_non_dict_profile_raises(self):
        target = _target()
        source = SimpleNamespace(ACTIVE_ENV="dev", ENVIRONMENTS={"dev": "nope"})
        with pytest.raises(EnvProfileError, match="必须是 dict"):
            apply_selected_environment(target, source, environ={}, active_file_text=None)


class TestActiveEnvFile:
    def test_write_and_read_roundtrip(self, tmp_path):
        path = tmp_path / "config" / ".active_env"
        write_active_env("uat", path=path)
        assert read_active_env_file(path) == "uat"

    def test_skips_comments_and_blank_lines(self, tmp_path):
        path = tmp_path / ".active_env"
        path.write_text("# current\n\nuat\n", encoding="utf-8")
        assert read_active_env_file(path) == "uat"

    def test_missing_file_is_none(self, tmp_path):
        assert read_active_env_file(tmp_path / "missing") is None

    def test_write_rejects_blank_name(self, tmp_path):
        with pytest.raises(EnvProfileError):
            write_active_env("  ", path=tmp_path / ".active_env")


class TestCli:
    @pytest.fixture(autouse=True)
    def _clear_env_vars(self, monkeypatch):
        monkeypatch.delenv("TUNER_ENV", raising=False)

    def test_show_lists_and_marks_active(self, monkeypatch, capsys):
        source = _catalog(dev=_DEV, uat=_UAT)
        source.ACTIVE_ENV = "dev"
        monkeypatch.setattr("tuner_testkit.config.load_env_local", lambda: source)
        monkeypatch.setattr("tuner_testkit.config.read_active_env_file", lambda path=None: None)
        rc = main(["show"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "* dev" in out
        assert "uat" in out
        assert "http://dev.example:8000" in out
        assert "secret" not in out

    def test_use_writes_pointer(self, monkeypatch, tmp_path, capsys):
        source = _catalog(dev=_DEV, uat=_UAT)
        pointer = tmp_path / ".active_env"
        monkeypatch.setattr("tuner_testkit.config.load_env_local", lambda: source)
        monkeypatch.setattr("tuner_testkit.config.active_env_path", lambda: pointer)
        rc = main(["use", "uat"])
        assert rc == 0
        assert pointer.read_text(encoding="utf-8").strip() == "uat"
        out = capsys.readouterr().out
        assert "active: uat" in out
        assert "secret" not in out

    def test_use_prod_warns_but_writes(self, monkeypatch, tmp_path, capsys):
        source = _catalog(prd={**_UAT, "TEST_BASE_URL": "https://prd.example"})
        pointer = tmp_path / ".active_env"
        monkeypatch.setattr("tuner_testkit.config.load_env_local", lambda: source)
        monkeypatch.setattr("tuner_testkit.config.active_env_path", lambda: pointer)
        rc = main(["use", "prd"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "production-like" in err
        assert pointer.read_text(encoding="utf-8").strip() == "prd"

    def test_use_unknown_name(self, monkeypatch, capsys):
        source = _catalog(dev=_DEV)
        monkeypatch.setattr("tuner_testkit.config.load_env_local", lambda: source)
        rc = main(["use", "nope"])
        assert rc == 1
        assert "未知环境" in capsys.readouterr().err

    def test_use_without_environments(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "tuner_testkit.config.load_env_local",
            lambda: SimpleNamespace(DATABASES={}, TEST_BASE_URL="http://x"),
        )
        rc = main(["use", "dev"])
        assert rc == 1
        assert "没有 ENVIRONMENTS" in capsys.readouterr().err

    def test_default_argv_is_show(self, monkeypatch, capsys):
        source = _catalog(dev=_DEV)
        monkeypatch.setattr("tuner_testkit.config.load_env_local", lambda: source)
        monkeypatch.setattr("tuner_testkit.config.read_active_env_file", lambda path=None: None)
        assert main([]) == 0
        assert "active: dev" in capsys.readouterr().out
