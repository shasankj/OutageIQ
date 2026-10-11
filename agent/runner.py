"""Public entry point: create_agent() wires the real LLM, MCP tools and retriever into the graph."""
import time
from contextlib import asynccontextmanager
from functools import partial

from agent.config import AgentConfig
from agent.graph import Deps, build_graph
from agent.tools import MCPTools, retrieve_context_async
from common.llm import AnthropicLLM, LLMRefusal, Meter


class Agent:
    def __init__(self, deps: Deps):
        self.cfg = deps.cfg
        self.graph = build_graph(deps)

    @staticmethod
    def _initial(question: str, history: list[dict] | None = None) -> dict:
        return {"question": question, "history": history or [], "attempts": [], "events": [], "warnings": [],
                "retries": 0, "semantic_retries": 0}

    async def ask(self, question: str, history: list[dict] | None = None) -> dict:
        """Run one question to completion. Always returns a result dict; never raises."""
        meter, started, state = Meter(), time.perf_counter(), {}
        try:
            state = await self.graph.ainvoke(self._initial(question, history),
                                             {"configurable": {"meter": meter}, "recursion_limit": 60})
            final = state["final"]
        except LLMRefusal:
            final = {"kind": "refused", "answer": "The model declined to handle this request."}
        except Exception as e:  # infrastructure failure: report, don't crash the caller
            final = {"kind": "error", "answer": "Something went wrong while answering.", "error": f"{type(e).__name__}: {e}"}
        return {"question": question, "final": final, "events": state.get("events", []),
                "attempts": state.get("attempts", []), "usage": meter.summary(),
                "latency_s": round(time.perf_counter() - started, 3), "prompt_version": self.cfg.prompt_version}

    async def stream(self, question: str, history: list[dict] | None = None):
        """Yield one dict per finished node (for the streaming API)."""
        meter = Meter()
        async for update in self.graph.astream(self._initial(question, history), {"configurable": {"meter": meter}, "recursion_limit": 60},
                                               stream_mode="updates"):
            for node, delta in update.items():
                yield {"node": node, "delta": delta, "usage": meter.summary()}


@asynccontextmanager
async def create_agent(cfg: AgentConfig | None = None, fake_mcp_backend: bool = False):
    cfg = cfg or AgentConfig()
    async with MCPTools(fake_backend=fake_mcp_backend) as tools:
        yield Agent(Deps(llm=AnthropicLLM(), tools=tools, retrieve=partial(_retrieve, cfg=cfg), cfg=cfg))


async def _retrieve(question: str, extra: str, widen: bool, cfg: AgentConfig):
    return await retrieve_context_async(question, extra, widen, cfg)
