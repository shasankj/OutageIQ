"""The allowlisted schema (table -> columns), parsed from the migration so it cannot drift."""
import re
from functools import cache
from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "db" / "migrations" / "0001_ops_schema.sql"
_COLUMN = re.compile(r"^\s{2}([a-z_]+)\s+(?:bigint|text|char|boolean|integer|timestamptz)", re.MULTILINE)


@cache
def load_schema() -> dict[str, dict[str, dict[str, str]]]:
    """{'ops': {'outages': {'outage_id': 'text', ...}, ...}} in the shape sqlglot expects."""
    ddl = MIGRATION.read_text()
    tables = {}
    for m in re.finditer(r"CREATE TABLE ops\.(\w+) \((.*?)\n\);", ddl, re.DOTALL):
        tables[m.group(1)] = {c: "text" for c in _COLUMN.findall(m.group(2))}
    return {"ops": tables}
