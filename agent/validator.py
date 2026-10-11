"""SQL validator: the gate between LLM-written SQL and the database (defense in depth, layer 4).

Allows exactly one read-only SELECT over allowlisted ops.* tables and columns, with no dangerous
functions, and forces a row LIMIT. Failures carry a `kind` so the repair loop can react to each
failure class differently (Phase 4). This is NOT the security boundary (the read-only DB role is);
it gives fast, specific error messages and stops obviously bad SQL before it costs a round trip.
"""
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify

from agent.schema import load_schema

MAX_ROWS = 200
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Merge,
                   exp.Command, exp.Into, exp.Lock)
FORBIDDEN_FUNCTIONS = {"pg_sleep", "set_config", "dblink", "lo_import", "lo_export", "copy",
                       "nextval", "setval", "currval", "lastval"}  # sequence functions change state
FORBIDDEN_PREFIXES = ("pg_", "lo_", "dblink")


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""  # the rewritten SQL to execute (LIMIT enforced); empty when not ok
    kind: str = ""  # syntax | multiple_statements | not_select | forbidden | unqualified_table | unknown_table | unknown_column
    errors: list[str] = field(default_factory=list)


def _fail(kind: str, message: str) -> ValidationResult:
    return ValidationResult(False, "", kind, [message])


def validate(sql: str, max_rows: int = MAX_ROWS) -> ValidationResult:
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        return _fail("syntax", f"SQL syntax error: {str(e).splitlines()[0]}")
    if not statements:
        return _fail("syntax", "Empty SQL.")
    if len(statements) > 1:
        return _fail("multiple_statements", "Only one statement is allowed.")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        return _fail("not_select", f"Only SELECT queries are allowed, got {type(tree).__name__}.")
    bad = next(tree.find_all(*FORBIDDEN_NODES), None)
    if bad is not None:
        return _fail("not_select", f"Forbidden construct: {type(bad).__name__}.")

    for func in tree.find_all(exp.Func):
        name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
        if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_PREFIXES):
            return _fail("forbidden", f"Function {name} is not allowed.")

    schema = load_schema()["ops"]
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.name in ctes and not table.db:
            continue
        if not table.db:
            return _fail("unqualified_table", f"Table {table.name} must be schema-qualified as ops.{table.name}.")
        if table.db != "ops" or table.name not in schema:
            return _fail("unknown_table", f"Table {table.db}.{table.name} does not exist or is not allowed. "
                                          f"Allowed tables: {', '.join('ops.' + t for t in sorted(schema))}.")

    try:
        qualify(tree.copy(), schema=load_schema(), dialect="postgres", validate_qualify_columns=True)
    except OptimizeError as e:
        return _fail("unknown_column", str(e))
    except SqlglotError as e:
        return _fail("syntax", f"Could not analyse the query: {e}")

    limit = tree.args.get("limit")
    current = limit.expression.this if limit is not None and limit.expression is not None else None
    if current is None or not str(current).isdigit() or int(current) > max_rows:
        tree = tree.limit(max_rows)
    return ValidationResult(True, tree.sql(dialect="postgres"))
