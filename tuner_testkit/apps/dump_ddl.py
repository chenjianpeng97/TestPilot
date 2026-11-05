"""Dump table DDL (DataGrip "auto-generated definition" style) into ``knowledge/ddl``.

The framework supports MySQL, SQL Server, and PostgreSQL side by side;
datasources are named in ``config/env.py`` -> ``DATABASES`` (business alias ->
connection config incl. ``type``). Pick the target with ``--datasource``
(default ``main``); output is grouped per datasource under
``knowledge/ddl/<alias>/`` (pre-7.0 workspaces: ``assets/ddl`` until migrated).

For each requested table this writes ``knowledge/ddl/<alias>/<table>.sql``
containing:

1. A best-effort DataGrip-style ``create table`` definition:
   - MySQL: reconstructed from ``information_schema`` (lowercase keywords,
     backtick-free identifiers, aligned columns, inline single-column
     ``primary key``, ``unique`` constraints, generated columns, secondary
     ``create index`` statements, lowercased table options).
   - SQL Server: reconstructed from ``sys.*`` catalog views + ``MS_Description``
     extended properties (comments rendered as trailing ``--`` line comments).
   - PostgreSQL: reconstructed from ``pg_catalog`` (``format_type``, identity /
     generated columns, comments via ``obj_description`` / ``col_description``);
     secondary indexes emitted from ``pg_get_indexdef``. Default schema is
     ``public`` (override with ``--schema``).
2. A commented-out sample ``INSERT`` for the latest-id row, as a reference for
   data factories. Computed / generated columns and credential columns
   (``password`` / ``token`` / ``session_*`` / ``*_token`` / …) are omitted
   from the column list. Rows whose commented SQL would exceed a size cap
   (large ``stdout`` / jsonb) are replaced with a skip note.

All DB access goes through ``tuner_testkit.db.DbClient`` (repo rule). Exact
byte-for-byte parity with DataGrip is not guaranteed; this is a faithful
best-effort formatter for the common cases in this repo.

Run from the repo root::

    python -m tuner_testkit.apps.dump_ddl invoice invoice_verify_basic
    python -m tuner_testkit.apps.dump_ddl inout_detail --no-sample
    python -m tuner_testkit.apps.dump_ddl some_table --datasource sqlserver
    python -m tuner_testkit.apps.dump_ddl --all                 # every base table in the schema
    python -m tuner_testkit.apps.dump_ddl --all --datasource sqlserver --no-sample
    python -m tuner_testkit.apps.dump_ddl --all --datasource postgres --schema public
"""
from __future__ import annotations

import argparse
import pathlib
import re
from dataclasses import replace
from typing import Any

from tuner_testkit.apps._shared.changelog import append_entry
from tuner_testkit.db import DEFAULT_ALIAS, DbClient, get_settings
from tuner_testkit.logging import log_data_setup, log_error, log_info, log_warn
from tuner_testkit.project import ddl_dir, ensure_project_on_path

# Allow Unicode word chars (some tables carry CJK suffixes) plus `$`/`-`, while
# still rejecting backticks, quotes, spaces and other injection vectors.
_TABLE_RE = re.compile(r"[\w$]+", re.UNICODE)
_DB_RE = re.compile(r"[\w$-]+", re.UNICODE)
_NUMERIC_RE = re.compile(r"-?\d+(\.\d+)?")


def _q(identifier: str) -> str:
    """Backtick-quote a (already validated) identifier (MySQL)."""
    return f"`{identifier}`"


def _qb(identifier: str) -> str:
    """Bracket-quote a (already validated) identifier (SQL Server)."""
    return f"[{identifier}]"


def _qp(identifier: str) -> str:
    """Double-quote a (already validated) identifier (PostgreSQL)."""
    return '"' + identifier.replace('"', '""') + '"'


#: column names that must never appear in commented sample INSERTs
_SECRET_COL_EXACT = {
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "api_secret",
    "session_key",
    "session_data",
    "session_id",
    "token_data",
}
_SECRET_COL_SUFFIXES = (
    "_password",
    "_passwd",
    "_secret",
    "_token",
    "_cookie",
    "_api_key",
)
#: skip the whole sample when the commented INSERT would exceed this
_SAMPLE_MAX_CHARS = 4000


def _is_secret_column(name: str) -> bool:
    n = str(name).lower()
    if n in _SECRET_COL_EXACT:
        return True
    return any(n.endswith(suffix) for suffix in _SECRET_COL_SUFFIXES)


def _secret_column_names(column_names: list[str]) -> list[str]:
    names = [str(n) for n in column_names]
    secret = [n for n in names if _is_secret_column(n)]
    lower_map = {n.lower(): n for n in names}
    # encrypted KV stores (e.g. Plane instance_configurations): never dump value
    if "is_encrypted" in lower_map and "value" in lower_map:
        value_name = lower_map["value"]
        if value_name not in secret:
            secret.append(value_name)
    return secret


def _commented_sample_insert(
    *,
    table: str,
    order_col: str,
    insert_cols: list[str],
    secret_omitted: list[str],
    rendered: str,
    excluded_kind: str,
) -> str:
    """Format the commented sample block, or a skip note."""
    if not insert_cols:
        return f"-- （{table} 可插入列均为{excluded_kind}或密钥列，无示例 INSERT）"
    if len(rendered) > _SAMPLE_MAX_CHARS:
        return (
            f"-- （{table} 最新一行过长，已省略示例 INSERT；"
            "常见于 stdout / jsonb。需要样例时对该表单独查询）"
        )
    bits = [f"已排除{excluded_kind}"]
    if secret_omitted:
        bits.append("已排除密钥列 " + ", ".join(secret_omitted))
    header = (
        f"-- 最新一条数据示例（latest {order_col}），"
        + "，".join(bits)
        + "，仅供数据构造参考"
    )
    commented = "\n".join("-- " + line for line in rendered.splitlines())
    return header + "\n" + commented


def _lower_keys(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """information_schema may return UPPERCASE column labels; normalize to lower."""
    return [{str(k).lower(): v for k, v in row.items()} for row in rows]


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# MySQL builder (information_schema based)
# ---------------------------------------------------------------------------


def _fmt_type(column_type: str) -> str:
    """Lowercase MySQL type with a space after commas, e.g. ``decimal(32, 2)``."""
    t = re.sub(r",\s*", ", ", column_type.strip())
    if t == "char(1)":  # DataGrip renders the 1-length default width as `char`
        t = "char"
    return t


def _collate_clause(
    col: dict[str, Any],
    table_charset: str | None,
    table_collation: str | None,
    charset_default_collate: dict[str, str],
) -> str:
    cs = col.get("character_set_name")
    co = col.get("collation_name")
    if not cs or not co:
        return ""
    if cs != table_charset:
        if charset_default_collate.get(cs) == co:
            return f"charset {cs}"
        return f"collate {co}"
    if co != table_collation:
        return f"collate {co}"
    return ""


def _default_clause(col: dict[str, Any]) -> str:
    dv = col.get("column_default")
    if dv is None:
        return ""
    s = str(dv)
    up = s.upper()
    if up == "NULL":
        return ""
    if up.startswith("CURRENT_TIMESTAMP"):
        return "default CURRENT_TIMESTAMP"
    if _NUMERIC_RE.fullmatch(s):
        return f"default {s}"
    return f"default {_sql_string_literal(s)}"


def _load_charset_maps(db: DbClient) -> tuple[dict[str, str], dict[str, str]]:
    """Return (collation_to_charset, charset_to_default_collation)."""
    collation_to_charset: dict[str, str] = {}
    for row in _lower_keys(db.fetch_all(
        "SELECT collation_name, character_set_name FROM information_schema.collations"
    )):
        name = row.get("collation_name")
        charset = row.get("character_set_name")
        if name and charset:
            collation_to_charset[str(name)] = str(charset)

    charset_default_collate: dict[str, str] = {}
    for row in _lower_keys(db.fetch_all(
        "SELECT character_set_name, default_collate_name FROM information_schema.character_sets"
    )):
        charset = row.get("character_set_name")
        default_col = row.get("default_collate_name")
        if charset and default_col:
            charset_default_collate[str(charset)] = str(default_col)
    return collation_to_charset, charset_default_collate


def _fetch_schema_default_collation(db: DbClient, schema: str) -> str | None:
    row = db.fetch_one(
        "SELECT default_collation_name FROM information_schema.schemata "
        "WHERE schema_name = %s",
        (schema,),
    )
    if not row:
        return None
    row = {str(k).lower(): v for k, v in row.items()}
    value = row.get("default_collation_name")
    return str(value) if value else None


def _fetch_all_tables_mysql(db: DbClient, schema: str) -> list[str]:
    """All base tables (views excluded) in ``schema``, ordered by name."""
    rows = _lower_keys(db.fetch_all(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
        "ORDER BY table_name",
        (schema,),
    ))
    return [str(r["table_name"]) for r in rows]


def _fetch_table_meta(db: DbClient, schema: str, table: str) -> dict[str, Any] | None:
    row = db.fetch_one(
        "SELECT table_comment, row_format, table_collation "
        "FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return {str(k).lower(): v for k, v in row.items()} if row else None


def _fetch_columns(db: DbClient, schema: str, table: str) -> list[dict[str, Any]]:
    return _lower_keys(db.fetch_all(
        "SELECT column_name, column_type, is_nullable, column_default, extra, "
        "column_comment, generation_expression, character_set_name, collation_name "
        "FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position",
        (schema, table),
    ))


def _fetch_indexes(db: DbClient, schema: str, table: str) -> dict[str, dict[str, Any]]:
    """Group ``information_schema.statistics`` rows by index name."""
    rows = _lower_keys(db.fetch_all(
        "SELECT index_name, non_unique, seq_in_index, column_name "
        "FROM information_schema.statistics "
        "WHERE table_schema = %s AND table_name = %s "
        "ORDER BY index_name, seq_in_index",
        (schema, table),
    ))
    indexes: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = str(r["index_name"])
        entry = indexes.setdefault(name, {"non_unique": int(r["non_unique"]), "columns": []})
        entry["columns"].append(str(r["column_name"]))
    return indexes


def _build_column_entries(
    columns: list[dict[str, Any]],
    pk_columns: list[str],
    table_charset: str | None,
    table_collation: str | None,
    charset_default_collate: dict[str, str],
) -> list[str]:
    name_width = max((len(c["column_name"]) for c in columns), default=0) + 1

    rendered: list[dict[str, Any]] = []
    for col in columns:
        extra_lower = (col.get("extra") or "").lower()
        # Real generated columns expose a non-empty generation_expression; do not
        # rely on EXTRA, whose "DEFAULT_GENERATED" tag also contains "generated".
        is_generated = bool((col.get("generation_expression") or "").strip())
        is_auto_inc = "auto_increment" in extra_lower
        nullable = (col.get("is_nullable") or "").upper() == "YES"
        comment = col.get("column_comment") or ""

        type_seg = _fmt_type(col["column_type"])
        collate = _collate_clause(col, table_charset, table_collation, charset_default_collate)
        if collate:
            type_seg += " " + collate

        default_seg = ""
        on_update = ""
        tail_null: str | None
        if is_generated:
            expr = (col.get("generation_expression") or "").strip().replace("\\'", "'")
            kind = "stored" if "stored" in extra_lower else "virtual"
            type_seg += f" as ({expr}) {kind}"
            tail_null = None
        elif is_auto_inc:
            type_seg += " auto_increment"
            tail_null = None
        else:
            default_seg = _default_clause(col)
            if "on update" in extra_lower:
                on_update = "on update CURRENT_TIMESTAMP"
            tail_null = "null" if nullable else "not null"

        rendered.append(
            {
                "name": col["column_name"],
                "type_seg": type_seg,
                "default_seg": default_seg,
                "on_update": on_update,
                "tail_null": tail_null,
                "comment": comment,
            }
        )

    # DataGrip lays normal columns out as four aligned cells:
    #   name | type(+collate) | default(+on update) | null/not null [comment]
    normal = [r for r in rendered if r["tail_null"] is not None]
    with_default = [r for r in normal if r["default_seg"]]
    type_col_w = max((len(r["type_seg"]) for r in with_default), default=0)
    type_col_w = type_col_w + 1 if type_col_w else 0
    def_col_w = max((len(r["default_seg"]) for r in with_default), default=0)
    def_col_w = def_col_w + 1 if def_col_w else 0
    max_type_only = max((len(r["type_seg"]) for r in normal), default=0)
    null_off = max(type_col_w + def_col_w, max_type_only + 1)

    single_pk = pk_columns[0] if len(pk_columns) == 1 else None
    entries: list[str] = []
    for r in rendered:
        if r["tail_null"] is None:
            body = r["type_seg"]
        else:
            if r["default_seg"]:
                seg = f"{r['type_seg']:<{type_col_w}}{r['default_seg']:<{def_col_w}}"
            else:
                seg = r["type_seg"]
            body = f"{seg:<{null_off}}{r['tail_null']}"
            if r["on_update"]:
                body += f" {r['on_update']}"
        if r["comment"]:
            body += f" comment {_sql_string_literal(r['comment'])}"

        line = f"    {r['name']:<{name_width}}{body}"
        if single_pk is not None and r["name"] == single_pk:
            line += "\n        primary key"
        entries.append(line)

    return entries


def _build_ddl(
    table: str,
    columns: list[dict[str, Any]],
    indexes: dict[str, dict[str, Any]],
    table_meta: dict[str, Any],
    table_charset: str | None,
    charset_default_collate: dict[str, str],
    schema_default_collation: str | None,
) -> str:
    table_collation = table_meta.get("table_collation")
    pk_columns = indexes.get("PRIMARY", {}).get("columns", [])

    entries = _build_column_entries(
        columns, pk_columns, table_charset, table_collation, charset_default_collate
    )

    if len(pk_columns) > 1:
        entries.append(f"    primary key ({', '.join(pk_columns)})")

    secondary_indexes: list[tuple[str, list[str]]] = []
    for name, info in indexes.items():
        if name == "PRIMARY":
            continue
        if info["non_unique"] == 0:
            cols = ", ".join(info["columns"])
            entries.append(f"    constraint {name}\n        unique ({cols})")
        else:
            secondary_indexes.append((name, info["columns"]))

    body = ",\n".join(entries)

    # DataGrip emits a table-level `collate = X` on its own line when the table
    # collation differs from the schema default; comment + row_format share the
    # final line.
    option_lines: list[str] = []
    if (
        table_collation
        and schema_default_collation
        and table_collation != schema_default_collation
    ):
        if table_charset and charset_default_collate.get(table_charset) == table_collation:
            option_lines.append(f"charset = {table_charset}")
        else:
            option_lines.append(f"collate = {table_collation}")

    final_parts: list[str] = []
    table_comment = table_meta.get("table_comment") or ""
    if table_comment:
        final_parts.append(f"comment {_sql_string_literal(table_comment)}")
    row_format = table_meta.get("row_format")
    if row_format:
        final_parts.append(f"row_format = {str(row_format).upper()}")
    if final_parts:
        option_lines.append(" ".join(final_parts))

    lines = ["-- auto-generated definition", f"create table {table}", "(", body]
    if option_lines:
        lines.append(")")
        for opt in option_lines[:-1]:
            lines.append(f"    {opt}")
        lines.append(f"    {option_lines[-1]};")
    else:
        lines.append(");")

    ddl = "\n".join(lines)

    for name, cols in secondary_indexes:
        cols_joined = ", ".join(cols)
        ddl += f"\n\ncreate index {name}\n    on {table} ({cols_joined});"

    return ddl


def _build_sample_insert(
    db: DbClient,
    schema: str,
    table: str,
    columns: list[dict[str, Any]],
    indexes: dict[str, dict[str, Any]],
) -> str:
    pk_columns = indexes.get("PRIMARY", {}).get("columns", [])
    column_names = [c["column_name"] for c in columns]
    if len(pk_columns) == 1:
        order_col = pk_columns[0]
    elif "id" in column_names:
        order_col = "id"
    elif pk_columns:
        order_col = pk_columns[0]
    else:
        order_col = column_names[0]

    select_sql = (
        f"SELECT * FROM {_q(schema)}.{_q(table)} "
        f"ORDER BY {_q(order_col)} DESC LIMIT 1"
    )
    row = db.fetch_one(select_sql)
    if not row:
        return f"-- （{table} 暂无数据，无示例 INSERT）"

    generated = {
        c["column_name"]
        for c in columns
        if "generated" in (c.get("extra") or "").lower()
    }
    secret_omitted = _secret_column_names(column_names)
    skip = generated | set(secret_omitted)
    insert_cols = [c for c in column_names if c not in skip]
    if not insert_cols:
        return _commented_sample_insert(
            table=table,
            order_col=order_col,
            insert_cols=[],
            secret_omitted=secret_omitted,
            rendered="",
            excluded_kind="生成列",
        )
    cols_joined = ", ".join(_q(c) for c in insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    insert_sql = f"INSERT INTO {_q(table)} ({cols_joined}) VALUES ({placeholders})"
    values = tuple(row[c] for c in insert_cols)
    rendered = db.mogrify(insert_sql, values) + ";"
    return _commented_sample_insert(
        table=table,
        order_col=order_col,
        insert_cols=insert_cols,
        secret_omitted=secret_omitted,
        rendered=rendered,
        excluded_kind="生成列",
    )


def _dump_one_mysql(
    db: DbClient,
    schema: str,
    table: str,
    output_dir: pathlib.Path,
    *,
    with_sample: bool,
    table_charset: str | None,
    charset_default_collate: dict[str, str],
    schema_default_collation: str | None,
) -> bool:
    table_meta = _fetch_table_meta(db, schema, table)
    if table_meta is None:
        log_error("dump_ddl table not found", schema=schema, table=table)
        return False

    columns = _fetch_columns(db, schema, table)
    if not columns:
        log_error("dump_ddl table has no columns", schema=schema, table=table)
        return False

    indexes = _fetch_indexes(db, schema, table)
    ddl = _build_ddl(
        table,
        columns,
        indexes,
        table_meta,
        table_charset,
        charset_default_collate,
        schema_default_collation,
    )

    # DDL files end with a trailing blank line (existing convention); the sample
    # block, when present, sits below that blank line.
    content = ddl + "\n\n"
    has_sample = False
    if with_sample:
        sample = _build_sample_insert(db, schema, table, columns, indexes)
        content += sample + "\n"
        has_sample = "INSERT INTO" in sample

    out_path = output_dir / f"{table}.sql"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    log_data_setup(
        "ddl_dump",
        schema=schema,
        table=table,
        columns=len(columns),
        sample=has_sample,
        path=str(out_path),
    )
    return True


# ---------------------------------------------------------------------------
# SQL Server builder (sys.* catalog views based)
# ---------------------------------------------------------------------------

#: types whose length/precision/scale are rendered in parentheses
_MSSQL_LENGTH_TYPES = {"char", "varchar", "binary", "varbinary"}
_MSSQL_NLENGTH_TYPES = {"nchar", "nvarchar"}
_MSSQL_PRECISION_TYPES = {"decimal", "numeric"}
_MSSQL_SCALE_TYPES = {"datetime2", "datetimeoffset", "time"}


def _fetch_all_tables_mssql(db: DbClient) -> list[str]:
    rows = db.fetch_all("SELECT name FROM sys.tables ORDER BY name")
    return [str(r["name"]) for r in rows]


def _fetch_table_meta_mssql(db: DbClient, table: str) -> dict[str, Any] | None:
    row = db.fetch_one(
        "SELECT t.name AS table_name, CAST(ep.value AS NVARCHAR(4000)) AS table_comment "
        "FROM sys.tables t "
        "LEFT JOIN sys.extended_properties ep "
        "  ON ep.major_id = t.object_id AND ep.minor_id = 0 "
        "  AND ep.class = 1 AND ep.name = 'MS_Description' "
        "WHERE t.name = %s",
        (table,),
    )
    return row


def _fetch_columns_mssql(db: DbClient, table: str) -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT c.name AS column_name, ty.name AS type_name, c.max_length, "
        "c.precision, c.scale, c.is_nullable, c.is_identity, c.is_computed, "
        "dc.definition AS default_definition, cc.definition AS computed_definition, "
        "cc.is_persisted, c.collation_name, "
        "CAST(ep.value AS NVARCHAR(4000)) AS column_comment "
        "FROM sys.columns c "
        "JOIN sys.types ty ON ty.user_type_id = c.user_type_id "
        "LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id "
        "LEFT JOIN sys.computed_columns cc "
        "  ON cc.object_id = c.object_id AND cc.column_id = c.column_id "
        "LEFT JOIN sys.extended_properties ep "
        "  ON ep.major_id = c.object_id AND ep.minor_id = c.column_id "
        "  AND ep.class = 1 AND ep.name = 'MS_Description' "
        "WHERE c.object_id = OBJECT_ID(%s) "
        "ORDER BY c.column_id",
        (table,),
    )


def _fetch_indexes_mssql(db: DbClient, table: str) -> list[dict[str, Any]]:
    """One row per index with ordered column list."""
    rows = db.fetch_all(
        "SELECT i.name AS index_name, i.is_primary_key, i.is_unique, "
        "i.is_unique_constraint, ic.key_ordinal, col.name AS column_name "
        "FROM sys.indexes i "
        "JOIN sys.index_columns ic "
        "  ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
        "JOIN sys.columns col "
        "  ON col.object_id = ic.object_id AND col.column_id = ic.column_id "
        "WHERE i.object_id = OBJECT_ID(%s) AND i.type > 0 AND ic.key_ordinal > 0 "
        "ORDER BY i.index_id, ic.key_ordinal",
        (table,),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = str(r["index_name"])
        entry = grouped.setdefault(
            name,
            {
                "is_primary_key": bool(r["is_primary_key"]),
                "is_unique": bool(r["is_unique"]),
                "is_unique_constraint": bool(r["is_unique_constraint"]),
                "columns": [],
            },
        )
        entry["columns"].append(str(r["column_name"]))
    return [{"name": k, **v} for k, v in grouped.items()]


def _fmt_type_mssql(col: dict[str, Any]) -> str:
    t = str(col["type_name"]).lower()
    max_length = int(col.get("max_length") or 0)
    precision = int(col.get("precision") or 0)
    scale = int(col.get("scale") or 0)
    if t in _MSSQL_LENGTH_TYPES:
        return f"{t}(max)" if max_length == -1 else f"{t}({max_length})"
    if t in _MSSQL_NLENGTH_TYPES:
        return f"{t}(max)" if max_length == -1 else f"{t}({max_length // 2})"
    if t in _MSSQL_PRECISION_TYPES:
        return f"{t}({precision}, {scale})" if scale else f"{t}({precision})"
    if t in _MSSQL_SCALE_TYPES:
        return f"{t}({scale})"
    return t


def _default_clause_mssql(col: dict[str, Any]) -> str:
    """Render ``sys.default_constraints.definition`` (e.g. ``(('0'))``)."""
    definition = col.get("default_definition")
    if not definition:
        return ""
    s = str(definition).strip()
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    return f"default {s}"


def _build_ddl_mssql(
    table: str,
    columns: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
    table_meta: dict[str, Any],
) -> str:
    pk = next((i for i in indexes if i["is_primary_key"]), None)
    pk_columns: list[str] = pk["columns"] if pk else []

    rendered: list[dict[str, Any]] = []
    for col in columns:
        comment = col.get("column_comment") or ""
        if col.get("is_computed"):
            expr = str(col.get("computed_definition") or "").strip()
            kind = " persisted" if col.get("is_persisted") else ""
            type_seg = f"as {expr}{kind}"
            default_seg = ""
            tail_null = None
        else:
            type_seg = _fmt_type_mssql(col)
            if col.get("is_identity"):
                type_seg += " identity"
                default_seg = ""
                tail_null = None
            else:
                default_seg = _default_clause_mssql(col)
                tail_null = "null" if col.get("is_nullable") else "not null"
        rendered.append(
            {
                "name": str(col["column_name"]),
                "type_seg": type_seg,
                "default_seg": default_seg,
                "tail_null": tail_null,
                "comment": str(comment),
            }
        )

    name_width = max((len(r["name"]) for r in rendered), default=0) + 1
    normal = [r for r in rendered if r["tail_null"] is not None]
    with_default = [r for r in normal if r["default_seg"]]
    type_col_w = max((len(r["type_seg"]) for r in with_default), default=0)
    type_col_w = type_col_w + 1 if type_col_w else 0
    def_col_w = max((len(r["default_seg"]) for r in with_default), default=0)
    def_col_w = def_col_w + 1 if def_col_w else 0
    max_type_only = max((len(r["type_seg"]) for r in normal), default=0)
    null_off = max(type_col_w + def_col_w, max_type_only + 1)

    single_pk = pk_columns[0] if len(pk_columns) == 1 else None
    entries: list[str] = []
    for r in rendered:
        if r["tail_null"] is None:
            body = r["type_seg"]
        else:
            if r["default_seg"]:
                seg = f"{r['type_seg']:<{type_col_w}}{r['default_seg']:<{def_col_w}}"
            else:
                seg = r["type_seg"]
            body = f"{seg:<{null_off}}{r['tail_null']}"
        if r["comment"]:
            body += f" -- {r['comment']}"

        line = f"    {r['name']:<{name_width}}{body}"
        if single_pk is not None and r["name"] == single_pk:
            line += "\n        primary key"
        entries.append(line)

    if len(pk_columns) > 1:
        entries.append(f"    primary key ({', '.join(pk_columns)})")

    secondary_indexes: list[dict[str, Any]] = []
    for idx in indexes:
        if idx["is_primary_key"]:
            continue
        if idx["is_unique_constraint"]:
            cols = ", ".join(idx["columns"])
            entries.append(f"    constraint {idx['name']}\n        unique ({cols})")
        else:
            secondary_indexes.append(idx)

    body = ",\n".join(entries)

    lines = ["-- auto-generated definition"]
    table_comment = table_meta.get("table_comment") or ""
    if table_comment:
        lines.append(f"-- {table_comment}")
    lines += [f"create table {table}", "(", body, ");"]
    ddl = "\n".join(lines)

    for idx in secondary_indexes:
        cols_joined = ", ".join(idx["columns"])
        unique = "unique " if idx["is_unique"] else ""
        ddl += f"\n\ncreate {unique}index {idx['name']}\n    on {table} ({cols_joined});"

    return ddl


def _build_sample_insert_mssql(
    db: DbClient,
    table: str,
    columns: list[dict[str, Any]],
    pk_columns: list[str],
) -> str:
    column_names = [str(c["column_name"]) for c in columns]
    if len(pk_columns) == 1:
        order_col = pk_columns[0]
    elif "id" in column_names:
        order_col = "id"
    elif pk_columns:
        order_col = pk_columns[0]
    else:
        order_col = column_names[0]

    select_sql = (
        f"SELECT TOP 1 * FROM {_qb(table)} ORDER BY {_qb(order_col)} DESC"
    )
    row = db.fetch_one(select_sql)
    if not row:
        return f"-- （{table} 暂无数据，无示例 INSERT）"

    computed = {str(c["column_name"]) for c in columns if c.get("is_computed")}
    secret_omitted = _secret_column_names(column_names)
    skip = computed | set(secret_omitted)
    insert_cols = [c for c in column_names if c not in skip]
    if not insert_cols:
        return _commented_sample_insert(
            table=table,
            order_col=order_col,
            insert_cols=[],
            secret_omitted=secret_omitted,
            rendered="",
            excluded_kind="计算列",
        )
    cols_joined = ", ".join(_qb(c) for c in insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    insert_sql = f"INSERT INTO {_qb(table)} ({cols_joined}) VALUES ({placeholders})"
    values = tuple(row[c] for c in insert_cols)
    rendered = db.mogrify(insert_sql, values) + ";"
    return _commented_sample_insert(
        table=table,
        order_col=order_col,
        insert_cols=insert_cols,
        secret_omitted=secret_omitted,
        rendered=rendered,
        excluded_kind="计算列",
    )


def _dump_one_mssql(
    db: DbClient,
    schema: str,
    table: str,
    output_dir: pathlib.Path,
    *,
    with_sample: bool,
) -> bool:
    table_meta = _fetch_table_meta_mssql(db, table)
    if table_meta is None:
        log_error("dump_ddl table not found", schema=schema, table=table)
        return False

    columns = _fetch_columns_mssql(db, table)
    if not columns:
        log_error("dump_ddl table has no columns", schema=schema, table=table)
        return False

    indexes = _fetch_indexes_mssql(db, table)
    ddl = _build_ddl_mssql(table, columns, indexes, table_meta)

    content = ddl + "\n\n"
    has_sample = False
    if with_sample:
        pk = next((i for i in indexes if i["is_primary_key"]), None)
        sample = _build_sample_insert_mssql(db, table, columns, pk["columns"] if pk else [])
        content += sample + "\n"
        has_sample = "INSERT INTO" in sample

    out_path = output_dir / f"{table}.sql"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    log_data_setup(
        "ddl_dump",
        schema=schema,
        table=table,
        columns=len(columns),
        sample=has_sample,
        path=str(out_path),
    )
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ensure_project_on_path()
    parser = argparse.ArgumentParser(
        description="Dump table DDL + sample INSERT into knowledge/ddl/<datasource>/<table>.sql",
    )
    parser.add_argument(
        "tables",
        nargs="*",
        help="one or more table names (omit when using --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="dump every base table in the schema (views excluded)",
    )
    parser.add_argument(
        "--datasource",
        default=DEFAULT_ALIAS,
        help=f"named datasource alias from config/env.py DATABASES (default: {DEFAULT_ALIAS})",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="override database name within the datasource instance",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="PostgreSQL schema to dump (default: public). Ignored for MySQL / SQL Server.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory (default: <repo>/knowledge/ddl/<datasource>)",
    )
    parser.add_argument(
        "--no-sample",
        action="store_true",
        help="do not append the sample INSERT block",
    )
    args = parser.parse_args(argv)

    if not args.all and not args.tables:
        parser.error("provide table name(s) or use --all")

    settings = get_settings(args.datasource)
    if args.db:
        if not _DB_RE.fullmatch(args.db):
            log_error("dump_ddl invalid --db", db=args.db)
            return 2
        settings = replace(settings, database=args.db)
    schema = settings.database

    output_dir = (
        pathlib.Path(args.output_dir)
        if args.output_dir
        else ddl_dir() / args.datasource
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    written: list[str] = []
    with DbClient(settings=settings) as db:
        dialect = db.dialect
        collation_to_charset: dict[str, str] = {}
        charset_default_collate: dict[str, str] = {}
        schema_default_collation: str | None = None
        if dialect == "mysql":
            collation_to_charset, charset_default_collate = _load_charset_maps(db)
            schema_default_collation = _fetch_schema_default_collation(db, schema)
            tables = _fetch_all_tables_mysql(db, schema) if args.all else args.tables
        elif dialect == "mssql":
            tables = _fetch_all_tables_mssql(db) if args.all else args.tables
        elif dialect == "postgresql":
            schema = args.schema or "public"
            if not _DB_RE.fullmatch(schema):
                log_error("dump_ddl invalid --schema", schema=schema)
                return 2
            tables = (
                _fetch_all_tables_postgres(db, schema) if args.all else args.tables
            )
        else:
            log_error("dump_ddl unsupported dialect", dialect=dialect)
            return 2

        log_info(
            "dump_ddl start",
            datasource=args.datasource,
            dialect=dialect,
            schema=schema,
            tables=len(tables),
            mode="all" if args.all else "explicit",
            output_dir=str(output_dir),
            sample=not args.no_sample,
        )

        for table in tables:
            if not _TABLE_RE.fullmatch(table):
                log_error("dump_ddl skip invalid table name", table=table)
                continue
            try:
                if dialect == "mysql":
                    table_meta = _fetch_table_meta(db, schema, table)
                    table_collation = table_meta.get("table_collation") if table_meta else None
                    table_charset = (
                        collation_to_charset.get(str(table_collation))
                        if table_collation
                        else None
                    )
                    done = _dump_one_mysql(
                        db,
                        schema,
                        table,
                        output_dir,
                        with_sample=not args.no_sample,
                        table_charset=table_charset,
                        charset_default_collate=charset_default_collate,
                        schema_default_collation=schema_default_collation,
                    )
                elif dialect == "mssql":
                    done = _dump_one_mssql(
                        db,
                        schema,
                        table,
                        output_dir,
                        with_sample=not args.no_sample,
                    )
                else:
                    done = _dump_one_postgres(
                        db,
                        schema,
                        table,
                        output_dir,
                        with_sample=not args.no_sample,
                    )
                if done:
                    ok += 1
                    written.append(table)
            except Exception as exc:  # noqa: BLE001 -- per-table isolation
                log_error("dump_ddl failed", table=table, error=str(exc))

        total = len(tables)

    # Auto-area changelog: one line per run so `maintain-index` can update
    # INDEX.project.md from the delta without re-reading every generated .sql body.
    if written:
        append_entry(
            ddl_dir() / "CHANGELOG.md",
            tool="dump_ddl",
            action="dump-ddl",
            items=written,
            datasource=args.datasource,
            schema=schema,
            count=len(written),
        )

    failed = total - ok
    if failed:
        log_warn("dump_ddl finished with failures", ok=ok, failed=failed)
    else:
        log_info("dump_ddl finished", ok=ok)
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# PostgreSQL builder (pg_catalog based)
# ---------------------------------------------------------------------------


def _fetch_all_tables_postgres(db: DbClient, schema: str) -> list[str]:
    rows = db.fetch_all(
        "SELECT c.relname AS table_name "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind = 'r' "
        "ORDER BY c.relname",
        (schema,),
    )
    return [str(r["table_name"]) for r in rows]


def _fetch_table_meta_postgres(
    db: DbClient, schema: str, table: str
) -> dict[str, Any] | None:
    return db.fetch_one(
        "SELECT c.relname AS table_name, "
        "obj_description(c.oid) AS table_comment "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s AND c.relkind = 'r'",
        (schema, table),
    )


def _fetch_columns_postgres(
    db: DbClient, schema: str, table: str
) -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT a.attname AS column_name, "
        "pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type, "
        "NOT a.attnotnull AS is_nullable, "
        "pg_get_expr(ad.adbin, ad.adrelid) AS default_expr, "
        "a.attidentity AS identity_kind, "
        "a.attgenerated AS generated_kind, "
        "col_description(c.oid, a.attnum) AS column_comment "
        "FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_attrdef ad "
        "  ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum "
        "WHERE n.nspname = %s AND c.relname = %s "
        "  AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY a.attnum",
        (schema, table),
    )


def _fetch_pk_columns_postgres(db: DbClient, schema: str, table: str) -> list[str]:
    rows = db.fetch_all(
        "SELECT a.attname AS column_name "
        "FROM pg_index i "
        "JOIN pg_class t ON t.oid = i.indrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS x(attnum, ord) ON true "
        "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.attnum "
        "WHERE n.nspname = %s AND t.relname = %s AND i.indisprimary "
        "ORDER BY x.ord",
        (schema, table),
    )
    return [str(r["column_name"]) for r in rows]


def _fetch_secondary_indexdefs_postgres(
    db: DbClient, schema: str, table: str
) -> list[str]:
    rows = db.fetch_all(
        "SELECT pg_get_indexdef(i.indexrelid) AS indexdef "
        "FROM pg_index i "
        "JOIN pg_class t ON t.oid = i.indrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = %s AND t.relname = %s AND NOT i.indisprimary "
        "ORDER BY pg_get_indexdef(i.indexrelid)",
        (schema, table),
    )
    return [str(r["indexdef"]) for r in rows if r.get("indexdef")]


def _fmt_type_postgres(formatted_type: str) -> str:
    t = (formatted_type or "").strip()
    t = t.replace("character varying", "varchar")
    t = t.replace("timestamp with time zone", "timestamptz")
    t = t.replace("timestamp without time zone", "timestamp")
    t = t.replace("time with time zone", "timetz")
    t = t.replace("time without time zone", "time")
    t = t.replace("character(", "char(")
    return t


def _default_clause_postgres(default_expr: Any) -> str:
    if default_expr is None:
        return ""
    s = str(default_expr).strip()
    if not s or s.upper() == "NULL":
        return ""
    return f"default {s}"


def _normalize_pg_indexdef(indexdef: str, schema: str) -> str:
    text = indexdef.strip().rstrip(";")
    needle = f" ON {schema}."
    if needle in text:
        text = text.replace(needle, " ON ", 1)
    return text + ";"


def _build_ddl_postgres(
    table: str,
    columns: list[dict[str, Any]],
    pk_columns: list[str],
    indexdefs: list[str],
    table_meta: dict[str, Any],
    schema: str,
) -> str:
    rendered: list[dict[str, Any]] = []
    for col in columns:
        comment = col.get("column_comment") or ""
        identity_kind = str(col.get("identity_kind") or "")
        generated_kind = str(col.get("generated_kind") or "")
        if generated_kind:
            expr = str(col.get("default_expr") or "").strip()
            type_seg = f"{_fmt_type_postgres(str(col.get('formatted_type') or ''))} generated always as ({expr}) stored"
            default_seg = ""
            tail_null = None
        else:
            type_seg = _fmt_type_postgres(str(col.get("formatted_type") or ""))
            if identity_kind == "a":
                type_seg += " generated always as identity"
                default_seg = ""
                tail_null = None
            elif identity_kind == "d":
                type_seg += " generated by default as identity"
                default_seg = ""
                tail_null = None
            else:
                default_seg = _default_clause_postgres(col.get("default_expr"))
                tail_null = "null" if col.get("is_nullable") else "not null"
        rendered.append(
            {
                "name": str(col["column_name"]),
                "type_seg": type_seg,
                "default_seg": default_seg,
                "tail_null": tail_null,
                "comment": str(comment),
            }
        )

    name_width = max((len(r["name"]) for r in rendered), default=0) + 1
    normal = [r for r in rendered if r["tail_null"] is not None]
    with_default = [r for r in normal if r["default_seg"]]
    type_col_w = max((len(r["type_seg"]) for r in with_default), default=0)
    type_col_w = type_col_w + 1 if type_col_w else 0
    def_col_w = max((len(r["default_seg"]) for r in with_default), default=0)
    def_col_w = def_col_w + 1 if def_col_w else 0
    max_type_only = max((len(r["type_seg"]) for r in normal), default=0)
    null_off = max(type_col_w + def_col_w, max_type_only + 1)

    single_pk = pk_columns[0] if len(pk_columns) == 1 else None
    entries: list[str] = []
    for r in rendered:
        if r["tail_null"] is None:
            body = r["type_seg"]
        else:
            if r["default_seg"]:
                seg = f"{r['type_seg']:<{type_col_w}}{r['default_seg']:<{def_col_w}}"
            else:
                seg = r["type_seg"]
            body = f"{seg:<{null_off}}{r['tail_null']}"
        if r["comment"]:
            body += f" -- {r['comment']}"
        line = f"    {r['name']:<{name_width}}{body}"
        if single_pk is not None and r["name"] == single_pk:
            line += "\n        primary key"
        entries.append(line)

    if len(pk_columns) > 1:
        entries.append(f"    primary key ({', '.join(pk_columns)})")

    body = ",\n".join(entries)
    lines = ["-- auto-generated definition"]
    table_comment = table_meta.get("table_comment") or ""
    if table_comment:
        lines.append(f"-- {table_comment}")
    lines += [f"create table {table}", "(", body, ");"]
    ddl = "\n".join(lines)

    for indexdef in indexdefs:
        ddl += f"\n\n{_normalize_pg_indexdef(indexdef, schema)}"
    return ddl


def _build_sample_insert_postgres(
    db: DbClient,
    schema: str,
    table: str,
    columns: list[dict[str, Any]],
    pk_columns: list[str],
) -> str:
    column_names = [str(c["column_name"]) for c in columns]
    if len(pk_columns) == 1:
        order_col = pk_columns[0]
    elif "id" in column_names:
        order_col = "id"
    elif pk_columns:
        order_col = pk_columns[0]
    else:
        order_col = column_names[0]

    qualified = f"{_qp(schema)}.{_qp(table)}"
    select_sql = (
        f"SELECT * FROM {qualified} ORDER BY {_qp(order_col)} DESC LIMIT 1"
    )
    row = db.fetch_one(select_sql)
    if not row:
        return f"-- （{table} 暂无数据，无示例 INSERT）"

    generated = {
        str(c["column_name"])
        for c in columns
        if str(c.get("generated_kind") or "")
    }
    secret_omitted = _secret_column_names(column_names)
    skip = generated | set(secret_omitted)
    insert_cols = [c for c in column_names if c not in skip]
    if not insert_cols:
        return _commented_sample_insert(
            table=table,
            order_col=order_col,
            insert_cols=[],
            secret_omitted=secret_omitted,
            rendered="",
            excluded_kind="生成列",
        )
    cols_joined = ", ".join(_qp(c) for c in insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    insert_sql = f"INSERT INTO {_qp(table)} ({cols_joined}) VALUES ({placeholders})"
    values = tuple(row[c] for c in insert_cols)
    rendered = db.mogrify(insert_sql, values) + ";"
    return _commented_sample_insert(
        table=table,
        order_col=order_col,
        insert_cols=insert_cols,
        secret_omitted=secret_omitted,
        rendered=rendered,
        excluded_kind="生成列",
    )


def _dump_one_postgres(
    db: DbClient,
    schema: str,
    table: str,
    output_dir: pathlib.Path,
    *,
    with_sample: bool,
) -> bool:
    table_meta = _fetch_table_meta_postgres(db, schema, table)
    if table_meta is None:
        log_error("dump_ddl table not found", schema=schema, table=table)
        return False

    columns = _fetch_columns_postgres(db, schema, table)
    if not columns:
        log_error("dump_ddl table has no columns", schema=schema, table=table)
        return False

    pk_columns = _fetch_pk_columns_postgres(db, schema, table)
    indexdefs = _fetch_secondary_indexdefs_postgres(db, schema, table)
    ddl = _build_ddl_postgres(
        table, columns, pk_columns, indexdefs, table_meta, schema
    )

    content = ddl + "\n\n"
    has_sample = False
    if with_sample:
        sample = _build_sample_insert_postgres(
            db, schema, table, columns, pk_columns
        )
        content += sample + "\n"
        has_sample = "INSERT INTO" in sample

    out_path = output_dir / f"{table}.sql"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    log_data_setup(
        "ddl_dump",
        schema=schema,
        table=table,
        columns=len(columns),
        sample=has_sample,
        path=str(out_path),
    )
    return True


if __name__ == "__main__":
    raise SystemExit(main())
