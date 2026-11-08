"""Read-only dashboard data for the workbench.

The numbers are produced offline by ``tuner-dashboard refresh`` (skill
``refresh-dashboard``). Requests only read ``artifacts/catalogs/dashboard.json``
— parsed once per file mtime — and fall back to the counts in the committed
``DASHBOARD.md``. Nothing here scans the workspace.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tuner_testkit.apps.dashboard.render import JSON_REL, MARKDOWN_NAME, read_markdown

HINT = "本机尚未统计：让 AI 执行 refresh-dashboard，或运行 uv run tuner-dashboard refresh"

PAGES: tuple[tuple[str, str, str], ...] = (
    ("assets", "测试资产", "用例、测试单、缺陷"),
    ("automation", "自动化覆盖", "API / 页面对象、动作词、BDD、pytest"),
    ("tools", "工具", "工作台通用命令与项目自建工具"),
    ("doctor", "工作台自检", "基础项与各功能就绪度"),
    ("config", "被测系统配置", "环境、地址、数据源概览"),
)


class DashboardStore:
    """Cache of the dashboard result files keyed by ``(mtime_ns, size)``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.json_path = self.root / JSON_REL
        self.md_path = self.root / MARKDOWN_NAME
        self.parse_count = 0
        self._lock = threading.Lock()
        self._key: tuple[str, int, int] | None = None
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Raw payload: ``source`` is ``json``, ``markdown`` or ``none``."""
        path, source = (self.json_path, "json") if self.json_path.is_file() else (self.md_path, "markdown")
        try:
            stat = path.stat()
        except OSError:
            return {"source": "none", "counts": {}, "sections": {}, "checked_at": None, "updated": None}
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                self._data = self._parse(path, source)
                self._key = key
                self.parse_count += 1
            return self._data

    def view(self) -> dict[str, Any]:
        """Payload plus display helpers for templates (age, hint, failed sections)."""
        data = self.load()
        sections = data.get("sections") or {}
        stamp = data.get("checked_at") or data.get("updated")
        return {
            **data,
            "stamp": stamp,
            "age": _age(stamp),
            "hint": None if data["source"] == "json" else HINT,
            "errors": {k: v["error"] for k, v in sections.items() if isinstance(v, dict) and v.get("error")},
        }

    @staticmethod
    def _parse(path: Path, source: str) -> dict[str, Any]:
        if source == "json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return {"source": "none", "counts": {}, "sections": {}, "checked_at": None, "updated": None,
                        "read_error": f"{type(exc).__name__}: {exc}"[:200]}
            return {**data, "source": "json"}
        front = read_markdown(path)
        counts = {k: v for k, v in front.items() if isinstance(v, int) and not isinstance(v, bool)}
        return {"source": "markdown", "counts": counts, "sections": {}, "checked_at": None,
                "updated": front.get("updated"), "kit_version": front.get("kit_version")}


def _age(stamp: Any) -> str:
    if not stamp:
        return ""
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    minutes = int((datetime.now(timezone.utc) - when).total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes} 分钟前"
    if minutes < 60 * 48:
        return f"{minutes // 60} 小时前"
    return f"{minutes // (60 * 24)} 天前"
