"""CLI for work tasks and blocking human questions.

    tuner-task create --type test-design --title "订单创建测试设计"
    tuner-task ask --task TASK-20260924-001 --topic sut-log-source --prompt "仓库没有日志来源"
    tuner-task answer Q-20260924-001 --option rancher-api --note "命名空间见 env_local 的 OPS.rancher"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tuner_testkit.catalog.front_matter import parse_front_matter
from tuner_testkit.logging import log_error
from tuner_testkit.project import ensure_project_on_path, project_root

from .store import (
    answer_question,
    ask_question,
    bind_task,
    create_task,
    finish_task,
    list_questions,
    list_tasks,
    set_status,
    show_task,
)
from .validate import validate_task_meta, validate_testdesign


def _option(raw: str) -> dict[str, str]:
    key, sep, label = raw.partition("=")
    if not sep or not key.strip() or not label.strip():
        raise argparse.ArgumentTypeError("option must be id=label")
    return {"id": key.strip(), "label": label.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tuner-task", description="Record work tasks and blocking human questions.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_p = sub.add_parser("create", help="write work/tasks/TASK-*.md")
    create_p.add_argument("--type", required=True, dest="task_type")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--objective", default="")
    create_p.add_argument("--scope", action="append", default=[])
    create_p.add_argument("--input", action="append", default=[], dest="inputs")
    create_p.add_argument("--output", action="append", default=[], dest="outputs")
    create_p.add_argument("--design", default="")
    create_p.add_argument("--author", default=None)
    create_p.add_argument("--root", type=Path, default=None)

    status_p = sub.add_parser("status", help="print one task or every task as JSON")
    status_p.add_argument("task_id", nargs="?")
    status_p.add_argument("--root", type=Path, default=None)

    start_p = sub.add_parser("start", help="mark a task in_progress")
    start_p.add_argument("task_id")
    start_p.add_argument("--root", type=Path, default=None)

    bind_p = sub.add_parser("bind", help="append inputs, outputs, or evidence paths on a task")
    bind_p.add_argument("task_id")
    bind_p.add_argument("--input", action="append", default=[], dest="inputs")
    bind_p.add_argument("--output", action="append", default=[], dest="outputs")
    bind_p.add_argument("--evidence", action="append", default=[])
    bind_p.add_argument("--root", type=Path, default=None)

    finish_p = sub.add_parser("finish", help="mark a task done when blocking questions are answered")
    finish_p.add_argument("task_id")
    finish_p.add_argument("--root", type=Path, default=None)

    ask_p = sub.add_parser("ask", help="write artifacts/inbox/questions and block the task")
    ask_p.add_argument("--task", required=True, dest="task_id")
    ask_p.add_argument("--topic", required=True)
    ask_p.add_argument("--prompt", required=True)
    ask_p.add_argument("--option", action="append", type=_option, default=[], dest="options")
    ask_p.add_argument("--no-blocking", action="store_true")
    ask_p.add_argument("--root", type=Path, default=None)

    answer_p = sub.add_parser("answer", help="record a human answer and unblock the task")
    answer_p.add_argument("question_id")
    answer_p.add_argument("--option", required=True)
    answer_p.add_argument("--note", default="")
    answer_p.add_argument("--curate", default="", help="knowledge/wiki/domain-notes/**/*.md to append the decision")
    answer_p.add_argument("--root", type=Path, default=None)

    questions_p = sub.add_parser("questions", help="list questions (default: open)")
    questions_p.add_argument("--status", default="open")
    questions_p.add_argument("--root", type=Path, default=None)

    validate_p = sub.add_parser("validate", help="check a testdesign file or a task id")
    validate_p.add_argument("path", nargs="?", type=Path)
    validate_p.add_argument("--task", dest="task_id")
    validate_p.add_argument("--root", type=Path, default=None)
    return parser


def _root(ns: argparse.Namespace) -> Path:
    if ns.root is not None:
        return ns.root
    ensure_project_on_path()
    return project_root()


def _print_json(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str))
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ns = build_parser().parse_args(argv)
    root = _root(ns)
    try:
        if ns.cmd == "create":
            _print_json(create_task(
                task_type=ns.task_type,
                title=ns.title,
                root=root,
                objective=ns.objective,
                scope=ns.scope,
                inputs=ns.inputs,
                outputs=ns.outputs,
                design=ns.design,
                author=ns.author,
            ))
            return 0
        if ns.cmd == "status":
            payload = show_task(ns.task_id, root=root) if ns.task_id else list_tasks(root=root)
            _print_json(payload)
            return 0
        if ns.cmd == "start":
            _print_json(set_status(ns.task_id, "in_progress", root=root))
            return 0
        if ns.cmd == "bind":
            _print_json(bind_task(
                ns.task_id,
                root=root,
                outputs=ns.outputs,
                inputs=ns.inputs,
                evidence=ns.evidence,
            ))
            return 0
        if ns.cmd == "finish":
            _print_json(finish_task(ns.task_id, root=root))
            return 0
        if ns.cmd == "ask":
            _print_json(ask_question(
                task_id=ns.task_id,
                topic=ns.topic,
                prompt=ns.prompt,
                root=root,
                options=ns.options,
                blocking=not ns.no_blocking,
            ))
            return 0
        if ns.cmd == "answer":
            _print_json(answer_question(
                ns.question_id,
                option=ns.option,
                root=root,
                note=ns.note,
                curate=ns.curate,
            ))
            return 0
        if ns.cmd == "questions":
            status = None if ns.status in {"", "all"} else ns.status
            _print_json(list_questions(root=root, status=status))
            return 0
        if ns.cmd == "validate":
            errors: list[str] = []
            if ns.task_id:
                task = show_task(ns.task_id, root=root)
                text = (root / task["path"]).read_text(encoding="utf-8")
                errors.extend(validate_task_meta(parse_front_matter(text)))
            if ns.path is not None:
                errors.extend(validate_testdesign(ns.path if ns.path.is_absolute() else root / ns.path))
            if ns.task_id is None and ns.path is None:
                raise ValueError("validate requires a path or --task")
            _print_json({"ok": not errors, "errors": errors})
            return 0 if not errors else 1
    except (OSError, ValueError, FileNotFoundError) as exc:
        log_error("task cli failed", error=f"{type(exc).__name__}: {exc}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
