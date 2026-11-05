"""项目主数据 / 默认样例常量占位。

业务仓库把真实主数据放到同目录 ``params_project.py``（模板不包含该文件）。
本模块在能导入 ``params_project`` 时再转出那些常量，供 db_seed 默认值与
步骤别名表引用。
"""
from __future__ import annotations

try:
    from packages.action_words._internal.params_project import *  # noqa: F403
except ImportError:
    pass
