"""Backends for the read-only MCP server.

PostgresBackend runs as outageiq_reader (SELECT-only role): validator -> EXPLAIN cost gate ->
execution with a statement timeout and a row cap. FakeBackend serves canned data so the MCP
protocol (tool schemas, error shape, stdio round trip) can be contract-tested with no database.

Every tool returns a dict with `ok`. Failures carry `error_kind` (a stable vocabulary the agent's
repair loop switches on) and a human-readable `message`.
"""
import datetime as dt
import decimal
import logging

import psycopg
from psycopg import errors as pg_errors
from psycopg.postgres import types as pg_types

from agent.schema import load_schema
from agent.validator import validate

log = logging.getLogger("outageiq.mcp")  # stderr only: stdout is the stdio protocol channel

MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 10_000
PLAN_COST_LIMIT = 100_000  # planner cost units; the whole database is far below this


def to_json_value(v):
    """JSON-safe cell values. Timestamps stay ISO strings with offset; durations become seconds."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


_ERROR_KINDS = [
    (pg_errors.UndefinedColumn, "unknown_column"),
    (pg_errors.UndefinedTable, "unknown_table"),
    (pg_errors.AmbiguousColumn, "ambiguous_column"),
    (pg_errors.SyntaxError, "syntax"),
    (pg_errors.QueryCanceled, "timeout"),
    (pg_errors.DatatypeMismatch, "type_mismatch"),
    (pg_errors.InvalidTextRepresentation, "type_mismatch"),
    (pg_errors.UndefinedFunction, "type_mismatch"),
    (pg_errors.DivisionByZero, "runtime_error"),
    (pg_errors.InsufficientPrivilege, "permission_denied"),
]


def classify_db_error(exc: Exception) -> str:
    for cls, kind in _ERROR_KINDS:
        if isinstance(exc, cls):
            return kind
    return "db_error"


def _failure(kind: str, message: str, **extra) -> dict:
    return {"ok": False, "error_kind": kind, "message": message, **extra}


class PostgresBackend:
    def _connect(self):
        from common.db import connect
        return connect("reader")

    def run_query(self, sql: str) -> dict:
        v = validate(sql)
        if not v.ok:
            return _failure(v.kind, "; ".join(v.errors))
        try:
            with self._connect() as conn:
                conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                plan = conn.execute("EXPLAIN (FORMAT JSON) " + v.sql).fetchone()[0]
                cost = plan[0]["Plan"]["Total Cost"]
                if cost > PLAN_COST_LIMIT:
                    return _failure("too_expensive", f"Estimated plan cost {cost:.0f} exceeds the limit "
                                                     f"{PLAN_COST_LIMIT}. Remove cross joins or add filters.")
                cur = conn.execute(v.sql)
                rows = cur.fetchmany(MAX_ROWS)
                columns = [{"name": d.name, "type": pg_types.get(d.type_code).name if pg_types.get(d.type_code) else str(d.type_code)}
                           for d in cur.description]
        except psycopg.Error as e:
            kind = classify_db_error(e)
            log.warning("query failed (%s): %s", kind, str(e).splitlines()[0])
            return _failure(kind, str(e).splitlines()[0], sqlstate=getattr(e, "sqlstate", None))
        return {"ok": True, "sql_executed": v.sql, "columns": columns,
                "rows": [[to_json_value(c) for c in row] for row in rows],
                "row_count": len(rows), "truncated": len(rows) >= MAX_ROWS, "plan_cost": cost}

    def explain(self, sql: str) -> dict:
        v = validate(sql)
        if not v.ok:
            return _failure(v.kind, "; ".join(v.errors))
        try:
            with self._connect() as conn:
                plan = conn.execute("EXPLAIN (FORMAT JSON) " + v.sql).fetchone()[0][0]["Plan"]
        except psycopg.Error as e:
            return _failure(classify_db_error(e), str(e).splitlines()[0])
        return {"ok": True, "sql_checked": v.sql, "total_cost": plan["Total Cost"],
                "estimated_rows": plan["Plan Rows"], "node_type": plan["Node Type"]}

    def describe(self, table: str) -> dict:
        name = table.removeprefix("ops.")
        if name not in load_schema()["ops"]:
            return _failure("unknown_table", f"Unknown table {table!r}. "
                                             f"Tables: {', '.join(sorted(load_schema()['ops']))}")
        try:
            with self._connect() as conn:
                cols = conn.execute(
                    "SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, "
                    "col_description(a.attrelid, a.attnum) FROM pg_attribute a "
                    "WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
                    (f"ops.{name}",)).fetchall()
                (comment,) = conn.execute("SELECT obj_description(%s::regclass, 'pg_class')", (f"ops.{name}",)).fetchone()
        except psycopg.Error as e:
            return _failure(classify_db_error(e), str(e).splitlines()[0])
        return {"ok": True, "table": f"ops.{name}", "comment": comment,
                "columns": [{"name": n, "type": t, "nullable": nl, "comment": c} for n, t, nl, c in cols]}


class FakeBackend:
    """Deterministic stand-in for contract tests. Same validation, canned data."""

    def run_query(self, sql: str) -> dict:
        v = validate(sql)
        if not v.ok:
            return _failure(v.kind, "; ".join(v.errors))
        return {"ok": True, "sql_executed": v.sql, "columns": [{"name": "outage_id", "type": "int8"}],
                "rows": [[1234]], "row_count": 1, "truncated": False, "plan_cost": 1.0}

    def explain(self, sql: str) -> dict:
        v = validate(sql)
        if not v.ok:
            return _failure(v.kind, "; ".join(v.errors))
        return {"ok": True, "sql_checked": v.sql, "total_cost": 1.0, "estimated_rows": 1, "node_type": "Seq Scan"}

    def describe(self, table: str) -> dict:
        name = table.removeprefix("ops.")
        cols = load_schema()["ops"].get(name)
        if cols is None:
            return _failure("unknown_table", f"Unknown table {table!r}.")
        return {"ok": True, "table": f"ops.{name}", "comment": None,
                "columns": [{"name": c, "type": "text", "nullable": True, "comment": None} for c in cols]}
