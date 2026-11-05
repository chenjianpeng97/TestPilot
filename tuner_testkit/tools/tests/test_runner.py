from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.tools.runner import DestructiveNotConfirmed, RunRequest, run_tool

DOGFOOD = Path(__file__).resolve().parents[2] / "tests_fixtures" / "sample_workspace"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    from tuner_testkit.action_words.registry import reset_registry_for_tests
    from tuner_testkit.tools.manifest import reset_registry_for_tests as reset_tools

    reset_tools()
    reset_registry_for_tests()
    monkeypatch.setenv("TUNER_ROOT", str(DOGFOOD))


def test_run_sample_tool_writes_envelope() -> None:
    result = run_tool(
        RunRequest(tool_id="sample_tool", params={"count": 2, "label": "demo", "json": True}),
        root=DOGFOOD,
    )
    assert result.status == "succeeded"
    assert result.envelope and result.envelope["status"] == "succeeded"
    assert (Path(result.dir) / "manifest.json").is_file()
    assert (Path(result.dir) / "envelope.json").is_file()


def test_destructive_word_requires_confirm() -> None:
    with pytest.raises(DestructiveNotConfirmed):
        run_tool(RunRequest(tool_id="db_seed.sample_seed", params={"count": 1, "dry_run": True}), root=DOGFOOD)


def test_run_sample_seed_with_confirm() -> None:
    result = run_tool(
        RunRequest(tool_id="db_seed.sample_seed", params={"count": 2, "prefix": "T", "dry_run": True}, confirm=True),
        root=DOGFOOD,
    )
    assert result.status == "succeeded"
    assert result.exit_code == 0
