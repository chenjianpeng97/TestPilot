"""Run a catalog tool or action word and persist ``artifacts/runs/<run_id>/``.

Used by ``tuner-workspace run`` and the local workbench. Destructive tools
(``spec.destructive`` or action-word categories ``db_seed`` / ``api_request`` /
``ui_action``) require ``confirm=True``; the workbench maps that to a checkbox.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tuner_testkit.artifacts import default_producer, start_run
from tuner_testkit.logging import log_error, log_info
from tuner_testkit.tools.manifest import ToolSpec, build_argv, get_tool, validate_params

DESTRUCTIVE_WORD_CATEGORIES = frozenset({"db_seed", "api_request", "ui_action"})


class DestructiveNotConfirmed(ValueError):
    """Raised when a destructive tool is invoked without ``confirm``."""


@dataclass
class RunRequest:
    tool_id: str
    params: dict[str, Any] = field(default_factory=dict)
    confirm: bool = False
    run_id: str | None = None
    timeout: int | None = None


@dataclass
class RunResult:
    run_id: str
    tool_id: str
    status: str
    exit_code: int
    dir: str
    argv: list[str]
    envelope: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tool_id": self.tool_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "dir": self.dir,
            "argv": list(self.argv),
            "envelope": self.envelope,
            "error": self.error,
        }


def run_tool(request: RunRequest, *, root: Path | None = None) -> RunResult:
    """Resolve *request.tool_id*, spawn the process, write a run manifest."""
    from tuner_testkit.project import ensure_project_on_path, project_root

    repo = Path(root).resolve() if root is not None else project_root()
    ensure_project_on_path(repo)
    os.environ["TUNER_ROOT"] = str(repo)

    kind, spec_or_word = _resolve(request.tool_id, repo)
    destructive, timeout, argv = _plan(kind, spec_or_word, request.params, repo)
    if destructive and not request.confirm:
        raise DestructiveNotConfirmed(
            f"{request.tool_id} is destructive; pass --confirm (or tick the workbench checkbox)"
        )

    manifest = start_run(
        "run",
        request.tool_id,
        root=repo,
        run_id=request.run_id,
        producer=default_producer(repo, tool_id=request.tool_id, argv=argv),
        params=request.params,
    )
    assert manifest.dir is not None
    stdout_path = manifest.dir / "stdout.log"
    stderr_path = manifest.dir / "stderr.log"
    limit = request.timeout if request.timeout is not None else timeout
    log_info("workspace run start", tool_id=request.tool_id, run_id=manifest.run_id, argv=argv)

    env = os.environ.copy()
    env["TUNER_ROOT"] = str(repo)
    env["PYTHONUTF8"] = "1"
    try:
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            completed = subprocess.run(
                argv,
                cwd=str(repo),
                env=env,
                stdout=out,
                stderr=err,
                timeout=limit or None,
                check=False,
            )
        exit_code = int(completed.returncode)
        status = "succeeded" if exit_code == 0 else "failed"
        error = None
    except subprocess.TimeoutExpired:
        exit_code = 124
        status = "failed"
        error = f"timed out after {limit}s"
        stderr_path.write_text((stderr_path.read_text(encoding="utf-8") if stderr_path.is_file() else "") + f"\n{error}\n", encoding="utf-8")
        log_error("workspace run timeout", tool_id=request.tool_id, run_id=manifest.run_id)
    except OSError as exc:
        exit_code = 127
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        stderr_path.write_text(error + "\n", encoding="utf-8")

    envelope = _extract_envelope(stdout_path)
    if envelope is not None:
        (manifest.dir / "envelope.json").write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    manifest.finish(status, exit_code=exit_code, summary={"error": error} if error else {})
    return RunResult(
        run_id=manifest.run_id,
        tool_id=request.tool_id,
        status=status,
        exit_code=exit_code,
        dir=str(manifest.dir),
        argv=argv,
        envelope=envelope,
        error=error,
    )


def _resolve(tool_id: str, root: Path) -> tuple[str, ToolSpec | dict[str, Any]]:
    try:
        return "tool", get_tool(tool_id, root)
    except KeyError:
        pass
    word = _load_word(tool_id, root)
    if word is None:
        raise KeyError(f"unknown tool or action word {tool_id!r}")
    return "word", word


def _load_word(word_id: str, root: Path) -> dict[str, Any] | None:
    from tuner_testkit.action_words.registry import get as get_word, reset_registry_for_tests

    root = root.resolve()
    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
    # Evict so ``@register`` re-runs after ``reset_registry_for_tests``.
    for name in [m for m in sys.modules if m == "packages" or m.startswith("packages.")]:
        sys.modules.pop(name, None)
    reset_registry_for_tests()
    try:
        cls = get_word(word_id)
    except KeyError:
        return None
    row = cls.describe()
    row["destructive"] = str(cls.category) in DESTRUCTIVE_WORD_CATEGORIES
    row["timeout"] = 180
    return row


def _plan(
    kind: str,
    spec: ToolSpec | dict[str, Any],
    params: dict[str, Any],
    root: Path,
) -> tuple[bool, int, list[str]]:
    if kind == "tool":
        assert isinstance(spec, ToolSpec)
        errors = validate_params(spec.params_schema, params)
        if errors:
            raise ValueError("; ".join(errors))
        argv = build_argv(spec, params)
        if argv and argv[0] == "python":
            argv = [sys.executable, *argv[1:]]
        return spec.destructive, spec.timeout, argv

    assert isinstance(spec, dict)
    word_id = spec["word_id"]
    payload = json.dumps(params, ensure_ascii=False)
    argv = [sys.executable, "-m", "tuner_testkit.action_words", "run", word_id, "--params", payload]
    return bool(spec.get("destructive")), int(spec.get("timeout") or 180), argv


def _extract_envelope(stdout_path: Path) -> dict[str, Any] | None:
    if not stdout_path.is_file():
        return None
    text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    # Prefer the last JSON object on stdout (tools may log then print --json).
    for chunk in reversed(text.splitlines()):
        chunk = chunk.strip()
        if chunk.startswith("{") and chunk.endswith("}"):
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "status" in data:
                return data
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "status" in data else None
