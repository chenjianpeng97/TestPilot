"""跨 action word 共享的 pydantic 业务模型。

项目落地时把模型放在同目录 ``models_project.py``（模板不包含该文件）。
本模块在能导入 ``models_project`` 时再转出，调用方仍写
``from packages.action_words.models import ...``。
"""
from __future__ import annotations

try:
    from packages.action_words.models_project import *  # noqa: F403
except ImportError:
    pass
