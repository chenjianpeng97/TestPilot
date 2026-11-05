"""Import-safe tool manifest for sample_tool (what the catalog / workbench read)."""
from __future__ import annotations

from tuner_testkit.tools import tool

from .cli import build_parser as _build_parser

build_parser = tool(
    tool_id="sample_tool",
    name="示例工具 sample_tool",
    summary="离线生成带标签的样例行；工作台表单与 QA 一天验收的 fixture。",
    group="dogfood",
    module="apps.sample_tool",
    readme_path="apps/sample_tool/README.md",
    hide_params=("out",),
)(_build_parser)
