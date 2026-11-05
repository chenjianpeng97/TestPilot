from __future__ import annotations

from pathlib import Path

import pytest

from tuner_testkit.apps.task.cli import main
from tuner_testkit.apps.task.store import answer_question, ask_question, create_task, finish_task, show_task
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
    task = next((tmp_path / "work" / "tasks").glob("TASK-*.md"))
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
