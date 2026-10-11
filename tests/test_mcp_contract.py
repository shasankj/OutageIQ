"""Contract tests: the real MCP server over a real stdio subprocess, with the fake backend
(no database). They pin the tool names, input schemas and the error shape the agent relies on."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent


def server_params():
    return StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=ROOT,
                                 env={"OUTAGEIQ_MCP_BACKEND": "fake"})


def payload(result) -> dict:
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(next(c.text for c in result.content if c.type == "text"))


async def call(tool, args):
    async with Client(server_params()) as client:
        return payload(await client.call_tool(tool, args))


def test_tool_names_and_input_schemas():
    async def go():
        async with Client(server_params()) as client:
            return (await client.list_tools()).tools
    tools = {t.name: t for t in asyncio.run(go())}
    assert set(tools) == {"run_query", "explain_query", "describe_table"}
    assert tools["run_query"].input_schema["required"] == ["sql"]
    assert tools["describe_table"].input_schema["required"] == ["table"]


def test_run_query_success_shape():
    r = asyncio.run(call("run_query", {"sql": "SELECT o.outage_id FROM ops.outages o WHERE o.outage_id = 1234"}))
    assert r["ok"] is True and r["rows"] == [[1234]] and r["columns"][0]["name"] == "outage_id"
    assert "LIMIT 200" in r["sql_executed"]  # the validator forces a row cap


@pytest.mark.parametrize("sql,kind", [
    ("DELETE FROM ops.outages", "not_select"),
    ("SELECT 1; SELECT 2", "multiple_statements"),
    ("SELECT * FROM rag.chunks", "unknown_table"),
    ("SELECT o.end_date FROM ops.outages o", "unknown_column"),
])
def test_run_query_refuses_bad_sql_with_a_stable_error_kind(sql, kind):
    r = asyncio.run(call("run_query", {"sql": sql}))
    assert r["ok"] is False and r["error_kind"] == kind and r["message"]


def test_describe_table():
    r = asyncio.run(call("describe_table", {"table": "ops.tickets"}))
    assert r["ok"] and "ticket_number" in [c["name"] for c in r["columns"]]
    assert asyncio.run(call("describe_table", {"table": "pg_user"}))["error_kind"] == "unknown_table"


def test_explain_query():
    r = asyncio.run(call("explain_query", {"sql": "SELECT o.outage_id FROM ops.outages o"}))
    assert r["ok"] and r["total_cost"] >= 0
