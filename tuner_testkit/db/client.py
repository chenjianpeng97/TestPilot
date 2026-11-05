"""Thin multi-dialect DB client backed by a SQLAlchemy engine.

Design:
    - Business code should create one ``DbClient`` per logical unit of work
      (e.g. a test scenario) and close it when done. The client keeps a single
      pooled connection alive and reconnects if it drops.
    - Datasources are named in ``config.env.DATABASES``; use
      ``DbClient.for_datasource("sqlserver")`` to target a specific one.
      ``DbClient.default()`` targets the ``"main"`` alias.
    - pymssql (SQL Server), pymysql (MySQL) and psycopg (PostgreSQL) all use
      the ``%s`` / ``%(key)s`` pyformat parameter style, and all SQL goes
      through ``Connection.exec_driver_sql``, so query code is identical
      across dialects apart from the SQL text itself.
    - No table names or column names are hardcoded here.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Iterator, Mapping, Sequence
from uuid import UUID

from .connection import (
    ConnectionSettings,
    create_engine_for,
    get_default_settings,
    get_settings,
)

_ParamType = Sequence[Any] | Mapping[str, Any] | None


def _sql_literal(value: Any, *, dialect: str = "mysql") -> str:
    """Render a Python value as a SQL literal (diagnostics / mogrify only)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        if dialect == "postgresql":
            return "TRUE" if value else "FALSE"
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        if dialect == "postgresql":
            return "'" + value.isoformat(sep=" ") + "'"
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "'"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    if isinstance(value, UUID):
        return f"'{value}'"
    if isinstance(value, (bytes, bytearray, memoryview)):
        blob = bytes(value)
        if dialect == "postgresql":
            return r"'\x" + blob.hex() + "'"
        return "0x" + blob.hex()
    text = str(value).replace("'", "''")
    return f"'{text}'"


@dataclass
class DbClient:
    settings: ConnectionSettings = field(default_factory=get_default_settings)
    _engine: Any = field(default=None, init=False, repr=False)
    _connection: Any = field(default=None, init=False, repr=False)
    _in_txn: bool = field(default=False, init=False, repr=False)

    @classmethod
    def default(cls) -> "DbClient":
        return cls()

    @classmethod
    def for_datasource(cls, alias: str) -> "DbClient":
        """Create a client for a named datasource from ``config.env.DATABASES``."""
        return cls(settings=get_settings(alias))

    @property
    def dialect(self) -> str:
        """SQL dialect: ``"mssql"`` / ``"mysql"`` / ``"postgresql"``."""
        return self.settings.dialect

    def __enter__(self) -> "DbClient":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        conn = self._connection
        self._connection = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 -- closing must not mask the caller's error
                pass
        engine = self._engine
        self._engine = None
        if engine is not None:
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001 -- closing must not mask the caller's error
                pass

    def reset_connection(self) -> None:
        """Drop and reopen the connection (e.g. after SQL Server deadlock victim)."""
        conn = self._connection
        self._connection = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 -- a dead connection may fail to close; we reopen next
                pass
        self._ensure_open()

    def _ensure_open(self) -> None:
        if self._engine is None:
            self._engine = create_engine_for(self.settings)
        if self._connection is None:
            self._connection = self._engine.connect()
            return
        from sqlalchemy.exc import SQLAlchemyError

        try:
            self._connection.exec_driver_sql("SELECT 1").scalar()
            self._connection.rollback()
        except SQLAlchemyError:
            try:
                self._connection.close()
            except Exception:  # noqa: BLE001 -- the stale connection is replaced below either way
                pass
            self._connection = self._engine.connect()

    def _execute_raw(self, sql: str, params: _ParamType) -> Any:
        """Run SQL through the driver, preserving pyformat ``%s`` placeholders."""
        self._ensure_open()
        if params:
            if isinstance(params, Mapping):
                driver_params: Any = dict(params)
            else:
                driver_params = tuple(params)
            return self._connection.exec_driver_sql(sql, driver_params)
        return self._connection.exec_driver_sql(sql)

    def _maybe_commit(self) -> None:
        """Commit-as-you-go outside explicit transactions (autocommit semantics)."""
        if not self._in_txn and self._connection is not None:
            self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator["DbClient"]:
        """Run a block in an explicit transaction (commit / rollback)."""
        self._ensure_open()
        self._in_txn = True
        try:
            yield self
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            self._in_txn = False

    def fetch_all(self, sql: str, params: _ParamType = None) -> list[dict[str, Any]]:
        result = self._execute_raw(sql, params)
        rows = [dict(r) for r in result.mappings().all()]
        self._maybe_commit()
        return rows

    def fetch_one(self, sql: str, params: _ParamType = None) -> dict[str, Any] | None:
        result = self._execute_raw(sql, params)
        row = result.mappings().first()
        self._maybe_commit()
        return dict(row) if row else None

    def fetch_scalar(self, sql: str, params: _ParamType = None) -> Any:
        row = self.fetch_one(sql, params)
        if not row:
            return None
        return next(iter(row.values()))

    def execute(self, sql: str, params: _ParamType = None) -> int:
        result = self._execute_raw(sql, params)
        affected = int(result.rowcount or 0)
        self._maybe_commit()
        return affected

    def execute_many(self, sql: str, params_seq: Sequence[Sequence[Any] | Mapping[str, Any]]) -> int:
        """Execute ``sql`` once per parameter set (driver ``executemany``)."""
        if not params_seq:
            return 0
        self._ensure_open()
        driver_seq = [
            dict(p) if isinstance(p, Mapping) else tuple(p) for p in params_seq
        ]
        result = self._connection.exec_driver_sql(sql, driver_seq)
        affected = int(result.rowcount or 0)
        self._maybe_commit()
        return affected

    def mogrify(self, sql: str, params: _ParamType = None) -> str:
        """Return SQL with parameters interpolated (for samples / diagnostics only).

        Does not execute the statement. Prefer ``execute`` / ``fetch_*`` for
        real queries; use this when you need a literal string (e.g. commented
        sample ``INSERT`` in DDL dumps).
        """
        if params is None:
            return sql
        if isinstance(params, Mapping):
            rendered = sql
            for key, value in params.items():
                rendered = rendered.replace(
                    f"%({key})s", _sql_literal(value, dialect=self.dialect)
                )
            return rendered
        parts = sql.split("%s")
        if len(parts) - 1 != len(params):
            raise ValueError(
                f"mogrify placeholder count mismatch: sql has {len(parts) - 1} "
                f"%s, params has {len(params)}"
            )
        out: list[str] = [parts[0]]
        for i, value in enumerate(params):
            out.append(_sql_literal(value, dialect=self.dialect))
            out.append(parts[i + 1])
        return "".join(out)

    def iter_all(self, sql: str, params: _ParamType = None, *, batch_size: int = 500) -> Iterable[dict[str, Any]]:
        """Stream rows in batches; useful for large result sets."""
        result = self._execute_raw(sql, params)
        for partition in result.mappings().partitions(batch_size):
            for row in partition:
                yield dict(row)
        self._maybe_commit()

    def fetch_last_identity(self) -> int | None:
        if self.dialect == "mysql":
            value = self.fetch_scalar("SELECT LAST_INSERT_ID() AS id")
        elif self.dialect == "postgresql":
            value = self.fetch_scalar("SELECT lastval() AS id")
        else:
            value = self.fetch_scalar("SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS id")
        return int(value) if value is not None else None


# Backward-compatible alias; prefer ``DbClient``.
MySQLClient = DbClient
