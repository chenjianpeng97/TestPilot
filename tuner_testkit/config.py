"""Runtime config helpers: named env profiles + API base URL.

Named environments live in gitignored ``config/env_local.py`` as ``ENVIRONMENTS``.
The active name is resolved (first hit wins) from:

1. ``TUNER_ENV`` (process / CI, does not change the repo pointer)
2. ``config/.active_env`` (repo-global pointer; gitignore)
3. ``env_local.ACTIVE_ENV`` (default before the first ``use``)
4. the sole key, if ``ENVIRONMENTS`` has exactly one entry

``python -m tuner_testkit.config show`` / ``use <name>`` (or ``tuner-config``)
switches the pointer; ``show --json`` prints the masked merged view and
``validate`` checks it (schema in ``tuner_testkit.config_schema``,
``docs/spec/config-syntax.md``). Callers still read the merged view on ``config.env``;
this module must not import ``config.env`` at module level (``config.env``
calls into here while it is still loading).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

TUNER_ENV_VAR = "TUNER_ENV"
_PROD_LIKE = frozenset({"prd", "prod", "production"})
_UNSET: Any = object()


class EnvProfileError(RuntimeError):
    """Named-environment catalog is missing, empty, or the active name is invalid."""


def repo_root() -> Path:
    from tuner_testkit.project import project_root

    return project_root()


def load_project_env() -> Any:
    """Import the SUT ``config.env`` module (always from the project tree)."""
    from tuner_testkit.project import ensure_project_on_path

    ensure_project_on_path()
    from config import env as env_config

    return env_config


def active_env_path() -> Path:
    return repo_root() / "config" / ".active_env"


def read_active_env_file(path: Path | None = None) -> str | None:
    p = path or active_env_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    for line in raw.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            return text
    return None


def write_active_env(name: str, path: Path | None = None) -> Path:
    chosen = name.strip()
    if not chosen:
        raise EnvProfileError("环境名不能为空")
    p = path or active_env_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(chosen + "\n", encoding="utf-8")
    return p


def environments_of(source: Any) -> dict[str, Any] | None:
    extra = getattr(source, "ENVIRONMENTS", None)
    if isinstance(extra, dict) and extra:
        return extra
    return None


def resolve_active_name(
    *,
    available: Sequence[str],
    module_default: str | None = None,
    environ: Mapping[str, str] | None = None,
    active_file_text: str | None = None,
) -> str:
    names = [str(n) for n in available if str(n).strip()]
    if not names:
        raise EnvProfileError("ENVIRONMENTS 为空")
    known = set(names)
    env_map = os.environ if environ is None else environ

    def _take(raw: str | None) -> str:
        return (raw or "").strip()

    candidates = (
        _take(env_map.get(TUNER_ENV_VAR) if hasattr(env_map, "get") else None),
        _take(active_file_text),
        _take(module_default),
    )
    for chosen in candidates:
        if not chosen:
            continue
        if chosen not in known:
            raise EnvProfileError(
                f"未知环境 {chosen!r}；可用: {sorted(known)}"
            )
        return chosen
    if len(names) == 1:
        return names[0]
    raise EnvProfileError(
        "未选择环境：设置 TUNER_ENV、执行 python -m tuner_testkit.config use <name>，"
        f"或在 env_local.py 设置 ACTIVE_ENV。可用: {sorted(known)}"
    )


def _merge_databases_into(target_db: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for alias, cfg in overlay.items():
        if not isinstance(cfg, dict):
            continue
        if alias in target_db:
            target_db[alias] = {**target_db[alias], **cfg}
        else:
            target_db[alias] = dict(cfg)


def apply_profile(target: Any, profile: Mapping[str, Any]) -> None:
    """Merge one environment profile (any section of ``config_schema.ALL_SECTIONS``) onto ``target``."""
    from tuner_testkit.config_schema import apply_sections

    apply_sections(target, profile)


def apply_module(target: Any, mod: Any) -> None:
    """Merge a flat overlay module (``env_overlay.py`` / flat ``env_local.py``) onto ``target``."""
    from tuner_testkit.config_schema import apply_sections, module_sections

    apply_sections(target, module_sections(mod))


def apply_selected_environment(
    target: Any,
    source: Any,
    *,
    environ: Mapping[str, str] | None = None,
    active_file_path: Path | None = None,
    active_file_text: Any = _UNSET,
) -> str | None:
    """Merge the active named profile from ``source`` onto ``target``.

    Returns the applied name, or ``None`` when ``source`` has no non-empty
    ``ENVIRONMENTS`` (caller should fall back to a flat overlay).
    """

    envs = environments_of(source)
    if envs is None:
        return None
    if active_file_text is _UNSET:
        file_text = read_active_env_file(active_file_path)
    else:
        file_text = active_file_text  # type: ignore[assignment]
    default = getattr(source, "ACTIVE_ENV", None)
    name = resolve_active_name(
        available=list(envs),
        module_default=str(default) if default else None,
        environ=environ,
        active_file_text=file_text,
    )
    profile = envs[name]
    if not isinstance(profile, dict):
        raise EnvProfileError(f"环境 {name!r} 必须是 dict，实际为 {type(profile).__name__}")
    from tuner_testkit.config_schema import WORKSPACE_SECTIONS, apply_sections, module_sections

    # Machine-level CHANNELS / PORTS / KNOWLEDGE at the top of env_local apply to every environment.
    apply_sections(target, module_sections(source), sections=WORKSPACE_SECTIONS)
    apply_profile(target, profile)
    target.ACTIVE_ENV = name
    return name


def load_env_local() -> Any | None:
    from tuner_testkit.project import ensure_project_on_path

    ensure_project_on_path()
    try:
        return __import__("config.env_local", fromlist=["*"])
    except ImportError:
        return None


def get_active_env_name() -> str | None:
    env_config = load_project_env()
    name = getattr(env_config, "ACTIVE_ENV", None)
    return str(name) if name else None


def get_test_base_url() -> str:
    """Base URL for API execution (host only).

    APIModel assets must store only path (no host). The host is injected at runtime.
    """

    base_url = (os.getenv("TEST_BASE_URL") or "").strip()
    if not base_url:
        env_config = load_project_env()
        base_url = str(getattr(env_config, "TEST_BASE_URL", "") or "").strip()
    if not base_url:
        # Keep a safe default for local development; tests should override as needed.
        return "http://localhost"
    return base_url.rstrip("/")


def get_ui_base_url() -> str:
    """Base URL for UI execution (host only).

    PageModel assets store only ``url_path`` (no host); the host is injected at
    runtime by ``tuner_testkit.page_test.driver.PageDriver``. Falls back to the API
    host when the SUT serves UI and API from the same origin.
    """

    base_url = (os.getenv("TEST_UI_BASE_URL") or "").strip()
    if not base_url:
        env_config = load_project_env()
        base_url = str(getattr(env_config, "TEST_UI_BASE_URL", "") or "").strip()
    if not base_url:
        return get_test_base_url()
    return base_url.rstrip("/")


def _print_profile_summary(name: str, profile: Mapping[str, Any]) -> None:
    url = profile.get("TEST_BASE_URL") or ""
    ui_url = profile.get("TEST_UI_BASE_URL") or ""
    databases = profile.get("DATABASES") if isinstance(profile.get("DATABASES"), dict) else {}
    aliases = ", ".join(sorted(str(k) for k in databases)) or "(none)"
    print(f"active: {name}")
    print(f"TEST_UI_BASE_URL: {ui_url or '(same as TEST_BASE_URL)'}")
    print(f"TEST_BASE_URL: {url}")
    print(f"DATABASES aliases: {aliases}")


def describe_project_config() -> dict[str, Any]:
    """Masked view of the merged project config (see ``config_schema.describe``)."""
    from tuner_testkit.config_schema import describe

    local = load_env_local()
    envs = environments_of(local) if local is not None else None
    mode = "none" if local is None else ("environments" if envs else "flat")
    try:
        env = load_project_env()
    except EnvProfileError as exc:
        return {"mode": mode, "env_local": local is not None, "error": str(exc), "available": sorted(envs or [])}
    payload = describe(env, available=list(envs or []), mode=mode, env_local=local is not None)
    payload["root"] = str(repo_root())
    return payload


def _cmd_show(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        import json

        payload = describe_project_config()
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
        return 1 if payload.get("error") else 0
    local = load_env_local()
    if local is None:
        print(
            "no config/env_local.py — copy config/env_local.py.example and fill values",
            file=sys.stderr,
        )
        return 1
    envs = environments_of(local)
    if envs is None:
        print("mode: flat (no ENVIRONMENTS)")
        url = getattr(local, "TEST_BASE_URL", "") or ""
        print(f"TEST_BASE_URL: {url}")
        aliases = getattr(local, "DATABASES", None) or {}
        if isinstance(aliases, dict) and aliases:
            print(f"DATABASES aliases: {', '.join(sorted(aliases))}")
        return 0
    try:
        active = resolve_active_name(
            available=list(envs),
            module_default=str(getattr(local, "ACTIVE_ENV", None) or "") or None,
            active_file_text=read_active_env_file(),
        )
    except EnvProfileError as exc:
        print(str(exc), file=sys.stderr)
        print("available: " + ", ".join(sorted(envs)))
        return 1
    print("available:")
    for name in sorted(envs):
        marker = "*" if name == active else " "
        profile = envs[name] if isinstance(envs[name], dict) else {}
        url = profile.get("TEST_BASE_URL") or ""
        print(f"  {marker} {name}  {url}")
    profile = envs[active] if isinstance(envs[active], dict) else {}
    _print_profile_summary(active, profile)
    return 0


def validate_project_config(root: Path | None = None) -> dict[str, Any]:
    """Deterministic config checks; ``ok`` is False when any finding is an error."""
    import subprocess

    from tuner_testkit.config_schema import Finding, committed_secret_literals, find_placeholders, validate_sections

    base = root or repo_root()
    findings: list[Finding] = []
    local_path = base / "config" / "env_local.py"
    if not local_path.is_file():
        findings.append(
            Finding("warn", "env_local.missing", "没有 config/env_local.py（本机密钥与真实地址）", "maintain-config")
        )
    else:
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "config/env_local.py"],
                cwd=str(base),
                capture_output=True,
                timeout=10,
                check=False,
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            tracked = False
        if tracked:
            findings.append(
                Finding("error", "env_local.tracked", "config/env_local.py 被 git 跟踪；立刻 git rm --cached 并确认 .gitignore", "")
            )
    for name in ("env.py", "env_overlay.py"):
        path = base / "config" / name
        if path.is_file():
            for hit in committed_secret_literals(path):
                findings.append(
                    Finding("error", "committed.secret", f"提交的配置里有疑似密钥：{hit}", "移到 config/env_local.py")
                )
    try:
        env = load_project_env()
    except EnvProfileError as exc:
        findings.append(Finding("error", "env.active", str(exc), "tuner-config use <name>"))
        env = None
    if env is not None:
        try:
            from tuner_testkit.tools import export_tools

            tools = export_tools(base, include_kit=False)
        except Exception as exc:  # noqa: BLE001 -- a broken app must not hide config findings
            findings.append(Finding("warn", "tools.discover", f"apps/*/tool.py 导入失败：{type(exc).__name__}: {exc}", ""))
            tools = None
        findings.extend(validate_sections(env, root=base, tools=tools))
        if not str(getattr(env, "TEST_BASE_URL", "") or "").strip():
            findings.append(Finding("warn", "env.api_url", "TEST_BASE_URL 为空", "maintain-config"))
        if not str(getattr(env, "TEST_UI_BASE_URL", "") or "").strip():
            findings.append(Finding("info", "env.ui_url", "TEST_UI_BASE_URL 为空，UI 沿用 TEST_BASE_URL", "maintain-config"))
        active_profile = {
            "DATABASES": getattr(env, "DATABASES", None) or {},
            "OPS": getattr(env, "OPS", None) or {},
        }
        for dotted in find_placeholders(active_profile):
            findings.append(Finding("warn", "env.placeholder", f"仍是模板占位：{dotted}", "maintain-config"))
    rows = [f.to_dict() for f in findings]
    return {
        "root": str(base),
        "ok": not any(f.severity == "error" for f in findings),
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warnings": sum(1 for f in findings if f.severity == "warn"),
        "findings": rows,
    }


def _cmd_validate(args: argparse.Namespace) -> int:
    import json

    result = validate_project_config()
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        for row in result["findings"]:
            fix = f"  -> {row['fix']}" if row["fix"] else ""
            print(f"[{row['severity']}] {row['code']}: {row['message']}{fix}")
        print(f"errors={result['errors']} warnings={result['warnings']}")
    return 0 if result["ok"] else 1


def _cmd_use(args: argparse.Namespace) -> int:
    local = load_env_local()
    if local is None:
        print(
            "no config/env_local.py — copy config/env_local.py.example and fill values",
            file=sys.stderr,
        )
        return 1
    envs = environments_of(local)
    if envs is None:
        print(
            "env_local.py 没有 ENVIRONMENTS；无法按名字切换。"
            "请把各套环境收进 ENVIRONMENTS 后再 use。",
            file=sys.stderr,
        )
        return 1
    name = (args.name or "").strip()
    if name not in envs:
        print(f"未知环境 {name!r}；可用: {sorted(envs)}", file=sys.stderr)
        return 1
    if name.lower() in _PROD_LIKE:
        print(f"warning: activating {name!r} (production-like)", file=sys.stderr)
    path = write_active_env(name)
    profile = envs[name] if isinstance(envs[name], dict) else {}
    _print_profile_summary(name, profile)
    print(f"wrote {path} (new processes will pick this up)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="python -m tuner_testkit.config",
        description="List or switch the active local named environment (env_local ENVIRONMENTS).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_show = sub.add_parser("show", help="list named environments and the active one")
    p_show.add_argument(
        "--json", action="store_true", help="print the merged config (env, URLs, channels, ports, knowledge) with secrets masked"
    )
    p_show.set_defaults(func=_cmd_show)

    p_use = sub.add_parser("use", help="write config/.active_env (repo-global switch)")
    p_use.add_argument("name", help="environment name defined in env_local.ENVIRONMENTS")
    p_use.set_defaults(func=_cmd_use)

    p_validate = sub.add_parser("validate", help="check config schema, placeholders, committed secrets, port bindings")
    p_validate.add_argument("--json", action="store_true", help="print findings as JSON")
    p_validate.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    if not args.cmd:
        return _cmd_show(args)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
