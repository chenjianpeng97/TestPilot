"""Import-safe tool manifest: this app is the dogfood adapter for the log-source port."""
from __future__ import annotations

from tuner_testkit.tools import tool

from .cli import build_parser as _build_parser

build_parser = tool(
    tool_id="sample_log_source",
    name="示例日志端口 sample_log_source",
    summary="log-source 端口的参考适配器：从本地 data/sample-logs 按时间窗读日志并脱敏。",
    group="dogfood",
    module="apps.sample_log_source",
    readme_path="apps/sample_log_source/README.md",
    port="log-source",
    hide_params=("out",),
)(_build_parser)
