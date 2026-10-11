"""Tool access for the agent. The agent never touches the database directly: it calls the MCP server
(a separate stdio process running as the SELECT-only role). `SQLTools` is the seam tests replace."""
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Protocol

from mcp import Client, StdioServerParameters

from agent.config import AgentConfig

ROOT = Path(__file__).resolve().parent.parent


class SQLTools(Protocol):
    async def run_query(self, sql: str) -> dict: ...


def _payload(result) -> dict:
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(next(c.text for c in result.content if c.type == "text"))


class MCPTools:
    """Spawns the MCP server once and keeps the session open for the agent's lifetime."""

    def __init__(self, fake_backend: bool = False):
        env = {"OUTAGEIQ_MCP_BACKEND": "fake"} if fake_backend else None
        self._params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"],
                                             cwd=ROOT, env=env)
        self._stack = AsyncExitStack()
        self._client: Client | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        self._client = await self._stack.enter_async_context(Client(self._params))
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def run_query(self, sql: str) -> dict:
        async with self._lock:  # one request at a time on the stdio pipe
            return _payload(await self._client.call_tool("run_query", {"sql": sql}))


async def retrieve_context_async(question: str, extra: str, widen: bool, cfg: AgentConfig) -> list[dict]:
    """Type-aware retrieval in a worker thread (Voyage + Postgres calls are blocking)."""
    from rag.retriever import retrieve_context

    query = f"{question}\n{extra}" if extra else question
    hits = await asyncio.to_thread(
        retrieve_context, query, cfg.tables_k + (3 if widen else 0), cfg.structure_k, cfg.examples_k)
    return [{"section": h.section, "doc_type": h.doc_type, "score": round(h.score, 4), "content": h.content}
            for h in hits]
