"""API contract tests: the real app with a fake LLM and the fake MCP backend is not wired here,
so these test the request validation, the SSE framing and the feedback endpoint with a stub agent."""
import json

from fastapi.testclient import TestClient

import api.main as main


class StubAgent:
    async def stream(self, question, history=None):
        yield {"node": "route", "delta": {"events": [{"node": "route", "ms": 5, "category": "answer"}]},
               "usage": {"cost_usd": 0.001}}
        yield {"node": "answer", "delta": {"events": [{"node": "answer", "ms": 9}],
                                           "final": {"kind": "answered", "answer": "ok"}}, "usage": {"cost_usd": 0.002}}


def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA", tmp_path)
    main.app.state.agent = StubAgent()  # TestClient used without `with` skips the lifespan (no MCP, no LLM)
    return TestClient(main.app)


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_ask_streams_steps_then_final_and_writes_a_trace(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    r = c.post("/ask", json={"question": "How many outages?"})
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["start", "step", "step", "final"]
    assert events[-1][1]["final"] == {"kind": "answered", "answer": "ok"}
    trace_files = list((tmp_path / "traces").glob("*.jsonl"))
    assert len(trace_files) == 1 and "How many outages?" in trace_files[0].read_text()


def test_ask_validates_input(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.post("/ask", json={"question": ""}).status_code == 422
    assert c.post("/ask", json={}).status_code == 422


def test_feedback_is_stored_and_validated(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.post("/feedback", json={"request_id": "r1", "rating": "down", "comment": "wrong site"}).json() == {"ok": True}
    assert "wrong site" in (tmp_path / "feedback.jsonl").read_text()
    assert c.post("/feedback", json={"request_id": "r1", "rating": "meh"}).status_code == 422
