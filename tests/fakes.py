"""Scripted stand-ins so agent behaviour is tested deterministically, offline, for free."""
from agent.config import AgentConfig
from agent.graph import Deps
from agent.runner import Agent
from agent.schemas import AnswerDraft, RouteDecision, SemanticVerdict, SQLDraft
from common.llm import CallUsage


class FakeLLM:
    """Returns queued objects per schema class; records every prompt it was sent."""

    def __init__(self, route="answer", sql=(), verdicts=(), answers=("ok",), clarifying=""):
        self.queues = {
            RouteDecision: [RouteDecision(category=route, clarifying_question=clarifying)],
            SQLDraft: [SQLDraft(interpretation="test", sql=s) for s in sql],
            SemanticVerdict: [SemanticVerdict(answers_question=v, problem="" if v else "wrong filter") for v in verdicts],
            AnswerDraft: [AnswerDraft(answer=a) for a in answers],
        }
        self.calls: list[tuple[str, str]] = []

    async def parse(self, *, model, system, user, schema, effort, max_tokens):
        self.calls.append((schema.__name__, user))
        queue = self.queues[schema]
        if not queue:
            if schema is SemanticVerdict:  # default: the judge approves
                return SemanticVerdict(answers_question=True, problem=""), CallUsage(model, 10, 5, 0)
            raise AssertionError(f"unexpected extra {schema.__name__} call")
        return queue.pop(0), CallUsage(model, 1000, 200, 0.0)

    def count(self, schema_name: str) -> int:
        return sum(1 for name, _ in self.calls if name == schema_name)


def rows_result(columns, rows, truncated=False):
    return {"ok": True, "columns": [{"name": n, "type": t} for n, t in columns], "rows": rows,
            "row_count": len(rows), "truncated": truncated, "sql_executed": "", "plan_cost": 1.0}


class FakeTools:
    """handler(sql) -> result dict; also records every executed SQL."""

    def __init__(self, handler):
        self.handler, self.executed = handler, []

    async def run_query(self, sql: str) -> dict:
        self.executed.append(sql)
        return self.handler(sql)


async def fake_retrieve(question, extra, widen):
    return [{"section": "Table ops.outages", "doc_type": "table", "score": 0.5, "content": "ctx"}]


def make_agent(llm, tools, **cfg_overrides) -> Agent:
    cfg = AgentConfig(**cfg_overrides)
    return Agent(Deps(llm=llm, tools=tools, retrieve=fake_retrieve, cfg=cfg))
