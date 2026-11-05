"""ActionContext — action word 运行所需环境资源的惰性容器。

持有 DB 连接与 API 登录 token，按 word 的 ``requires`` 声明按需初始化：

- ``get_db(alias)``: 按 ``config.env.DATABASES`` 中的命名数据源别名取
  :class:`tuner_testkit.db.DbClient`，实例内按别名缓存（框架支持 MySQL /
  SQL Server 共存，word 通过类元数据 ``datasource`` 声明目标库）；
- ``db``: 默认别名（``main``）的便捷入口，等价 ``get_db(DEFAULT_ALIAS)``；
- ``api_token``: 首次访问时通过可配置的登录 API Object 换取；凭据解析
  顺序为 显式入参 > 环境变量 ``TEST_USERNAME`` / ``TEST_PASSWORD``（CI 注入） >
  ``data/sut-accounts.local.yaml``（``tuner_testkit.accounts``）；behave 的 ``-D username/password`` 由
  environment 钩子解析后显式传入。

一个 behave scenario / 一次 CLI 运行对应一个 ActionContext 实例，
token 与各别名的 DB 连接在实例内缓存。
"""
from __future__ import annotations

import os

from tuner_testkit.db import DEFAULT_ALIAS, DbClient


class ActionContext:
    def __init__(
        self,
        *,
        db: DbClient | None = None,
        username: str | None = None,
        password: str | None = None,
        bearer_token: str | None = None,
    ) -> None:
        # 别名 -> DbClient；外部注入的 db 挂在默认别名下，由注入方管理生命周期
        self._dbs: dict[str, DbClient] = {}
        self._injected_aliases: set[str] = set()
        if db is not None:
            self._dbs[DEFAULT_ALIAS] = db
            self._injected_aliases.add(DEFAULT_ALIAS)
        self._username = username
        self._password = password
        self._token = bearer_token

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def get_db(self, alias: str = DEFAULT_ALIAS) -> DbClient:
        """按命名数据源别名取 DbClient；未注入时首次访问惰性创建并缓存。"""
        client = self._dbs.get(alias)
        if client is None:
            client = DbClient.for_datasource(alias)
            self._dbs[alias] = client
        return client

    @property
    def db(self) -> DbClient:
        return self.get_db(DEFAULT_ALIAS)

    # ------------------------------------------------------------------
    # API 登录 token
    # ------------------------------------------------------------------

    @property
    def api_token(self) -> str:
        if self._token:
            return self._token
        username, password = self._resolve_credentials()
        from tuner_testkit.action_words._internal.api import login_token

        self._token = login_token(username, password)
        return self._token

    def _resolve_credentials(self) -> tuple[str, str]:
        username = self._username or os.getenv("TEST_USERNAME") or ""
        password = self._password or os.getenv("TEST_PASSWORD") or ""
        if not username or not password:
            from tuner_testkit.accounts import resolve_account

            account = resolve_account()
            username = username or account.get("username", "")
            password = password or account.get("password", "")
        if not username or not password:
            raise RuntimeError(
                "缺少登录凭据：请在 data/sut-accounts.local.yaml 写账号（模板 data/sut-accounts.example.yaml），"
                "或通过 behave -D username=... -D password=...，"
                "或环境变量 TEST_USERNAME / TEST_PASSWORD 提供"
            )
        return str(username), str(password)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭自建的 DB 连接；外部注入的连接由注入方管理。"""
        for alias, client in list(self._dbs.items()):
            if alias not in self._injected_aliases:
                client.close()
                del self._dbs[alias]

    def __enter__(self) -> "ActionContext":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
