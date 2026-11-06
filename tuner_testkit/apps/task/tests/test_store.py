from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.apps.task.cli import main
from tuner_testkit.apps.task.store import answer_question, ask_question, attach_file, create_task, finish_task, list_tasks, show_task
from tuner_testkit.apps.task.validate import validate_testdesign
from tuner_testkit.catalog.front_matter import parse_front_matter


def _design(root: Path) -> Path:
    path = root / "assets" / "testdesign" / "order" / "create.md"
    path.parent.mkdir(parents=True)
    headings = ["范围", "不测", "风险", "策略", "点击路径", "用例大纲", "执行反馈", "证据与来源"]
    body = "\n".join(f"## {title}\n\n无\n" for title in headings)
    path.write_text(
        "---\nkind: testdesign\nsource: assets/usecases/order/create.md\nevidence: []\n---\n\n# 订单创建\n\n" + body,
        encoding="utf-8",
    )
    return path


def test_ask_blocks_until_answer_then_curates(tmp_path: Path):
    design = _design(tmp_path)
    created = create_task(
        task_type="test-execution",
        title="订单创建端到端",
        root=tmp_path,
        design=design.relative_to(tmp_path).as_posix(),
        outputs=["assets/testreport/order/2026-09/create.md"],
        author="qa@example.com",
    )
    asked = ask_question(
        task_id=created["id"],
        topic="sut-log-source",
        prompt="仓库没有写明后端日志从哪取",
        root=tmp_path,
    )
    assert asked["task_status"] == "blocked"
    question = (tmp_path / asked["path"]).read_text(encoding="utf-8")
    assert "rancher-api" in question
    with pytest.raises(ValueError, match="secrets"):
        answer_question(asked["id"], option="log-api", note="token: abcdef", root=tmp_path)
    answered = answer_question(
        asked["id"],
        option="rancher-api",
        note="命名空间见 env_local 的 OPS.rancher",
        curate="knowledge/wiki/domain-notes/order/log-source.md",
        root=tmp_path,
    )
    assert answered["task_status"] == "in_progress"
    assert any("create-app" in step and "log-source" in step for step in answered["next"])
    assert any("PORTS" in step for step in answered["next"])
    assert answered["path"].startswith("artifacts/inbox/archived-question/")
    assert not (tmp_path / "artifacts" / "inbox" / "questions" / f"{asked['id']}.md").is_file()
    archived = tmp_path / answered["path"]
    assert "status: answered" in archived.read_text(encoding="utf-8")
    note = (tmp_path / answered["curated"]).read_text(encoding="utf-8")
    assert "rancher-api" in note
    assert parse_front_matter(note)["kind"] == "domain-note"
    report = tmp_path / "assets" / "testreport" / "order" / "2026-09" / "create.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report\n", encoding="utf-8")
    done = finish_task(created["id"], root=tmp_path)
    assert done["status"] == "done"


def test_cli_create_and_validate(tmp_path: Path):
    design = _design(tmp_path)
    assert validate_testdesign(design) == []
    code = main([
        "create",
        "--type", "test-design",
        "--title", "订单创建测试设计",
        "--scope", "order-create",
        "--root", str(tmp_path),
        "--author", "qa@example.com",
    ])
    assert code == 0
    task = next((tmp_path / "work" / "tasks").glob("TASK-*/task.md"))
    meta = parse_front_matter(task.read_text(encoding="utf-8"))
    assert meta["type"] == "test-design"
    assert meta["status"] == "open"
    code = main(["validate", "--task", meta["id"], "--root", str(tmp_path), str(design.relative_to(tmp_path))])
    assert code == 0


def test_bind_appends_output(tmp_path: Path):
    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    report = tmp_path / "assets" / "explore" / "web" / "home.md"
    report.parent.mkdir(parents=True)
    report.write_text("# home\n", encoding="utf-8")
    assert main([
        "bind", created["id"],
        "--output", "assets/explore/web/home.md",
        "--evidence", "artifacts/evidence/20260924T000000Z-home",
        "--root", str(tmp_path),
    ]) == 0
    shown = show_task(created["id"], root=tmp_path)
    assert shown["outputs"] == ["assets/explore/web/home.md"]
    assert shown["evidence"] == ["artifacts/evidence/20260924T000000Z-home"]


def test_answer_archives_question_and_keeps_id(tmp_path: Path):
    created = create_task(task_type="explore", title="看日志", root=tmp_path, author="qa@example.com")
    first = ask_question(
        task_id=created["id"],
        topic="sut-log-source",
        prompt="日志从哪取",
        root=tmp_path,
    )
    answer_question(first["id"], option="skip", root=tmp_path)
    second = ask_question(
        task_id=created["id"],
        topic="sut-log-source",
        prompt="再确认一次通道",
        root=tmp_path,
    )
    assert second["id"] != first["id"]
    assert int(second["id"].rsplit("-", 1)[-1]) == int(first["id"].rsplit("-", 1)[-1]) + 1


def test_finish_refuses_open_question(tmp_path: Path):
    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    ask_question(
        task_id=created["id"],
        topic="sut-log-source",
        prompt="缺日志来源",
        root=tmp_path,
    )
    assert main(["finish", created["id"], "--root", str(tmp_path)]) == 1


def test_create_makes_task_folder_with_attachments(tmp_path: Path):
    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    assert created["path"] == f"work/tasks/{created['id']}/task.md"
    folder = tmp_path / "work" / "tasks" / created["id"]
    assert (folder / "task.md").is_file() and (folder / "attachments").is_dir()
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    note = tmp_path / "需求补充.md"
    note.write_text("客户补充：只测管理员\n", encoding="utf-8")
    assert main(["attach", created["id"], "--file", str(shot), "--root", str(tmp_path)]) == 0
    attached = attach_file(created["id"], note, root=tmp_path)
    assert attached["attached"].endswith("attachments/需求补充.md")
    row = show_task(created["id"], root=tmp_path)
    assert row["attachments"] == ["attachments/shot.png", "attachments/需求补充.md"]
    assert list_tasks(root=tmp_path)[0]["attachments"] == row["attachments"]
    # 不覆盖同名附件
    with pytest.raises(ValueError, match="already exists"):
        attach_file(created["id"], shot, root=tmp_path)


def test_attach_rejects_secrets_and_bad_names(tmp_path: Path):
    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    bad = tmp_path / "notes.txt"
    bad.write_text("password: hunter2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secrets"):
        attach_file(created["id"], bad, root=tmp_path)
    ok = tmp_path / "ok.txt"
    ok.write_text("fine\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bad attachment name"):
        attach_file(created["id"], ok, root=tmp_path, name="../x.txt")


def test_legacy_single_file_task_still_works_and_upgrades_on_attach(tmp_path: Path):
    legacy = tmp_path / "work" / "tasks" / "TASK-20260101-001.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        "---\nkind: task\nid: TASK-20260101-001\ntitle: 旧任务\ntype: explore\nstatus: open\n"
        "questions: []\n---\n# 旧任务\n\n## Decisions\n",
        encoding="utf-8",
    )
    assert show_task("TASK-20260101-001", root=tmp_path)["path"] == "work/tasks/TASK-20260101-001.md"
    new = create_task(task_type="explore", title="新任务", root=tmp_path, author="qa@example.com")
    assert new["id"] != "TASK-20260101-001"
    # 同一天再建不与旧编号冲突
    f = tmp_path / "a.txt"
    f.write_text("x\n", encoding="utf-8")
    result = attach_file("TASK-20260101-001", f, root=tmp_path)
    assert result["path"] == "work/tasks/TASK-20260101-001/task.md"
    assert not legacy.exists()
    assert {r["id"] for r in list_tasks(root=tmp_path)} == {"TASK-20260101-001", new["id"]}


def test_archive_warns_but_never_blocks(tmp_path: Path):
    from tuner_testkit.apps.task.store import archive_task

    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    ask_question(task_id=created["id"], topic="sut-log-source", prompt="日志从哪取", root=tmp_path)
    preview = archive_task(created["id"], root=tmp_path, dry_run=True)
    assert preview["moved"] is False and len(preview["warnings"]) == 2
    assert (tmp_path / "work" / "tasks" / created["id"] / "task.md").is_file()
    moved = archive_task(created["id"], root=tmp_path)
    assert moved["moved"] is True and moved["archived"] is True
    assert (tmp_path / "work" / "tasks" / "archived" / created["id"] / "task.md").is_file()


def test_archive_done_task_and_keep_lookup(tmp_path: Path):
    from tuner_testkit.apps.task.store import archive_task

    created = create_task(task_type="explore", title="摸页面", root=tmp_path, author="qa@example.com")
    shot = tmp_path / "a.txt"
    shot.write_text("x\n", encoding="utf-8")
    attach_file(created["id"], shot, root=tmp_path)
    finish_task(created["id"], root=tmp_path)
    row = archive_task(created["id"], root=tmp_path)
    assert row["warnings"] == []
    assert row["path"] == f"work/tasks/archived/{created['id']}/task.md" and row["archived"] is True
    assert row["attachments"] == ["attachments/a.txt"]
    assert not (tmp_path / "work" / "tasks" / created["id"]).exists()
    assert list_tasks(root=tmp_path) == []
    assert [r["id"] for r in list_tasks(root=tmp_path, include_archived=True)] == [created["id"]]
    assert show_task(created["id"], root=tmp_path)["status"] == "done"
    with pytest.raises(ValueError, match="already archived"):
        archive_task(created["id"], root=tmp_path)
    # 编号不复用已归档任务
    assert create_task(task_type="explore", title="再来", root=tmp_path, author="qa@example.com")["id"] != created["id"]
    assert main(["status", "--all", "--root", str(tmp_path)]) == 0
