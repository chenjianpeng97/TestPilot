"""Scan ``.cursor/**`` AI components and render ``.cursor/REGISTRY.md``.

Deterministic (no LLM): parses lightweight front-matter from rules/skills/agents
and the ``.cursor/hooks.json`` event map, then renders a Markdown registry. Also
supports ``--check`` (used by CI / a sync hook) to detect drift.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from tuner_testkit.project import project_root

_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")

#: Explicit root (set by ``scaffold`` / callers that already know the workspace);
#: ``None`` → resolve via ``tuner_testkit.project.project_root()``.
_ROOT_OVERRIDE: pathlib.Path | None = None


def set_root(root: pathlib.Path | None) -> None:
    """Pin the workspace root for subsequent collect/render/write calls (``None`` resets)."""
    global _ROOT_OVERRIDE
    _ROOT_OVERRIDE = pathlib.Path(root).resolve() if root is not None else None


def _repo_root() -> pathlib.Path:
    if _ROOT_OVERRIDE is not None:
        return _ROOT_OVERRIDE
    return project_root()


def _cursor_dir() -> pathlib.Path:
    return _repo_root() / ".cursor"


def _registry_path() -> pathlib.Path:
    return _cursor_dir() / "REGISTRY.md"


@dataclass
class Component:
    kind: str            # rule | skill | agent | hook
    name: str
    trigger: str
    scope: str
    description: str
    version: str
    path: str
    group: str = "-"     # skills: knowledge | action | availability | internal
    extra: dict = field(default_factory=dict)


#: Public skill groups in display order (AGENTS.md §3); everything else is internal.
SKILL_GROUPS: tuple[tuple[str, str], ...] = (
    ("knowledge", "知识"),
    ("action", "动作"),
    ("availability", "可用性"),
)
_GROUP_ORDER = {name: i for i, (name, _) in enumerate(SKILL_GROUPS)} | {"internal": len(SKILL_GROUPS)}


def parse_front_matter(text: str) -> dict[str, str]:
    """Minimal YAML-ish front-matter parser (delimited by ``---``).

    Handles ``key: value`` and folded/literal blocks (``>-`` / ``|``). No third
    party deps; good enough for this repo's simple front-matter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    fm: dict[str, str] = {}
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = _KEY_RE.match(line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", ">-", "|", "|-"):
            block: list[str] = []
            i += 1
            while i < end and (lines[i].startswith(("  ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            sep = " " if val.startswith(">") else "\n"
            fm[key] = sep.join(b for b in block if b)
            continue
        fm[key] = val
        i += 1
    return fm


def _first_sentence(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    if not text:
        return "-"
    # Cut at a sentence end: CJK 。；, or ./; only when followed by whitespace
    # (so file extensions like ".feature" are not treated as sentence ends).
    m = re.search(r"[。；]|[.;](?=\s)", text)
    cut = text[: m.start()] if m else text
    if len(cut) > limit:
        cut = cut[: limit - 1] + "…"
    return cut or "-"


def collect_rules() -> list[Component]:
    out: list[Component] = []
    for path in sorted((_cursor_dir() / "rules").glob("*.mdc")):
        fm = parse_front_matter(path.read_text(encoding="utf-8"))
        always = str(fm.get("alwaysApply", "")).strip().lower() == "true"
        globs = fm.get("globs", "").strip()
        if always:
            trigger, scope = "always", "all files"
        elif globs:
            trigger, scope = "glob", globs
        else:
            trigger, scope = "manual", "-"
        out.append(Component(
            kind="rule",
            name=path.stem,
            trigger=trigger,
            scope=scope,
            description=(fm.get("description") or "").strip() or "-",
            version=fm.get("version", "-").strip() or "-",
            path=str(path.relative_to(_repo_root())).replace("\\", "/"),
        ))
    return out


def _collect_named(subdir: str, pattern: str, kind: str, trigger: str) -> list[Component]:
    out: list[Component] = []
    for path in sorted((_cursor_dir() / subdir).glob(pattern)):
        fm = parse_front_matter(path.read_text(encoding="utf-8"))
        out.append(Component(
            kind=kind,
            name=fm.get("name", path.parent.name if path.name == "SKILL.md" else path.stem),
            trigger=trigger,
            scope="-",
            description=(fm.get("description") or "").strip() or "-",
            version=fm.get("version", "-").strip() or "-",
            path=str(path.relative_to(_repo_root())).replace("\\", "/"),
            group=(fm.get("group") or "-").strip() or "-",
        ))
    return out


def collect_skills() -> list[Component]:
    skills = _collect_named("skills", "*/SKILL.md", "skill", "on-demand")
    return sorted(skills, key=lambda c: (_GROUP_ORDER.get(c.group, len(_GROUP_ORDER)), c.name))


def collect_agents() -> list[Component]:
    return _collect_named("agents", "*.md", "agent", "orchestration")


def collect_hooks() -> list[Component]:
    out: list[Component] = []
    hooks_json = _cursor_dir() / "hooks.json"
    if hooks_json.exists():
        try:
            data = json.loads(hooks_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        for event, entries in (data.get("hooks") or {}).items():
            for entry in entries:
                cmd = entry.get("command", entry.get("type", "prompt"))
                out.append(Component(
                    kind="hook",
                    name=f"{event}",
                    trigger=event,
                    scope=entry.get("matcher", "-") or "-",
                    description=f"command: {cmd}",
                    version=str(data.get("version", "-")),
                    path=".cursor/hooks.json",
                ))
    # git hooks (not agent hooks) — listed for completeness
    git_hooks = _repo_root() / "tools" / "git-hooks"
    for name, trigger, description in _GIT_HOOKS:
        if (git_hooks / name).exists():
            out.append(Component(
                kind="hook",
                name=name,
                trigger=trigger,
                scope="tools/git-hooks",
                description=description,
                version="-",
                path=f"tools/git-hooks/{name}",
            ))
    return out


_GIT_HOOKS: tuple[tuple[str, str, str], ...] = (
    ("pre-commit", "git commit (before message)", "Deterministic secret scan over staged files (secret_scan.py)"),
    ("commit-msg", "git commit", "Conventional Commits + layer-scope consistency check"),
    ("pre-push", "git push", "Warn when DNA drifted from release_manifest.json (non-blocking)"),
)


def _render_table(title: str, comps: list[Component], *, with_group: bool = False) -> str:
    lines = [f"## {title}", ""]
    if not comps:
        lines.append("_(暂无)_")
        lines.append("")
        return "\n".join(lines)
    if with_group:
        lines.append("| 名称 | 分组 | 版本 | 职责 | 文件 |")
        lines.append("| --- | --- | --- | --- | --- |")
    else:
        lines.append("| 名称 | 触发 | 作用范围 | 版本 | 职责 | 文件 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
    for c in comps:
        scope = c.scope.replace("|", "\\|")
        desc = _first_sentence(c.description).replace("|", "\\|")
        if with_group:
            lines.append(f"| `{c.name}` | {c.group} | {c.version} | {desc} | `{c.path}` |")
        else:
            lines.append(
                f"| `{c.name}` | {c.trigger} | {scope} | {c.version} | {desc} | `{c.path}` |"
            )
    lines.append("")
    return "\n".join(lines)


def _render_entries(skills: list[Component]) -> str:
    lines = ["## 对外入口（按三组）", ""]
    lines.append("用户直接点名或描述任务时，从这些 skill 进入；其余 skill 标 `internal`，由入口 skill 或 agent 调用。")
    lines.append("")
    for group, label in SKILL_GROUPS:
        names = [f"`{c.name}`" for c in skills if c.group == group]
        lines.append(f"- **{label}**（`{group}`）：{'、'.join(names) if names else '_(暂无)_'}")
    lines.append("")
    return "\n".join(lines)


def render() -> str:
    rules = collect_rules()
    skills = collect_skills()
    agents = collect_agents()
    hooks = collect_hooks()
    total = len(rules) + len(skills) + len(agents) + len(hooks)
    public = sum(1 for c in skills if c.group in _GROUP_ORDER and c.group != "internal")

    header = (
        "<!-- GENERATED by `python -m tuner_testkit.apps.index_ai`. Do not edit by hand. -->\n"
        "# REGISTRY — TestPilot AI 组件注册表\n"
        "\n"
        "> `.cursor/**` 下的 rule / skill / agent / hook 相当于测试平台后端 service 的\n"
        "> 业务规则与处理逻辑。本表由 `python -m tuner_testkit.apps.index_ai` 扫描各组件 front-matter\n"
        "> 确定性生成，供人类工程师一眼看全当前能力与版本。稳定世界观见 `AGENTS.md`；\n"
        "> 业务资产地图见 `INDEX.project.md`。\n"
        "\n"
        f"> 组件总数：**{total}**（rules {len(rules)} · skills {len(skills)}，其中对外入口 {public} · "
        f"agents {len(agents)} · hooks {len(hooks)}）\n"
    )
    body = "\n".join([
        "",
        _render_entries(skills),
        _render_table("Rules（约束/边界）", rules),
        _render_table("Skills（操作流程）", skills, with_group=True),
        _render_table("Agents（编排 playbook）", agents),
        _render_table("Hooks（事件驱动脚本）", hooks),
    ])
    return header + body


def write() -> pathlib.Path:
    _registry_path().write_text(render(), encoding="utf-8", newline="\n")
    return _registry_path()


def is_current() -> bool:
    if not _registry_path().exists():
        return False
    return _registry_path().read_text(encoding="utf-8") == render()


KIND_META: tuple[tuple[str, str, str], ...] = (
    ("rule", "规则", "约束/边界。能写成确定性约束的用 rule，不用 skill。"),
    ("skill", "技能", "操作流程。按需触发，教 LLM 怎么做一件事。"),
    ("agent", "编排", "Playbook。把多步 skill/rule 串成一条任务。"),
    ("hook", "钩子", "事件驱动脚本。能脚本化的不要交给 LLM。"),
)


def resolve_cursor_root(root: pathlib.Path) -> pathlib.Path:
    """Workspace with `.cursor/`, or parent."""
    workspace = pathlib.Path(root).resolve()
    if (workspace / ".cursor").is_dir():
        return workspace
    parent = workspace.parent
    if (parent / ".cursor").is_dir():
        return parent
    return workspace


def _component_row(comp: Component) -> dict[str, Any]:
    row = asdict(comp)
    row["id"] = f"{comp.kind}:{comp.name}"
    row["summary"] = _first_sentence(comp.description)
    row["href"] = f"/ai/{comp.kind}/{comp.name}"
    row["group_label"] = dict(SKILL_GROUPS).get(comp.group, "内部" if comp.group == "internal" else "")
    row["public"] = comp.kind == "skill" and comp.group in dict(SKILL_GROUPS)
    return row


def collect_catalog(root: pathlib.Path | None = None) -> dict[str, Any]:
    """Structured AI-component catalog for workbench / API (same scan as REGISTRY.md)."""
    workspace = pathlib.Path(root).resolve() if root is not None else _repo_root()
    dna = resolve_cursor_root(workspace)
    set_root(dna)
    try:
        by_kind = {
            "rule": collect_rules(),
            "skill": collect_skills(),
            "agent": collect_agents(),
            "hook": collect_hooks(),
        }
        groups: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for kind, title, blurb in KIND_META:
            comps = by_kind[kind]
            rows = [_component_row(c) for c in comps]
            counts[kind] = len(rows)
            groups.append({"kind": kind, "title": title, "blurb": blurb, "entries": rows})
            items.extend(rows)
        return {
            "workspace": str(workspace),
            "dna_root": str(dna),
            "counts": counts,
            "total": len(items),
            "groups": groups,
            "items": items,
        }
    finally:
        set_root(None)


def find_component(
    kind: str,
    name: str,
    root: pathlib.Path | None = None,
) -> dict[str, Any] | None:
    catalog = collect_catalog(root)
    for row in catalog["items"]:
        if row["kind"] == kind and row["name"] == name:
            return row
    return None


def read_component_intro(root: pathlib.Path, rel_path: str, *, limit: int = 1200) -> str:
    """Plain-text body after front-matter; never follow paths outside ``root``."""
    dna = resolve_cursor_root(pathlib.Path(root))
    path = (dna / rel_path).resolve()
    try:
        path.relative_to(dna)
    except ValueError:
        return ""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
    body = body.strip()
    if len(body) > limit:
        return body[: limit - 1] + "…"
    return body
