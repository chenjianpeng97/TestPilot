"""Scaffold a new TestPilot workspace: layered skeleton + DNA overlay + kit dependency."""
from __future__ import annotations

import pathlib
import re
import shutil
import textwrap

SKELETON_DIRS: tuple[str, ...] = (
    # knowledge layer — evolves with the SUT (docs/spec/knowledge-syntax.md)
    "knowledge/ddl",
    "knowledge/raw",
    "knowledge/wiki/domain-notes",
    "knowledge/wiki/usecases",
    "knowledge/wiki/explore",
    "knowledge/wiki/design",
    "knowledge/requirements",
    "knowledge/defects",
    # asset layer (Markdown) — evolves with the test work
    "assets/sql",
    "assets/testdesign",
    "assets/testcases",
    "assets/testsheet",
    "assets/testreport",
    "work/tasks",
    "packages/action_words/db_seed",
    "packages/action_words/db_assert",
    "packages/action_words/api_request",
    "packages/action_words/api_assert",
    "packages/action_words/ui_action",
    "packages/action_words/ui_assert",
    "packages/api_objects",
    "packages/page_objects",
    "apps",
    "data/mocks",
    "tests/features/ui_steps",
    "tests/features/api_steps",
    "tests/pytest",
    "docs/spec",
    "config",
    "logs",
    "artifacts",
    "artifacts/evidence",
    "artifacts/catalogs",
    "artifacts/inbox",
    "artifacts/runs",
    "artifacts/reports",
)

# Thin SUT files copied from this template (not the full kit runtime).
_STUB_FILES: tuple[str, ...] = (
    "config/env.py",
    "config/env_local.py.example",
    "knowledge/wiki/index.md",
    "knowledge/wiki/log.md",
    "packages/__init__.py",
    "packages/page_objects/__init__.py",
    "packages/page_objects/session.py",
    "packages/api_objects/__init__.py",
    "packages/api_objects/auth.py",
    "packages/api_objects/registry.py",
    "packages/api_objects/recording/__init__.py",
    "packages/action_words/__init__.py",
    "packages/action_words/models.py",
    "packages/action_words/_internal/__init__.py",
    "packages/action_words/_internal/params.py",
    "apps/__init__.py",
    "behave.ini",
    "data/sut-accounts.example.yaml",
    "INDEX.project.md",
    "workbench.cmd",
    "workbench.sh",
    "tests/features/api_environment.py",
    "tests/features/ui_environment.py",
    "tests/features/api_steps/given.py",
    "tests/features/api_steps/when.py",
    "tests/features/api_steps/then.py",
    "tests/features/ui_steps/given.py",
    "tests/features/ui_steps/when.py",
    "tests/features/ui_steps/then.py",
    "tests/pytest/conftest.py",
)

# Stub files whose on-disk name differs from the bundled name (dotfiles are dropped by sdist).
_RENAMED_STUBS: dict[str, str] = {
    "gitignore": ".gitignore",
}


def _stub_root() -> pathlib.Path | None:
    """Directory that contains thin SUT stub files (``config/env.py``, …).

    ``init_repo/stubs/`` is the single source of truth for both editable and
    wheel installs: the platform repo itself is **not** a workspace (its
    workspace example lives in ``dogfood/``), so scaffold never copies from
    the repo root. ``project_root()`` must not be used: scaffold is how a
    project is created.
    """
    bundled = pathlib.Path(__file__).resolve().parent / "stubs"
    if (bundled / "config" / "env.py").is_file():
        return bundled
    return None


# PEP 503 / 426 name: start and end with an alphanumeric; dots, underscores, hyphens inside.
_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def project_name_from_directory(directory_name: str) -> str:
    """Turn a generated folder name into a ``pyproject.toml`` project name.

    ``Acme`` becomes ``acme``. Characters outside the project-name
    alphabet become hyphens. Pass ``--name`` when the folder name cannot
    produce a valid name.
    """
    slug = directory_name.strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    slug = re.sub(r"[-_.]{2,}", "-", slug).strip("-._")
    if not slug:
        raise ValueError(
            f"cannot derive a project name from directory {directory_name!r}; pass --name"
        )
    return normalize_project_name(slug)


def normalize_project_name(raw: str) -> str:
    """Accept an explicit ``--name`` or raise ``ValueError``."""
    name = raw.strip()
    if not _PROJECT_NAME_RE.fullmatch(name):
        raise ValueError(
            "invalid project name "
            f"{raw!r}: use letters, digits, '.', '_' or '-', "
            "and do not start or end with punctuation"
        )
    return name


def _copy_file(src: pathlib.Path, dst: pathlib.Path, *, overwrite: bool) -> bool:
    if dst.exists() and not overwrite:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _write_pyproject(
    target: pathlib.Path,
    *,
    overwrite: bool,
    project_name: str,
    kit_version: str,
) -> bool:
    dest = target / "pyproject.toml"
    if dest.exists() and not overwrite:
        return False
    dest.write_text(
        textwrap.dedent(
            f"""\
            [project]
            name = "{project_name}"
            version = "0.1.0"
            description = "TestPilot workspace created from tuner-testkit"
            requires-python = ">=3.12,<3.14"
            dependencies = [
                "tuner-testkit[db,api]>={kit_version}",
            ]

            [project.optional-dependencies]
            web-ui = ["tuner-testkit[web-ui]"]
            recorder = ["tuner-testkit[recorder]"]
            mock = ["tuner-testkit[mock]"]
            report = ["tuner-testkit[report]"]
            test = ["pytest>=9.0.3"]
            bdd = ["behave>=1.2.6", "playwright>=1.54.0"]
            dev = ["pytest>=9.0.3", "behave>=1.2.6", "playwright>=1.54.0"]

            [build-system]
            requires = ["setuptools>=75", "wheel"]
            build-backend = "setuptools.build_meta"

            [tool.setuptools.packages.find]
            include = ["packages*", "config*", "apps*"]

            [tool.tuner-testkit]
            page_objects = "packages/page_objects"
            api_objects = "packages/api_objects"
            mocks = "data/mocks"
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    return True


def scaffold(
    target: pathlib.Path,
    *,
    with_ai: bool = True,
    overwrite: bool = False,
    project_name: str | None = None,
) -> list[str]:
    """Create a SUT test repo at ``target``.

    The directory's own name is the generated folder name. ``project_name``
    (CLI ``--name``) is the ``[project] name`` written into ``pyproject.toml``.
    When omitted, that name is derived from the folder name.
    """
    actions: list[str] = []
    target = target.resolve()
    explicit = (project_name or "").strip()
    resolved_name = (
        normalize_project_name(explicit)
        if explicit
        else project_name_from_directory(target.name)
    )
    from tuner_testkit import __version__

    target.mkdir(parents=True, exist_ok=True)
    src_root = _stub_root()

    for rel in SKELETON_DIRS:
        d = target / rel
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not any(d.iterdir()) and not keep.exists():
            keep.write_text("", encoding="utf-8")
        actions.append(f"dir  {rel}")

    if _write_pyproject(
        target,
        overwrite=overwrite,
        project_name=resolved_name,
        kit_version=__version__,
    ):
        actions.append(f"write pyproject.toml ({resolved_name})")
    else:
        actions.append("skip pyproject.toml (exists)")

    py_ver = target / ".python-version"
    if py_ver.exists() and not overwrite:
        actions.append("skip .python-version (exists)")
    else:
        py_ver.write_text("3.12\n", encoding="utf-8", newline="\n")
        actions.append("write .python-version")

    if src_root is None:
        actions.append("skip stubs (not bundled in this install)")
    else:
        for rel in _STUB_FILES:
            src = src_root / rel
            if not src.exists():
                continue
            if _copy_file(src, target / rel, overwrite=overwrite):
                actions.append(f"copy {rel}")
            else:
                actions.append(f"skip {rel} (exists)")
        for bundled_name, dest_rel in _RENAMED_STUBS.items():
            src = src_root / bundled_name
            if not src.exists():
                continue
            if _copy_file(src, target / dest_rel, overwrite=overwrite):
                actions.append(f"copy {dest_rel}")
            else:
                actions.append(f"skip {dest_rel} (exists)")

    if with_ai:
        from types import SimpleNamespace

        from tuner_testkit.apps.dna.cli import cmd_sync

        code = cmd_sync(
            SimpleNamespace(target=str(target), overwrite=overwrite),
        )
        actions.append(f"dna sync (exit {code})")
        actions.append(_write_registry(target))

    return actions


def _write_registry(target: pathlib.Path) -> str:
    """Generate ``.cursor/REGISTRY.md`` in the new workspace (deterministic, via index_ai)."""
    from tuner_testkit.apps.index_ai import registry

    registry.set_root(target)
    try:
        path = registry.write()
        return f"write {path.relative_to(target).as_posix()}"
    except Exception as exc:  # noqa: BLE001 -- scaffold must not fail on registry rendering
        return f"skip .cursor/REGISTRY.md ({type(exc).__name__}: {exc})"
    finally:
        registry.set_root(None)
