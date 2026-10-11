"""HTTP API. Run: uvicorn api.main:app --port 8000

POST /ask       {question}  -> server-sent events: one `step` per finished graph node, then `final`
POST /feedback  {request_id, rating: up|down, comment?} -> data/feedback.jsonl (reviewed into new golden examples)
GET  /health
Every request's full trace (nodes, SQL, attempts, tokens, cost) is appended to data/traces/<date>.jsonl.
"""
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.runner import create_agent

DATA = Path(__file__).resolve().parent.parent / "data"
FINAL_NODES = {"answer", "respond_nonsql", "fail", "refuse_unsafe"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_agent() as agent:  # one MCP server process for the life of the API
        app.state.agent = agent
        yield


app = FastAPI(title="OutageIQ", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class HistoryTurn(BaseModel):
    question: str = Field(max_length=1000)
    answer: str = Field(default="", max_length=4000)
    sql: str | None = Field(default=None, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)  # earlier turns, oldest first


class FeedbackRequest(BaseModel):
    request_id: str
    rating: str = Field(pattern="^(up|down)$")
    comment: str = Field(default="", max_length=2000)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def append_jsonl(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(req: AskRequest):
    request_id = str(uuid.uuid4())

    async def events():
        started, trace, final, usage = time.perf_counter(), [], None, {}
        yield sse("start", {"request_id": request_id})
        try:
            async for update in app.state.agent.stream(req.question, [h.model_dump() for h in req.history]):
                delta, usage = update["delta"], update["usage"]
                step = (delta.get("events") or [{"node": update["node"], "ms": 0}])[-1]
                if update["node"] == "retrieve":
                    step = {**step, "chunks": step.get("chunks", [])}
                trace.append(step)
                yield sse("step", {**step, "usage": usage})
                if update["node"] in FINAL_NODES and "final" in delta:
                    final = delta["final"]
        except Exception as e:
            final = {"kind": "error", "answer": "Something went wrong while answering.", "error": f"{type(e).__name__}: {e}"}
        yield sse("final", {"request_id": request_id, "final": final, "usage": usage,
                            "latency_s": round(time.perf_counter() - started, 3)})
        append_jsonl(DATA / "traces" / f"{date.today()}.jsonl",
                     {"request_id": request_id, "question": req.question, "trace": trace, "final": final,
                      "usage": usage, "latency_s": round(time.perf_counter() - started, 3)})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    append_jsonl(DATA / "feedback.jsonl", {"ts": time.time(), **req.model_dump()})
    return {"ok": True}
