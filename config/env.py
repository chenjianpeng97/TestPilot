# 放置「在哪、用什么」：被测系统环境、运维通道、端口绑定、执行通道、知识位置。
# 本文件只提交占位结构（别名 / 类型 / 本地示例 host / 非密钥的团队约定），不含真实密钥。
# 字段说明见 docs/spec/config-syntax.md；查看合并结果：tuner-config show --json；校验：tuner-config validate。
#
# 覆盖顺序（后者覆盖前者的同名键）：
#   1. 本文件占位
#   2. config/env_overlay.py（可选，提交：额外数据源别名与类型、团队约定，仍无密钥）
#   3. config/env_local.py（gitignore，本机真实 host/密码/账号；模板 config/env_local.py.example）
#      - 顶层 CHANNELS / PORTS / KNOWLEDGE 对本机所有环境生效
#      - 若定义了非空 ENVIRONMENTS：由 tuner_testkit.config 按激活名只套用那一套
#        （TUNER_ENV > config/.active_env > ACTIVE_ENV > 唯一 key）
#      - 否则按扁平写法合并
#   4. 环境变量 TUNER_DB_<ALIAS>_HOST/PORT/USER/PASSWORD/NAME
#      （未带别名的 TUNER_DB_HOST 等继续覆盖默认别名 "main"）
#      TEST_BASE_URL / TEST_UI_BASE_URL / TEST_USERNAME / TEST_PASSWORD 同样优先于本模块。
#   探索登录优先读 data/sut-accounts.local.yaml（gitignore；模板 data/sut-accounts.example.yaml）
#
# 切换激活环境：tuner-config use <name>（写入 gitignore 的 .active_env）。

from __future__ import annotations

import sys
from typing import Any

# ---- 被测系统环境（按环境成套切换） -------------------------------------------
DATABASES: dict[str, dict[str, Any]] = {
    # 主业务库 — MySQL
    "main": {
        "type": "mysql",
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "CHANGE_ME",
        "database": "example",
    },
    # 第二数据源占位 — SQL Server（需要时填入真实连接）
    "sqlserver": {
        "type": "sqlserver",
        "host": "127.0.0.1",
        "port": 1433,
        "user": "sa",
        "password": "CHANGE_ME",
        "database": "example",
    },
    # 第三数据源占位 — PostgreSQL（需要时填入真实连接）
    "postgres": {
        "type": "postgres",
        "host": "127.0.0.1",
        "port": 5432,
        "user": "postgres",
        "password": "CHANGE_ME",
        "database": "example",
    },
}

# API 执行的网关地址与 UI 地址（仅 host，不带路径！）。环境变量优先于此处。
TEST_BASE_URL = ""
TEST_UI_BASE_URL = ""

# behave api stage 登录账号。优先级：behave -D username/-D password
# > 环境变量 TEST_USERNAME/TEST_PASSWORD > 此处。
TEST_ACCOUNT: dict[str, str] | None = None

# 运维通道（按环境）：Rancher / SSH 跳板 / 日志平台等。只给端口适配器（apps/）读，kit 不解释内容。
# 真实地址与密钥写在 env_local.ENVIRONMENTS.<name>.OPS。
OPS: dict[str, dict[str, Any]] = {}

# ---- workspace 级约定（可提交，本机可在 env_local 顶层覆盖） ---------------------
# 执行通道：browser = playwright-mcp | cursor-browser（见 docs/spec/browser-channel.md）
CHANNELS: dict[str, str] = {"browser": "playwright-mcp"}

# 端口绑定：端口名 -> 实现它的 workspace app（docs/spec/ports.md），如 {"log-source": "apps.acme_logs"}
PORTS: dict[str, str] = {}

# 知识位置：api_docs = API 文档 URL 或仓库路径；source_roots = 源码本机路径（写在 env_local）
KNOWLEDGE: dict[str, Any] = {"api_docs": [], "source_roots": [], "wiki": "knowledge/wiki"}

# 当前套用的命名环境（仅 env_local 使用 ENVIRONMENTS 时由 tuner_testkit.config 写入）
ACTIVE_ENV: str | None = None


def _apply_module(mod: Any) -> None:
    from tuner_testkit.config import apply_module

    apply_module(sys.modules[__name__], mod)


def _load_overlay(mod_name: str) -> None:
    try:
        mod = __import__(mod_name, fromlist=["*"])
    except ImportError:
        return
    _apply_module(mod)


def _load_env_local() -> None:
    try:
        local = __import__("config.env_local", fromlist=["*"])
    except ImportError:
        return
    from tuner_testkit.config import apply_selected_environment

    if apply_selected_environment(sys.modules[__name__], local) is None:
        _apply_module(local)


_load_overlay("config.env_overlay")
_load_env_local()

# 向后兼容：历史代码读取的默认库即 main 别名
DB_CONFIG = DATABASES["main"]
