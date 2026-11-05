"""Read, filter and redact local log files (reference adapter for the log-source port)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tuner_testkit.apps.evidence.persist import redact_text

_RELATIVE = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
_LINE = re.compile(r"^(?P<ts>\S+)\s+(?P<level>[A-Z]+)\s+(?P<service>\S+)\s+(?P<rest>.*)$")


@dataclass
class LogLine:
    ts: datetime
    level: str
    service: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"ts": self.ts.isoformat(), "level": self.level, "service": self.service, "line": self.text}


def parse_time(raw: str, *, now: datetime | None = None) -> datetime:
    """``now``, a relative window like ``15m`` / ``2h`` (meaning *ago*), or an ISO timestamp."""
    current = now or datetime.now(timezone.utc)
    text = raw.strip()
    if text == "now":
        return current
    match = _RELATIVE.match(text)
    if match:
        return current - timedelta(**{_UNITS[match.group(2)]: int(match.group(1))})
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def read_lines(folder: Path) -> list[LogLine]:
    rows: list[LogLine] = []
    for path in sorted(folder.glob("*.log")):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = _LINE.match(raw.strip())
            if not match:
                continue
            try:
                ts = parse_time(match.group("ts"))
            except ValueError:
                continue
            rows.append(LogLine(ts=ts, level=match.group("level"), service=match.group("service"), text=raw.strip()))
    return rows


def select(
    lines: list[LogLine],
    *,
    since: datetime,
    until: datetime,
    service: str = "",
    grep: str = "",
    trace_id: str = "",
    limit: int = 500,
) -> list[LogLine]:
    picked: list[LogLine] = []
    for line in sorted(lines, key=lambda item: item.ts):
        if not since <= line.ts <= until:
            continue
        if service and line.service != service:
            continue
        if grep and grep not in line.text:
            continue
        if trace_id and f"trace={trace_id}" not in line.text:
            continue
        picked.append(LogLine(ts=line.ts, level=line.level, service=line.service, text=redact_text(line.text)))
        if len(picked) >= limit:
            break
    return picked
