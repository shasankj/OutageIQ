"""Read-only OutageIQ MCP server (stdio). Run: python -m mcp_server.server

Tools: run_query, explain_query, describe_table. All are read-only by construction:
validator (one SELECT, allowlisted ops.* tables/columns) -> EXPLAIN cost gate -> execution as the
SELECT-only database role with a statement timeout and a row cap. Set OUTAGEIQ_MCP_BACKEND=fake
for contract tests that must not touch the database.
"""
import logging
import os
import sys

from mcp.server import MCPServer

from mcp_server.backends import FakeBackend, PostgresBackend

logging.basicConfig(level=logging.INFO, stream=sys.stderr)  # never stdout: it carries the protocol

mcp = MCPServer(
    "outageiq-readonly",
    instructions=("Read-only access to the OutageIQ operational database (schema ops). "
                  "Send one PostgreSQL SELECT per call; tables must be schema-qualified (ops.outages)."),
)
backend = FakeBackend() if os.environ.get("OUTAGEIQ_MCP_BACKEND") == "fake" else PostgresBackend()


@mcp.tool()
def run_query(sql: str) -> dict:
    """Run one read-only SELECT over the ops schema and return its rows (max 200).

    On failure returns ok=false with error_kind (syntax, multiple_statements, not_select, forbidden,
    unqualified_table, unknown_table, unknown_column, ambiguous_column, type_mismatch, timeout,
    too_expensive, permission_denied, db_error) and a message.
    """
    return backend.run_query(sql)


@mcp.tool()
def explain_query(sql: str) -> dict:
    """Validate a SELECT and return the planner's cost and row estimate without running it."""
    return backend.explain(sql)


@mcp.tool()
def describe_table(table: str) -> dict:
    """Return the columns, types, nullability and comments of one ops table (e.g. 'ops.outages')."""
    return backend.describe(table)


if __name__ == "__main__":
    mcp.run()
