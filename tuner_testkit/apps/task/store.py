"""Git-tracked work tasks and gitignored human questions.

Spec: ``docs/spec/work-task.md``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tuner_testkit.catalog.front_matter import dump_front_matter, parse_front_matter, replace_front_matter
from tuner_testkit.project import project_root
from tuner_testkit.workspace.meta import resolve_author, stamp_file

TASK_TYPES = ("explore", "test-design", "test-execution")
TASK_STATUSES = ("open", "in_progress", "blocked", "done")

LOG_SOURCE_TOPIC = "sut-log-source"
LOG_SOURCE_OPTIONS: list[dict[str, str]] = [
    {"id": "ssh-dir", "label": "SSH 到指定目录读日志文件"},
    {"id": "log-api", "label": "调用已有日志接口"},
    {"id": "rancher-api", "label": "用 Rancher API 拉 Pod 日志"},
    {"id": "skip", "label": "本轮不做日志通道"},
]

_SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|token|secret|cookie|authorization|api[_-]?key)\b\s*[:=]\s*\S+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")


def assert_no_secret(text: str) -> None:
    """Reject notes that embed a credential instead of pointing at local config."""
    if not text:
        return
    if _SECRET_ASSIGN.search(text) or _BEARER.search(text):
        raise ValueError(
            "note must not contain secrets; point at config/env_local.py, an env var, or account_id"
        )


def tasks_dir(root: Path) -> Path:
    return root / "work" / "tasks"


def questions_dir(root: Path) -> Path:
    return root / "artifacts" / "inbox" / "questions"


def archived_questions_dir(root: Path) -> Path:
    return root / "artifacts" / "inbox" / "archived-question"


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _next_question_id(repo: Path) -> str:
    """Next Q-id for today, counting both the open inbox and the archive."""
    day = _utc_day()
    pat = re.compile(rf"^Q-{day}-(\d+)$")
    nums: list[int] = []
    for directory in (questions_dir(repo), archived_questions_dir(repo)):
        if not directory.is_dir():
            continue
        nums.extend(int(m.group(1)) for path in directory.glob(f"Q-{day}-*.md") if (m := pat.match(path.stem)))
    questions_dir(repo).mkdir(parents=True, exist_ok=True)
    return f"Q-{day}-{max(nums, default=0) + 1:03d}"


def _next_seq(directory: Path, prefix: str, day: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    pat = re.compile(rf"^{re.escape(prefix)}-{day}-(\d+)$")
    nums = [int(m.group(1)) for path in directory.glob(f"{prefix}-{day}-*.md") if (m := pat.match(path.stem))]
    return f"{prefix}-{day}-{max(nums, default=0) + 1:03d}"


def _read(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    return parse_front_matter(text), text


def _write(path: Path, meta: dict[str, Any], text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(replace_front_matter(text, meta), encoding="utf-8", newline="\n")


def _rel(root: Path, raw: str) -> Path:
    rel = raw.replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("../") or "/../" in f"/{rel}":
        raise ValueError(f"path escapes the repo: {raw}")
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes the repo: {raw}")
    return path


def _task_path(root: Path, task_id: str) -> Path:
    path = tasks_dir(root) / f"{task_id}.md"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _question_path(root: Path, question_id: str) -> Path:
    path = questions_dir(root) / f"{question_id}.md"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def create_task(
    *,
    task_type: str,
    title: str,
    root: Path | None = None,
    objective: str = "",
    scope: list[str] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    design: str = "",
    author: str | None = None,
) -> dict[str, Any]:
    if task_type not in TASK_TYPES:
        raise ValueError(f"type must be one of {TASK_TYPES}")
    if task_type == "test-execution" and not design.strip():
        raise ValueError("test-execution requires --design pointing at a testdesign file")
    repo = Path(root) if root is not None else project_root()
    if design:
        design_path = _rel(repo, design)
        if task_type == "test-execution" and not design_path.is_file():
            raise ValueError(f"design file does not exist: {design}")
    task_id = _next_seq(tasks_dir(repo), "TASK", _utc_day())
    meta: dict[str, Any] = {
        "kind": "task",
        "id": task_id,
        "title": title.strip(),
        "type": task_type,
        "status": "open",
        "author": author if author is not None else (resolve_author(repo) or ""),
        "created": _today(),
        "updated": _today(),
        "objective": " ".join(objective.split()),
        "scope": list(scope or []),
        "inputs": list(inputs or []),
        "outputs": list(outputs or []),
        "evidence": [],
        "questions": [],
    }
    if design.strip():
        meta["design"] = design.replace("\\", "/")
    body = (
        f"# {title.strip()}\n\n"
        "## Objective\n\n"
        f"{meta['objective'] or '（未写）'}\n\n"
        "## Decisions\n"
    )
    path = tasks_dir(repo) / f"{task_id}.md"
    path.write_text(dump_front_matter(meta) + body, encoding="utf-8", newline="\n")
    stamp_file(repo, path, kind="task", author=meta["author"] or None)
    return {"id": task_id, "path": path.relative_to(repo).as_posix(), "status": "open", "type": task_type}


def _summary(meta: dict[str, Any], path: Path, root: Path) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "title": meta.get("title"),
        "type": meta.get("type"),
        "status": meta.get("status"),
        "design": meta.get("design"),
        "path": path.relative_to(root).as_posix(),
        "questions": _as_list(meta.get("questions")),
        "evidence": _as_list(meta.get("evidence")),
        "outputs": _as_list(meta.get("outputs")),
    }


def list_tasks(*, root: Path | None = None) -> list[dict[str, Any]]:
    repo = Path(root) if root is not None else project_root()
    directory = tasks_dir(repo)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("TASK-*.md")):
        meta, _ = _read(path)
        rows.append(_summary(meta, path, repo))
    return rows


def show_task(task_id: str, *, root: Path | None = None) -> dict[str, Any]:
    repo = Path(root) if root is not None else project_root()
    path = _task_path(repo, task_id)
    meta, _ = _read(path)
    row = _summary(meta, path, repo)
    row["objective"] = meta.get("objective") or ""
    row["scope"] = _as_list(meta.get("scope"))
    row["inputs"] = _as_list(meta.get("inputs"))
    return row


def set_status(task_id: str, status: str, *, root: Path | None = None) -> dict[str, Any]:
    if status not in TASK_STATUSES:
        raise ValueError(f"status must be one of {TASK_STATUSES}")
    repo = Path(root) if root is not None else project_root()
    path = _task_path(repo, task_id)
    meta, text = _read(path)
    current = str(meta.get("status") or "open")
    if current == "done":
        raise ValueError(f"{task_id} is done")
    if status == "in_progress" and current == "blocked":
        raise ValueError(f"{task_id} is blocked; answer open questions first")
    meta["status"] = status
    meta["updated"] = _today()
    _write(path, meta, text)
    return show_task(task_id, root=repo)


def _open_blocking(repo: Path, question_ids: list[Any]) -> list[str]:
    open_ids: list[str] = []
    for qid in question_ids:
        path = questions_dir(repo) / f"{qid}.md"
        if not path.is_file():
            continue
        meta, _ = _read(path)
        if meta.get("status") == "open" and meta.get("blocking") is not False:
            open_ids.append(str(qid))
    return open_ids


def bind_task(
    task_id: str,
    *,
    root: Path | None = None,
    outputs: list[str] | None = None,
    inputs: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Append output, input, and evidence paths onto a task without dropping existing ones."""
    repo = Path(root) if root is not None else project_root()
    path = _task_path(repo, task_id)
    meta, text = _read(path)
    if meta.get("status") == "done":
        raise ValueError(f"{task_id} is done")
    for raw in [*(outputs or []), *(inputs or []), *(evidence or [])]:
        _rel(repo, raw)
    for key, extra in (("outputs", outputs), ("inputs", inputs), ("evidence", evidence)):
        current = [str(item) for item in _as_list(meta.get(key))]
        for item in extra or []:
            normalized = item.replace("\\", "/")
            if normalized not in current:
                current.append(normalized)
        meta[key] = current
    meta["updated"] = _today()
    _write(path, meta, text)
    return show_task(task_id, root=repo)


def finish_task(task_id: str, *, root: Path | None = None) -> dict[str, Any]:
    repo = Path(root) if root is not None else project_root()
    path = _task_path(repo, task_id)
    meta, text = _read(path)
    if meta.get("status") == "done":
        raise ValueError(f"{task_id} is done")
    pending = _open_blocking(repo, _as_list(meta.get("questions")))
    if pending:
        raise ValueError(f"{task_id} still has open questions: {', '.join(pending)}")
    if meta.get("type") == "test-execution":
        design = str(meta.get("design") or "")
        if not design or not _rel(repo, design).is_file():
            raise ValueError("test-execution finish requires the design file to exist")
        outputs = [str(item) for item in _as_list(meta.get("outputs"))]
        if not outputs:
            raise ValueError("test-execution finish requires outputs (the curated test report path)")
        missing = [item for item in outputs if not _rel(repo, item).is_file()]
        if missing:
            raise ValueError(f"outputs missing on disk: {', '.join(missing)}")
    meta["status"] = "done"
    meta["updated"] = _today()
    _write(path, meta, text)
    return show_task(task_id, root=repo)


def ask_question(
    *,
    task_id: str,
    topic: str,
    prompt: str,
    root: Path | None = None,
    options: list[dict[str, str]] | None = None,
    blocking: bool = True,
) -> dict[str, Any]:
    assert_no_secret(prompt)
    repo = Path(root) if root is not None else project_root()
    task_path = _task_path(repo, task_id)
    task_meta, task_text = _read(task_path)
    if task_meta.get("status") == "done":
        raise ValueError(f"{task_id} is done")
    chosen = list(options or [])
    if not chosen and topic == LOG_SOURCE_TOPIC:
        chosen = list(LOG_SOURCE_OPTIONS)
    if len(chosen) < 2:
        raise ValueError("ask requires at least two --option id=label values, or topic sut-log-source")
    ids = [item["id"] for item in chosen]
    if len(ids) != len(set(ids)):
        raise ValueError("option ids must be unique")
    question_id = _next_question_id(repo)
    prompt_one = " ".join(prompt.split())
    meta: dict[str, Any] = {
        "kind": "question",
        "id": question_id,
        "task_id": task_id,
        "status": "open",
        "blocking": blocking,
        "topic": topic,
        "prompt": prompt_one,
        "asked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "options": chosen,
    }
    lines = [
        f"# {question_id}",
        "",
        prompt_one,
        "",
        "回答前不要替人选定通道，也不要编写对应的取数实现。",
        "",
        "## Options",
        "",
    ]
    for item in chosen:
        lines.append(f"- `{item['id']}` — {item['label']}")
    lines.append("")
    qpath = questions_dir(repo) / f"{question_id}.md"
    qpath.write_text(dump_front_matter(meta) + "\n".join(lines), encoding="utf-8", newline="\n")
    questions = [str(item) for item in _as_list(task_meta.get("questions"))]
    questions.append(question_id)
    task_meta["questions"] = questions
    if blocking:
        task_meta["status"] = "blocked"
    task_meta["updated"] = _today()
    _write(task_path, task_meta, task_text)
    return {
        "id": question_id,
        "path": qpath.relative_to(repo).as_posix(),
        "task_id": task_id,
        "status": "open",
        "task_status": task_meta["status"],
        "blocking": blocking,
    }


def list_questions(*, root: Path | None = None, status: str | None = "open") -> list[dict[str, Any]]:
    repo = Path(root) if root is not None else project_root()
    if status == "answered":
        directories = [archived_questions_dir(repo)]
    elif status == "open":
        directories = [questions_dir(repo)]
    else:
        directories = [questions_dir(repo), archived_questions_dir(repo)]
    rows = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("Q-*.md")):
            meta, _ = _read(path)
            if status and meta.get("status") != status:
                continue
            rows.append(
                {
                    "id": meta.get("id"),
                    "task_id": meta.get("task_id"),
                    "topic": meta.get("topic"),
                    "status": meta.get("status"),
                    "blocking": meta.get("blocking"),
                    "prompt": meta.get("prompt"),
                    "path": path.relative_to(repo).as_posix(),
                }
            )
    return rows


def _append_decision(text: str, question_id: str, topic: str, option: str, note: str) -> str:
    block = (
        f"\n### {question_id} {topic}\n\n"
        f"- option: {option}\n"
        f"- note: {note or '无'}\n"
    )
    if "## Decisions" not in text:
        text = text.rstrip() + "\n\n## Decisions\n"
    return text.rstrip() + block


def _curate(repo: Path, rel: str, *, task_id: str, question_id: str, topic: str, option: str, note: str) -> str:
    assert_no_secret(note)
    normalized = rel.replace("\\", "/")
    allowed = ("knowledge/wiki/domain-notes/", "assets/domain-notes/")  # second: pre-7.0 layout
    if not normalized.startswith(allowed) or not normalized.endswith(".md"):
        raise ValueError("curate path must be knowledge/wiki/domain-notes/**/*.md")
    path = _rel(repo, normalized)
    section = (
        f"\n## {question_id} {topic}\n\n"
        f"- option: {option}\n"
        f"- note: {note or '无'}\n"
        f"- task: work/tasks/{task_id}.md\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n" + section, encoding="utf-8", newline="\n")
    else:
        meta = {
            "kind": "domain-note",
            "title": path.stem,
            "source": f"work/tasks/{task_id}.md",
            "confidence": "high",
            "task_id": task_id,
        }
        path.write_text(dump_front_matter(meta) + f"# {topic}\n" + section, encoding="utf-8", newline="\n")
        stamp_file(repo, path, kind="domain-note")
    return path.relative_to(repo).as_posix()


def answer_question(
    question_id: str,
    *,
    option: str,
    root: Path | None = None,
    note: str = "",
    curate: str = "",
) -> dict[str, Any]:
    assert_no_secret(note)
    repo = Path(root) if root is not None else project_root()
    path = _question_path(repo, question_id)
    meta, text = _read(path)
    if meta.get("status") != "open":
        raise ValueError(f"{question_id} is {meta.get('status')}")
    known = {str(item.get("id")) for item in _as_list(meta.get("options")) if isinstance(item, dict)}
    if option not in known:
        raise ValueError(f"option must be one of {sorted(known)}")
    meta["status"] = "answered"
    meta["answer"] = {
        "option": option,
        "note": note.strip(),
        "answered": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write(path, meta, text)
    dest = archived_questions_dir(repo) / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    path = dest
    task_id = str(meta.get("task_id") or "")
    task_path = _task_path(repo, task_id)
    task_meta, task_text = _read(task_path)
    task_text = _append_decision(task_text, question_id, str(meta.get("topic") or ""), option, note.strip())
    task_meta["updated"] = _today()
    pending = _open_blocking(repo, _as_list(task_meta.get("questions")))
    if task_meta.get("status") == "blocked" and not pending:
        task_meta["status"] = "in_progress"
    _write(task_path, task_meta, task_text)
    curated = _curate(
        repo,
        curate,
        task_id=task_id,
        question_id=question_id,
        topic=str(meta.get("topic") or ""),
        option=option,
        note=note.strip(),
    ) if curate else ""
    return {
        "id": question_id,
        "status": "answered",
        "option": option,
        "path": path.relative_to(repo).as_posix(),
        "task_id": task_id,
        "task_status": task_meta.get("status"),
        "curated": curated or None,
        "next": next_steps(str(meta.get("topic") or ""), option),
    }


def next_steps(topic: str, option: str) -> list[str]:
    """What the LLM does after a person answered (ports + custom apps, AGENTS.md §4)."""
    if topic != LOG_SOURCE_TOPIC or option == "skip":
        return []
    return [
        f"create-app：按 docs/spec/ports.md 的 log-source 契约写 apps/<name>/（通道 {option}），tool.py 声明 port=\"log-source\"",
        f"maintain-config：在 config 的 PORTS 绑定 log-source，把 {option} 的地址与密钥写进 env_local.ENVIRONMENTS.<env>.OPS",
        "health-check：tuner-workspace doctor 复检 ports.log-source",
    ]
