"""CLI: stats (testsheet numbers + checks) / draft (report Markdown) / render (docx) / build-template."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from tuner_testkit.logging import log_error, log_info, log_warn
from tuner_testkit.project import project_root

from .stats import build

PACKAGED_TEMPLATE = pathlib.Path(__file__).resolve().parent / "templates" / "gjb438b.docx"


def _emit(line: str) -> None:
    """Structured one-liner for the Shell / AI (not a diagnostic print)."""

    sys.stdout.write(line.rstrip() + "\n")


def _envelope(status: str, outputs: list[dict[str, Any]], artifacts: list[str]) -> None:
    _emit(json.dumps({"status": status, "outputs": outputs, "artifacts": artifacts, "log_path": None}, ensure_ascii=False))


def _resolve(root: pathlib.Path, path: str) -> pathlib.Path:
    candidate = pathlib.Path(path).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate)


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path.resolve())


def _sheet_dirs(root: pathlib.Path, raw_paths: list[str]) -> list[pathlib.Path]:
    dirs = []
    for raw in raw_paths:
        path = _resolve(root, raw)
        if path.is_file() and path.name == "testsheet.md":
            path = path.parent
        if not (path / "testsheet.md").is_file():
            log_error("testsheet_missing", path=raw)
            raise SystemExit(f"找不到测试单：{raw}/testsheet.md")
        dirs.append(path)
    return dirs


def _emit_issues(data: dict[str, Any]) -> None:
    for issue in data["issues"]:
        line = f" line={issue['line']}" if issue["line"] else ""
        _emit(f"issue level={issue['level']} code={issue['code']} sheet={issue['sheet']}{line} {issue['detail']}")


def cmd_stats(args: argparse.Namespace) -> int:
    root = args.root
    dirs = _sheet_dirs(root, args.sheets)
    data = build(dirs, root=root)
    failed = bool(args.check and data["errors"])
    artifacts: list[str] = []

    if args.out:
        out = _resolve(root, args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts.append(_rel(root, out))

    if args.check:
        _emit_issues(data)
        rows = data["rows"]
        _emit(
            "rows total={total} 通过={通过} 失败={失败} 部分通过={部分通过} 未执行={未执行} 阻塞={阻塞}".format(**rows)
            + f" errors={data['errors']} warnings={data['warnings']}"
        )
    elif args.out:
        _emit(f"stats out={artifacts[0]} errors={data['errors']} warnings={data['warnings']}")
    else:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    (log_warn if data["errors"] else log_info)(
        "testreport_stats", sheets=len(dirs), rows=data["rows"]["total"], errors=data["errors"], warnings=data["warnings"]
    )
    if args.json:
        _envelope(
            "failed" if failed else "succeeded",
            [{"kind": "rows", **data["rows"]}, {"kind": "issues", "errors": data["errors"], "warnings": data["warnings"]}],
            artifacts,
        )
    return 1 if failed else 0


def cmd_draft(args: argparse.Namespace) -> int:
    from datetime import date

    from .draft import compose
    from .profile import REQUIRED_KEYS, load_profile

    root = args.root
    dirs = _sheet_dirs(root, args.sheets)
    data = build(dirs, root=root)
    if data["errors"]:
        _emit_issues(data)
        log_warn("testreport_draft_refused", errors=data["errors"])
        _emit(f"draft refused errors={data['errors']}：先按 stats --check 改测试单")
        if args.json:
            _envelope("failed", [{"kind": "issues", "errors": data["errors"], "warnings": data["warnings"]}], [])
        return 1

    default_profile = f"assets/testreport/profiles/{args.sut}.md"
    legacy_profile = f"assets/domain-notes/testreport/{args.sut}.md"
    if not args.profile and not _resolve(root, default_profile).is_file() and _resolve(root, legacy_profile).is_file():
        default_profile = legacy_profile  # pre-7.0 workspace, before `tuner-workspace migrate knowledge`
    profile_path = _resolve(root, args.profile or default_profile)
    profile = load_profile(profile_path)
    if profile.path is None or not profile_path.is_file():
        _emit(f"profile missing path={_rel(root, profile_path)}")
    today = date.today()
    text, hints = compose(
        data,
        profile,
        slug=args.slug,
        sut=args.sut,
        env=args.env,
        task_id=args.task,
        profile_rel=_rel(root, profile_path),
        today=today,
        root=root,
    )
    out = _resolve(root, args.out or f"assets/testreport/{args.sut}/{today:%Y-%m}/{args.slug}.md")
    if out.exists() and not args.force:
        _emit(f"draft refused out={_rel(root, out)} 已存在，加 --force 覆盖")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    for key in profile.missing():
        if key not in REQUIRED_KEYS:
            _emit(f"profile empty field={key}（报告写「/」）")
    for hint in hints:
        _emit(f"todo {hint}")
    _emit(f"draft out={_rel(root, out)} todos={len(hints)} cases={data['rows']['total']} defects={data['defects']['total']}")
    log_info("testreport_draft", out=_rel(root, out), todos=len(hints))
    if args.json:
        _envelope("succeeded", [{"kind": "draft", "todos": len(hints)}], [_rel(root, out)])
    return 0


def _safe_name(name: str) -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip()
    return cleaned or "testreport"


def cmd_render(args: argparse.Namespace) -> int:
    from tuner_testkit.artifacts import default_producer, start_run

    from .render import ReportFormatError, parse_report, render_docx

    root = args.root
    report = _resolve(root, args.report)
    template = _resolve(root, args.template) if args.template else PACKAGED_TEMPLATE
    try:
        parsed = parse_report(report)
    except ReportFormatError as exc:
        log_error("testreport_render_refused", report=_rel(root, report), reason=str(exc))
        _emit(f"render refused report={_rel(root, report)} {exc}")
        if args.json:
            _envelope("failed", [{"kind": "error", "detail": str(exc)}], [])
        return 1

    slug = parsed["meta"].get("id") or report.stem
    manifest = start_run(
        "run",
        f"testreport-{slug}",
        root=root,
        producer=default_producer(root, tool_id="testreport", argv=sys.argv[1:]),
        params={"report": _rel(root, report), "template": _rel(root, template)},
    )
    out = manifest.dir / f"{_safe_name(parsed['doc_title'])}.docx"
    summary = render_docx(report, template, out)
    ok = summary["leftover_tags"] == 0 and summary["case_rows"] == summary["cases"]
    status = "succeeded" if ok else "failed"
    manifest.finish(status, exit_code=0 if ok else 1, summary={"report": _rel(root, report), "docx": _rel(root, out), **summary})
    (log_info if ok else log_error)("testreport_rendered", report=_rel(root, report), docx=_rel(root, out), ok=ok)
    _emit(f"render out={_rel(root, out)} cases={summary['cases']} verdict={summary['verdict']}")
    _emit(f"check leftover_tags={summary['leftover_tags']} case_rows={summary['case_rows']} {'ok' if ok else 'failed'}")
    if args.json:
        _envelope(status, [{"kind": "docx", **summary}], [_rel(root, out), _rel(root, manifest.path)])
    return 0 if ok else 1


def cmd_build_template(args: argparse.Namespace) -> int:
    from .template_build import build_template

    root = args.root
    out = build_template(_resolve(root, args.source), _resolve(root, args.out))
    log_info("testreport_template_built", out=_rel(root, out))
    _emit(f"template out={_rel(root, out)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuner-testreport",
        description="Count testsheet results and render a GJB438B test report.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stats = sub.add_parser("stats", help="parse testsheet rounds and print report numbers")
    p_stats.add_argument("sheets", nargs="+", help="assets/testsheet/<轮次> 目录；多份时同一用例以后者为准")
    p_stats.add_argument("--check", action="store_true", help="只输出问题与计数；有 error 时退出码 1")
    p_stats.add_argument("--out", default="", help="把完整 JSON 写到这个文件")
    p_stats.add_argument("--json", action="store_true", help="最后一行输出 envelope JSON")
    p_stats.set_defaults(func=cmd_stats)

    p_draft = sub.add_parser("draft", help="write the report Markdown from testsheets + profile")
    p_draft.add_argument("sheets", nargs="+", help="assets/testsheet/<轮次> 目录")
    p_draft.add_argument("--sut", required=True, help="被测系统短名；也决定画像与报告路径")
    p_draft.add_argument("--slug", required=True, help="报告 id（ASCII，例 260101-login）")
    p_draft.add_argument("--profile", default="", help="画像路径，默认 assets/testreport/profiles/<sut>.md")
    p_draft.add_argument("--env", default="", help="front-matter env")
    p_draft.add_argument("--task", default="", help="front-matter task_id")
    p_draft.add_argument("--out", default="", help="默认 assets/testreport/<sut>/<yyyy-mm>/<slug>.md")
    p_draft.add_argument("--force", action="store_true", help="覆盖已存在的报告")
    p_draft.add_argument("--json", action="store_true", help="最后一行输出 envelope JSON")
    p_draft.set_defaults(func=cmd_draft)

    p_render = sub.add_parser("render", help="render the report Markdown into docx under artifacts/runs/")
    p_render.add_argument("report", help="assets/testreport/<sut>/<yyyy-mm>/<slug>.md")
    p_render.add_argument("--template", default="", help="docxtpl 模板；默认用 kit 自带的 gjb438b.docx")
    p_render.add_argument("--json", action="store_true", help="最后一行输出 envelope JSON")
    p_render.set_defaults(func=cmd_render)

    p_tpl = sub.add_parser("build-template", help="convert a sample GJB438B report docx into the docxtpl template")
    p_tpl.add_argument("source", help="样例报告 .docx")
    p_tpl.add_argument("--out", required=True, help="模板输出路径，render 时用 --template 指过去")
    p_tpl.set_defaults(func=cmd_build_template)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.root = project_root()
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
