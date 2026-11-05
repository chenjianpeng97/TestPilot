"""Static, round-independent report fields kept in assets/testreport/profiles/<sut>.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import mdparse

BASIC_KEYS = (
    "系统名称", "编制单位", "文档标识号", "缩略语", "需方", "开发方", "保障机构",
    "软件标识号", "软件名称", "编程语言", "程序规模", "测试类型",
)
REQUIRED_KEYS = ("系统名称", "编制单位")
REFERENCE_COLUMNS = ("文档编号", "文档标题", "编写单位", "发布日期")
SOFTWARE_COLUMNS = ("支持软件名称", "版本号", "用途", "介质", "来源", "保密性")
HARDWARE_COLUMNS = ("硬件名称", "配置", "推荐型号", "用途", "数量", "保密性")
IMPACT_COLUMNS = ("测试环境", "实装环境", "影响分析", "解决措施")


@dataclass
class Profile:
    path: Path | None = None
    basic: dict[str, str] = field(default_factory=dict)
    intro: list[str] = field(default_factory=list)
    run_site: list[str] = field(default_factory=list)
    references: list[dict[str, str]] = field(default_factory=list)
    software: list[dict[str, str]] = field(default_factory=list)
    hardware: list[dict[str, str]] = field(default_factory=list)
    impacts: list[dict[str, str]] = field(default_factory=list)
    criteria: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        return self.basic.get(key, "").strip()

    def missing(self) -> list[str]:
        """Basic fields left empty; the skill asks the engineer instead of guessing."""

        return [key for key in BASIC_KEYS if not self.get(key)]


def _kv(blocks: list[mdparse.Block]) -> dict[str, str]:
    for block in blocks:
        if block.kind == "table" and block.table and block.table.header[:2] == ["项", "内容"]:
            return {row[0].strip(): (row[1].strip() if len(row) > 1 else "") for row in block.table.rows if row and row[0].strip()}
    return {}


def _records(blocks: list[mdparse.Block], columns: tuple[str, ...]) -> list[dict[str, str]]:
    for block in blocks:
        if block.kind == "table" and block.table and all(col in block.table.header for col in columns[:2]):
            rows = []
            for record in block.table.records():
                values = {col: record.get(col, "").strip() for col in columns}
                if any(values.values()):
                    rows.append(values)
            return rows
    return []


def _paras(blocks: list[mdparse.Block]) -> list[str]:
    return [block.text for block in blocks if block.kind == "para"]


def load_profile(path: Path | None) -> Profile:
    if path is None or not path.is_file():
        return Profile(path=path)
    _, body = mdparse.split_front_matter(path.read_text(encoding="utf-8"))
    parts = mdparse.outline(body)
    return Profile(
        path=path,
        basic=_kv(parts.get("基本信息", [])),
        intro=_paras(parts.get("系统简介", [])),
        run_site=_paras(parts.get("运行现场", [])),
        references=_records(parts.get("引用文档", []), REFERENCE_COLUMNS),
        software=_records(parts.get("软件环境", []), SOFTWARE_COLUMNS),
        hardware=_records(parts.get("硬件环境", []), HARDWARE_COLUMNS),
        impacts=_records(parts.get("测试环境影响", []), IMPACT_COLUMNS),
        criteria=_kv(parts.get("通过准则", [])),
    )
