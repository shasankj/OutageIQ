"""The self-correcting text-to-SQL agent as a LangGraph state machine.

  route -> retrieve -> generate -> validate -> execute -> check_result -> answer
              ^            ^          |           |           |
              |            +----------+-----------+-----------+   (failure -> diagnose -> retry)
              +-- re-retrieve on unknown_column / unknown_table

Key design points
- Typed failures: every failure has a `kind`; `diagnose` decides retry vs give up per kind.
- The repair prompt carries the question, retrieved context, ALL previous SQL and each one's error.
- Loop control: max retries, same-SQL-twice detection, per-question cost cap.
- An empty result is not trusted blindly: if the question names an outage/ticket that exists, a
  zero-row answer means the query dropped it (e.g. an INNER JOIN), so we retry once.
- A successful result is reviewed by an LLM judge (reflection WITH execution feedback).
- The answer is produced from deterministic facts and verified for grounding before it is returned.
"""
import re
import time
from dataclasses import dataclass
from operator import add
from typing import Annotated, Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from agent import facts as F
from agent import prompts as P
from agent.config import AgentConfig
from agent.schemas import AnswerDraft, RouteDecision, SemanticVerdict, SQLDraft
from agent.tools import SQLTools
from agent.validator import validate
from common.llm import LLMRefusal, Meter

SOFT_KINDS = {"empty_result", "empty_result_entity_exists", "semantic_mismatch"}
UNSAFE_KINDS = {"not_select", "forbidden", "permission_denied"}
Retriever = Callable[[str, str, bool], Awaitable[list[dict]]]

REFUSALS = {
    "refuse_write": "I can't change data. This assistant is read-only: it answers questions by reading the "
                    "outage, ticket, site and alarm records.",
    "refuse_injection": "I can't help with that request. I only answer questions about outages, tickets, "
                        "sites, alarms and root causes, and I follow fixed safety rules.",
    "out_of_scope": "That isn't information this database holds. I can answer questions about outages, tickets, "
                    "sites, alarms, root causes and who is assigned to tickets.",
    "clarify": "Could you be more specific? For example, which period and which measure (priority, number of "
               "customers, or duration) do you mean?",
}


@dataclass
class Deps:
    llm: object            # needs: async parse(model, system, user, schema, effort, max_tokens) -> (obj, usage)
    tools: SQLTools
    retrieve: Retriever
    cfg: AgentConfig


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]
    route: str
    clarifying_question: str
    context: list[dict]
    extra_retrieval: str
    sql: str
    interpretation: str
    sql_validated: str
    exec_result: dict
    failure: dict | None
    attempts: Annotated[list[dict], add]
    retries: int
    semantic_retries: int
    next: str
    not_found: str
    warnings: Annotated[list[str], add]
    final: dict
    events: Annotated[list[dict], add]


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()


def _event(node: str, started: float, **info) -> dict:
    return {"node": node, "ms": int((time.perf_counter() - started) * 1000), **info}


_OUTAGE = re.compile(r"\boutage(?:\s+(?:id|number))?\s*#?\s*(\d{1,9})\b", re.IGNORECASE)
_TICKET = re.compile(r"\bINC-(\d{1,9})\b", re.IGNORECASE)


def named_entity(question: str) -> tuple[str, str] | None:
    """('outage', '1234') or ('ticket', 'INC-55821') if the question names one, else None."""
    m = _OUTAGE.search(question)
    if m:
        return "outage", m.group(1)
    m = _TICKET.search(question)
    if m:
        return "ticket", f"INC-{m.group(1)}"
    return None


def _preview(res: dict, limit: int = 8) -> str:
    cols = [c["name"] for c in res["columns"]]
    lines = [" | ".join(cols)] + [" | ".join("NULL" if v is None else str(v) for v in r) for r in res["rows"][:limit]]
    more = f"\n... ({res['row_count']} rows total)" if res["row_count"] > limit else ""
    return "\n".join(lines) + more


def build_graph(deps: Deps):
    cfg, llm, tools = deps.cfg, deps.llm, deps.tools

    def meter(config) -> Meter:
        return config["configurable"]["meter"]

    async def route(state: AgentState, config):
        t0 = time.perf_counter()
        decision, usage = await llm.parse(model=cfg.router_model, system=P.ROUTER_SYSTEM,
                                          user=P.build_router_user_prompt(state["question"], state.get("history", [])),
                                          schema=RouteDecision, effort=cfg.router_effort, max_tokens=4000)
        meter(config).add(usage)
        return {"route": decision.category, "clarifying_question": decision.clarifying_question,
                "events": [_event("route", t0, category=decision.category)]}

    async def respond_nonsql(state: AgentState, config):
        t0 = time.perf_counter()
        category = state["route"]
        text = state.get("clarifying_question") if category == "clarify" and state.get("clarifying_question") \
            else REFUSALS[category]
        kind = "clarify" if category == "clarify" else ("out_of_scope" if category == "out_of_scope" else "refused")
        return {"final": {"kind": kind, "answer": text}, "events": [_event("respond", t0, kind=kind)]}

    async def retrieve(state: AgentState, config):
        t0 = time.perf_counter()
        extra = state.get("extra_retrieval", "")
        context = await deps.retrieve(state["question"], extra, bool(extra))
        return {"context": context, "extra_retrieval": "",
                "events": [_event("retrieve", t0, chunks=[c["section"] for c in context], widened=bool(extra))]}

    async def generate(state: AgentState, config):
        t0 = time.perf_counter()
        user = P.build_sql_user_prompt(state["question"], cfg.now_note(), state["context"], state.get("attempts", []),
                                       state.get("history", []))
        draft, usage = await llm.parse(model=cfg.sql_model, system=P.SQL_SYSTEM, user=user, schema=SQLDraft,
                                       effort=cfg.sql_effort, max_tokens=12000)
        meter(config).add(usage)
        n = len(state.get("attempts", [])) + 1
        return {"sql": draft.sql.strip(), "interpretation": draft.interpretation,
                "events": [_event("generate", t0, attempt=n, sql=draft.sql.strip(),
                                  interpretation=draft.interpretation, tokens=usage.output_tokens)]}

    async def validate_node(state: AgentState, config):
        t0 = time.perf_counter()
        v = validate(state["sql"])
        if v.ok:
            return {"sql_validated": v.sql, "failure": None, "events": [_event("validate", t0, ok=True)]}
        return {"failure": {"kind": v.kind, "message": "; ".join(v.errors)},
                "events": [_event("validate", t0, ok=False, kind=v.kind, message="; ".join(v.errors))]}

    async def execute(state: AgentState, config):
        t0 = time.perf_counter()
        res = await tools.run_query(state["sql_validated"])
        if not res["ok"]:
            return {"failure": {"kind": res["error_kind"], "message": res["message"]},
                    "events": [_event("execute", t0, ok=False, kind=res["error_kind"], message=res["message"])]}
        return {"exec_result": res, "failure": None,
                "events": [_event("execute", t0, ok=True, rows=res["row_count"])]}

    async def entity_exists(entity: tuple[str, str]) -> bool | None:
        kind, ident = entity
        sql = (f"SELECT o.outage_id FROM ops.outages o WHERE o.outage_id = {int(ident)}" if kind == "outage"
               else f"SELECT t.ticket_id FROM ops.tickets t WHERE t.ticket_number = '{ident.upper()}'")
        res = await tools.run_query(sql)
        return res["row_count"] > 0 if res.get("ok") else None

    async def check_result(state: AgentState, config):
        t0 = time.perf_counter()
        res = state["exec_result"]
        retries = state.get("retries", 0)
        if res["row_count"] == 0:
            entity = named_entity(state["question"])
            if entity:
                exists = await entity_exists(entity)
                if exists is False:
                    label = f"{entity[0]} {entity[1]}"
                    return {"failure": None, "not_found": label,
                            "events": [_event("check", t0, verdict="not_found", entity=label)]}
                if exists is True:
                    return {"failure": {"kind": "empty_result_entity_exists",
                                        "message": f"{entity[0]} {entity[1]} exists but the query returned no rows"},
                            "events": [_event("check", t0, verdict="empty_but_entity_exists")]}
            elif retries == 0:
                return {"failure": {"kind": "empty_result", "message": "the query returned no rows"},
                        "events": [_event("check", t0, verdict="empty_first_try")]}
        if cfg.semantic_check and state.get("semantic_retries", 0) < 1 and meter(config).cost_usd < cfg.max_cost_usd_per_question:
            user = P.build_judge_user_prompt(state["question"], cfg.now_note(), state["sql_validated"],
                                             state.get("interpretation", ""), _preview(res))
            verdict, usage = await llm.parse(model=cfg.judge_model, system=P.JUDGE_SYSTEM, user=user,
                                             schema=SemanticVerdict, effort=cfg.judge_effort, max_tokens=6000)
            meter(config).add(usage)
            if not verdict.answers_question:
                return {"failure": {"kind": "semantic_mismatch", "message": verdict.problem},
                        "semantic_retries": state.get("semantic_retries", 0) + 1,
                        "events": [_event("check", t0, verdict="judge_rejected", problem=verdict.problem)]}
        return {"failure": None, "events": [_event("check", t0, verdict="ok")]}

    async def diagnose(state: AgentState, config):
        t0 = time.perf_counter()
        failure = state["failure"]
        kind, message = failure["kind"], failure["message"]
        attempts = state.get("attempts", [])
        record = {"n": len(attempts) + 1, "sql": state["sql"], "kind": kind, "outcome": f"{kind}: {message}"}
        retries = state.get("retries", 0)
        repeated = any(_norm(a["sql"]) == _norm(state["sql"]) for a in attempts)
        if kind in UNSAFE_KINDS:
            decision = "refuse"
        elif repeated:
            decision = "give_up_soft" if kind in SOFT_KINDS else "give_up_hard"
        elif retries >= cfg.max_retries or meter(config).cost_usd >= cfg.max_cost_usd_per_question:
            decision = "give_up_soft" if kind in SOFT_KINDS else "give_up_hard"
        elif kind in ("unknown_column", "unknown_table"):
            decision = "retry_retrieve"
        else:
            decision = "retry_generate"
        return {"attempts": [record], "retries": retries + 1, "next": decision,
                "extra_retrieval": message if decision == "retry_retrieve" else "",
                "warnings": [f"unverified: {message}"] if decision == "give_up_soft" and kind == "semantic_mismatch" else [],
                "events": [_event("diagnose", t0, kind=kind, decision=decision, repeated=repeated)]}

    async def fail(state: AgentState, config):
        t0 = time.perf_counter()
        last = state["attempts"][-1]
        text = (f"I couldn't produce a reliable answer after {len(state['attempts'])} attempt(s). "
                f"The last problem was: {last['outcome']}")
        return {"final": {"kind": "failed", "answer": text, "sql": state.get("sql")},
                "events": [_event("fail", t0)]}

    async def refuse_unsafe(state: AgentState, config):
        t0 = time.perf_counter()
        return {"final": {"kind": "refused", "answer": REFUSALS["refuse_write"], "sql": None},
                "events": [_event("refuse_unsafe", t0)]}

    async def answer(state: AgentState, config):
        t0 = time.perf_counter()
        res = state["exec_result"]
        base = {"sql": state["sql_validated"], "interpretation": state.get("interpretation"),
                "columns": [c["name"] for c in res["columns"]], "rows": res["rows"][:50],
                "row_count": res["row_count"], "attempts": len(state.get("attempts", [])) + 1,
                "warnings": state.get("warnings", [])}
        if state.get("not_found"):
            return {"final": {**base, "kind": "not_found", "answer": f"No record was found for {state['not_found']}."},
                    "events": [_event("answer", t0, kind="not_found")]}
        facts = F.build_facts(res, cfg.data_as_of)
        if state.get("interpretation"):
            facts["interpretation"] = state["interpretation"]
        if res["row_count"] == 0:
            return {"final": {**base, "kind": "answered", "answer": F.template_answer(facts)},
                    "events": [_event("answer", t0, kind="empty")]}
        user = P.build_answer_user_prompt(state["question"], F.facts_json(facts))
        draft, usage = await llm.parse(model=cfg.answer_model, system=P.ANSWER_SYSTEM, user=user,
                                       schema=AnswerDraft, effort=cfg.answer_effort, max_tokens=6000)
        meter(config).add(usage)
        violations = F.faithfulness_violations(draft.answer, facts)
        text, grounded = (draft.answer, True) if not violations else (F.template_answer(facts), False)
        return {"final": {**base, "kind": "answered", "answer": text, "grounded": grounded,
                          "ungrounded_values": violations},
                "events": [_event("answer", t0, grounded=grounded, violations=violations)]}

    g = StateGraph(AgentState)
    for name, fn in [("route", route), ("respond_nonsql", respond_nonsql), ("retrieve", retrieve),
                     ("generate", generate), ("validate", validate_node), ("execute", execute),
                     ("check_result", check_result), ("diagnose", diagnose), ("fail", fail),
                     ("refuse_unsafe", refuse_unsafe), ("answer", answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: "retrieve" if s["route"] == "answer" else "respond_nonsql")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", lambda s: "diagnose" if s.get("failure") else "execute")
    g.add_conditional_edges("execute", lambda s: "diagnose" if s.get("failure") else "check_result")
    g.add_conditional_edges("check_result", lambda s: "diagnose" if s.get("failure") else "answer")
    g.add_conditional_edges("diagnose", lambda s: {
        "retry_retrieve": "retrieve", "retry_generate": "generate", "give_up_soft": "answer",
        "give_up_hard": "fail", "refuse": "refuse_unsafe"}[s["next"]])
    for terminal in ("respond_nonsql", "fail", "refuse_unsafe", "answer"):
        g.add_edge(terminal, END)
    return g.compile()
