"""Structure checks for the knowledge file (offline: no database needed)."""
import re
from pathlib import Path

import pytest

from common.knowledge import load_sections

MIGRATION = Path(__file__).resolve().parent.parent / "db" / "migrations" / "0001_ops_schema.sql"
FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT)\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def sections():
    return load_sections()


def test_every_section_has_meta(sections):
    for s in sections:
        if s.body:  # container headings such as "3. Tables" have no body of their own
            assert s.meta.get("type"), f"no meta on: {s.heading}"


def test_every_migrated_table_is_documented(sections):
    in_db = set(re.findall(r"CREATE TABLE ops\.(\w+)", MIGRATION.read_text()))
    documented = {s.heading.removeprefix("Table ops.") for s in sections if s.heading.startswith("Table ops.")}
    assert in_db == documented


def test_table_sections_mention_every_column(sections):
    ddl = MIGRATION.read_text()
    for s in sections:
        if not s.heading.startswith("Table ops."):
            continue
        table = s.heading.removeprefix("Table ops.")
        block = re.search(rf"CREATE TABLE ops\.{table} \((.*?)\n\);", ddl, re.DOTALL).group(1)
        columns = [m.group(1) for m in re.finditer(r"^\s{2}([a-z_]+)\s+(?:bigint|text|char|boolean|integer|timestamptz)", block, re.MULTILINE)]
        for col in columns:
            if col == "created_by":
                continue  # pure audit column, documented once in the outages table row
            if col in ("created_at", "updated_at") and table != "tickets":
                continue  # audit columns; on tickets they are business times and must be documented
            assert f"`{col}`" in s.body or f"| {col} " in s.body or f"{col}," in s.body, f"{table}.{col} undocumented"


def test_examples_are_single_read_only_selects(sections):
    examples = [s for s in sections if s.meta.get("type") == "example"]
    assert len(examples) >= 15
    for s in examples:
        assert s.sql_blocks, s.heading
        for sql in s.sql_blocks:
            assert sql.upper().startswith("SELECT"), s.heading
            assert sql.count(";") == 1 and sql.endswith(";"), s.heading
            assert not FORBIDDEN.search(sql), s.heading
            assert "now()" not in sql.lower(), s.heading
            assert "ops." in sql, s.heading
