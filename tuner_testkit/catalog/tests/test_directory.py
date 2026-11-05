"""Directory slice: ``@tool`` + ``@register`` only, no git, mtime cache."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tuner_testkit.action_words import registry as words_registry
from tuner_testkit.catalog.directory import build_directory, clear_directory_cache, entry_mtimes
from tuner_testkit.tools import manifest as tools_manifest

DOGFOOD = Path(__file__).resolve().parents[2] / "tests_fixtures" / "sample_workspace"


def setup_function() -> None:
    tools_manifest.reset_registry_for_tests()
    words_registry.reset_registry_for_tests()
    clear_directory_cache()


def teardown_function() -> None:
    tools_manifest.reset_registry_for_tests()
    words_registry.reset_registry_for_tests()
    clear_directory_cache()
    for name in [m for m in sys.modules if m == "packages" or m.startswith("packages.")]:
        sys.modules.pop(name, None)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_directory_does_not_call_git(monkeypatch, tmp_path: Path) -> None:
    real_run = subprocess.run

    def guarded(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]) == "git":
            raise AssertionError(f"git should not run: {cmd}")
        return real_run(*args, **kwargs)

    monkeypatch.setattr("subprocess.run", guarded)
    monkeypatch.setattr("tuner_testkit.catalog.scan.git_first_author", lambda *a, **k: (_ for _ in ()).throw(AssertionError("git_first_author")))
    monkeypatch.setattr("tuner_testkit.catalog.scan.read_git_meta", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read_git_meta")))

    _write(tmp_path / "apps" / "__init__.py", "")
    _write(tmp_path / "apps" / "hello" / "__init__.py", "")
    _write(
        tmp_path / "apps" / "hello" / "tool.py",
        "from argparse import ArgumentParser\n"
        "from tuner_testkit.tools import tool\n\n"
        "@tool(tool_id='hello', name='Hello', module='apps.hello', summary='hi')\n"
        "def build_parser():\n"
        "    p = ArgumentParser()\n"
        "    p.add_argument('--n', type=int, default=1, help='n')\n"
        "    return p\n",
    )
    payload = build_directory(tmp_path, include_kit_tools=False, refresh=True)
    ids = {row["tool_id"] for row in payload["tools"]}
    assert "hello" in ids
    assert payload["counts_by_kind"]["apps"] >= 1
    assert payload["action_words"] == []


def test_directory_cache_ignores_asset_mtime(tmp_path: Path) -> None:
    _write(tmp_path / "apps" / "__init__.py", "")
    _write(tmp_path / "apps" / "hello" / "__init__.py", "")
    _write(tmp_path / "apps" / "hello" / "tool.py", "from argparse import ArgumentParser\nfrom tuner_testkit.tools import tool\n\n@tool(tool_id='hello', name='Hello', module='apps.hello')\ndef build_parser():\n    p = ArgumentParser()\n    p.add_argument('--n', type=int, default=1, help='n')\n    return p\n")
    first = build_directory(tmp_path, include_kit_tools=False)
    stamp = entry_mtimes(tmp_path)
    _write(tmp_path / "assets" / "usecases" / "note.md", "# unrelated knowledge\n")
    assert entry_mtimes(tmp_path) == stamp
    second = build_directory(tmp_path, include_kit_tools=False)
    assert second is first


def test_directory_hides_local_visibility_words(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TUNER_ROOT", str(tmp_path))
    _write(tmp_path / "packages" / "__init__.py", "")
    _write(
        tmp_path / "packages" / "action_words" / "__init__.py",
        "from tuner_testkit.action_words import ActionCategory, ActionResult, ActionWord, register\n"
        "__all__ = ['ActionCategory', 'ActionResult', 'ActionWord', 'register']\n",
    )
    _write(tmp_path / "packages" / "action_words" / "db_seed" / "__init__.py", "")
    word_src = """
from pydantic import BaseModel, ConfigDict, Field
from tuner_testkit.action_words import ActionCategory, ActionResult, ActionWord, register

@register
class VisibleSeed(ActionWord):
    \"\"\"可见造数词，应出现在工作台目录。\"\"\"
    word_id = "db_seed.visible_seed"
    name = "可见造数"
    category = ActionCategory.DB_SEED
    example_params = {"n": 1}

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        n: int = Field(1, description="数量")

    def run(self, params):
        return ActionResult()

@register
class HiddenSeed(ActionWord):
    \"\"\"本地维护造数词，不进工作台目录。\"\"\"
    word_id = "db_seed.hidden_seed"
    name = "隐藏造数"
    category = ActionCategory.DB_SEED
    visibility = "local"
    example_params = {"n": 1}

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        n: int = Field(1, description="数量")

    def run(self, params):
        return ActionResult()
"""
    _write(tmp_path / "packages" / "action_words" / "db_seed" / "pair.py", word_src)
    payload = build_directory(tmp_path, include_kit_tools=False, refresh=True)
    ids = {row["word_id"] for row in payload["action_words"]}
    assert "db_seed.visible_seed" in ids
    assert "db_seed.hidden_seed" not in ids
    assert payload["counts_by_kind"]["db_seed"] == 1


def test_directory_discovers_nested_category_modules(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TUNER_ROOT", str(tmp_path))
    _write(tmp_path / "packages" / "__init__.py", "")
    _write(
        tmp_path / "packages" / "action_words" / "__init__.py",
        "from tuner_testkit.action_words import ActionCategory, ActionResult, ActionWord, register\n"
        "__all__ = ['ActionCategory', 'ActionResult', 'ActionWord', 'register']\n",
    )
    _write(tmp_path / "packages" / "action_words" / "db_seed" / "__init__.py", "")
    _write(tmp_path / "packages" / "action_words" / "db_seed" / "audit" / "__init__.py", "")
    _write(
        tmp_path / "packages" / "action_words" / "db_seed" / "audit" / "create_audit.py",
        "from pydantic import BaseModel, ConfigDict, Field\n"
        "from tuner_testkit.action_words import ActionCategory, ActionResult, ActionWord, register\n\n"
        "@register\n"
        "class NestedAudit(ActionWord):\n"
        "    \"\"\"嵌套子目录造数词，工作台必须能发现。\"\"\"\n"
        "    word_id = 'db_seed.nested_audit'\n"
        "    name = '嵌套审计造数'\n"
        "    category = ActionCategory.DB_SEED\n"
        "    example_params = {'n': 1}\n\n"
        "    class Params(BaseModel):\n"
        "        model_config = ConfigDict(extra='forbid')\n"
        "        n: int = Field(1, description='数量')\n\n"
        "    def run(self, params):\n"
        "        return ActionResult()\n",
    )
    stamp = entry_mtimes(tmp_path)
    assert any("create_audit.py" in path for path, _ in stamp)
    payload = build_directory(tmp_path, include_kit_tools=False, refresh=True)
    ids = {row["word_id"] for row in payload["action_words"]}
    assert "db_seed.nested_audit" in ids


def test_directory_dogfood_sample_seed() -> None:
    payload = build_directory(DOGFOOD, include_kit_tools=True, refresh=True)
    words = {row["word_id"]: row for row in payload["action_words"]}
    assert "db_seed.sample_seed" in words
    assert words["db_seed.sample_seed"]["example_params"]["prefix"] == "DEMO"
    assert payload["counts_by_kind"]["db_seed"] >= 1
    tools = {row["tool_id"] for row in payload["tools"]}
    assert "sample_tool" in tools
