"""Pure logic for sample_tool (offline, unit-testable)."""
from __future__ import annotations


def build_lines(count: int, label: str, style: str = "plain") -> list[str]:
    """Return ``count`` lines like ``"<label>-001"``; ``style="upper"`` upper-cases them."""
    if count < 0:
        raise ValueError("count must be >= 0")
    lines = [f"{label}-{index:03d}" for index in range(1, count + 1)]
    if style == "upper":
        return [line.upper() for line in lines]
    return lines
