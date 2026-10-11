"""The agent loop, tested with scripted LLM output and scripted tool results (no network, no DB)."""
import asyncio

from tests.fakes import FakeLLM, FakeTools, make_agent, rows_result

GOOD = "SELECT o.outage_id, o.priority FROM ops.outages o WHERE o.outage_id = 1234"
COUNT_COLS = [("outage_id", "int8"), ("priority", "text")]


def ok_handler(sql):
    return rows_result(COUNT_COLS, [[1234, "critical"]])


def ask(llm, tools, question="What priority does outage 1234 have?", **cfg):
    return asyncio.run(make_agent(llm, tools, **cfg).ask(question))


def nodes(result):
    return [e["node"] for e in result["events"]]


def test_happy_path_answers_from_rows_and_counts_usage():
    llm = FakeLLM(sql=[GOOD], answers=["Outage **1234** has **critical** priority."])
    r = ask(llm, FakeTools(ok_handler))
    assert r["final"]["kind"] == "answered" and "critical" in r["final"]["answer"]
    assert r["final"]["grounded"] is True and r["final"]["attempts"] == 1
    assert nodes(r) == ["route", "retrieve", "generate", "validate", "execute", "check", "answer"]
    assert r["usage"]["llm_calls"] == 4  # route, generate, judge, answer
    assert r["usage"]["input_tokens"] > 0 and r["usage"]["cost_usd"] > 0


def test_unknown_column_is_repaired_with_re_retrieval_and_the_error_is_in_the_repair_prompt():
    bad = "SELECT o.end_date FROM ops.outages o WHERE o.outage_id = 1234"
    llm = FakeLLM(sql=[bad, GOOD], answers=["Outage **1234** is **critical**."])
    tools = FakeTools(ok_handler)
    r = ask(llm, tools)
    assert r["final"]["kind"] == "answered" and r["final"]["attempts"] == 2
    assert nodes(r).count("retrieve") == 2  # unknown_column triggers re-retrieval
    repair_prompt = [u for name, u in llm.calls if name == "SQLDraft"][1]
    assert bad in repair_prompt and "unknown_column" in repair_prompt and "end_date" in repair_prompt
    assert len(tools.executed) == 1  # the invalid SQL was stopped by the validator and never reached the DB


def test_same_sql_twice_is_detected_as_a_loop_and_stops():
    bad = "SELECT o.end_date FROM ops.outages o"
    llm = FakeLLM(sql=[bad, bad])
    r = ask(llm, FakeTools(ok_handler))
    assert r["final"]["kind"] == "failed" and len(r["attempts"]) == 2
    assert llm.count("SQLDraft") == 2  # stopped; did not burn the remaining retries


def test_retry_limit_stops_a_run_of_different_bad_queries():
    bads = [f"SELECT o.nope{i} FROM ops.outages o" for i in range(6)]
    llm = FakeLLM(sql=bads)
    r = ask(llm, FakeTools(ok_handler), max_retries=3)
    assert r["final"]["kind"] == "failed"
    assert llm.count("SQLDraft") == 4  # first try + 3 repairs


def test_database_error_is_fed_back_and_fixed():
    def handler(sql):
        if "bad_cast" in sql:
            return {"ok": False, "error_kind": "type_mismatch", "message": "operator does not exist"}
        return rows_result(COUNT_COLS, [[1234, "critical"]])
    llm = FakeLLM(sql=["SELECT o.outage_id, o.priority FROM ops.outages o WHERE o.priority = 1 /* bad_cast */",
                       GOOD], answers=["Outage **1234** is **critical**."])
    r = ask(llm, FakeTools(handler))
    assert r["final"]["kind"] == "answered" and r["attempts"][0]["kind"] == "type_mismatch"


def test_empty_result_when_the_named_outage_exists_triggers_a_retry():
    def handler(sql):
        if "INNER" in sql:
            return rows_result(COUNT_COLS, [])  # the join dropped it
        return rows_result(COUNT_COLS, [[1234, "critical"]])
    inner = "SELECT o.outage_id, o.priority FROM ops.outages o INNER JOIN ops.tickets t ON t.outage_id = o.outage_id WHERE o.outage_id = 1234"
    llm = FakeLLM(sql=[inner, GOOD], answers=["Outage **1234** is **critical**."])
    r = ask(llm, FakeTools(handler))
    assert r["final"]["kind"] == "answered" and r["attempts"][0]["kind"] == "empty_result_entity_exists"


def test_nonexistent_entity_is_reported_not_found_without_retrying():
    llm = FakeLLM(sql=[GOOD])
    r = ask(llm, FakeTools(lambda sql: rows_result(COUNT_COLS, [])), "What are the details of outage 99999?")
    assert r["final"]["kind"] == "not_found" and "outage 99999" in r["final"]["answer"]
    assert llm.count("SQLDraft") == 1 and r["attempts"] == []


def test_destructive_sql_from_the_model_is_blocked_before_the_database():
    tools = FakeTools(ok_handler)
    llm = FakeLLM(sql=["DELETE FROM ops.tickets WHERE status = 'closed'"])
    r = ask(llm, tools, "Please clean up closed tickets")
    assert r["final"]["kind"] == "refused" and tools.executed == []


def test_router_refusal_never_generates_sql():
    llm = FakeLLM(route="refuse_write")
    r = ask(llm, FakeTools(ok_handler), "Delete all closed tickets.")
    assert r["final"]["kind"] == "refused" and llm.count("SQLDraft") == 0


def test_router_clarify_returns_the_clarifying_question():
    llm = FakeLLM(route="clarify", clarifying="Which period do you mean?")
    r = ask(llm, FakeTools(ok_handler), "Show me the recent big outages.")
    assert r["final"] == {"kind": "clarify", "answer": "Which period do you mean?"}


def test_ungrounded_prose_is_replaced_by_the_deterministic_template():
    llm = FakeLLM(sql=[GOOD], answers=["Outage **1234** has critical priority and affected 9,999 customers."])
    r = ask(llm, FakeTools(ok_handler))
    assert r["final"]["grounded"] is False and "9,999" in r["final"]["ungrounded_values"]
    assert "9,999" not in r["final"]["answer"] and "critical" in r["final"]["answer"]


def test_judge_rejection_triggers_one_repair_then_stops_judging():
    llm = FakeLLM(sql=[GOOD, GOOD.replace("= 1234", "= 1234 AND 1 = 1")], verdicts=[False],
                  answers=["Outage **1234** is **critical**."])
    r = ask(llm, FakeTools(ok_handler))
    assert r["final"]["kind"] == "answered" and r["attempts"][0]["kind"] == "semantic_mismatch"
    assert llm.count("SemanticVerdict") == 1  # judged once, then trusted the repair


def test_cost_cap_stops_further_retries():
    bads = [f"SELECT o.nope{i} FROM ops.outages o" for i in range(6)]
    r = ask(FakeLLM(sql=bads), FakeTools(ok_handler), max_cost_usd_per_question=0.0)
    assert r["final"]["kind"] == "failed" and len(r["attempts"]) == 1


def test_now_note_gives_the_snapshot_time_in_eastern_and_todays_eastern_date():
    from agent.config import AgentConfig
    note = AgentConfig().now_note()
    assert "2026-09-30 20:00 EDT" in note and "2026-10-01 00:00 UTC" in note
    assert "Today in Eastern time is 2026-09-30" in note


def test_conversation_history_reaches_the_router_and_the_sql_prompt():
    history = [{"question": "How many sites were affected today?", "answer": "9 sites were affected.",
                "sql": "SELECT COUNT(DISTINCT o.site_id) FROM ops.outages o"}]
    llm = FakeLLM(sql=[GOOD], answers=["Outage **1234** is **critical**."])
    asyncio.run(make_agent(llm, FakeTools(ok_handler)).ask("Show those site details", history))
    router_prompt = next(u for n, u in llm.calls if n == "RouteDecision")
    sql_prompt = next(u for n, u in llm.calls if n == "SQLDraft")
    for prompt in (router_prompt, sql_prompt):
        assert "How many sites were affected today?" in prompt and "COUNT(DISTINCT o.site_id)" in prompt
    assert "current time is 2026-09-30 20:00 EDT" in sql_prompt


def test_without_history_the_router_sees_only_the_question():
    llm = FakeLLM(sql=[GOOD], answers=["Outage **1234** is **critical**."])
    asyncio.run(make_agent(llm, FakeTools(ok_handler)).ask("What priority does outage 1234 have?"))
    assert next(u for n, u in llm.calls if n == "RouteDecision") == "What priority does outage 1234 have?"


def test_interpretation_is_passed_to_the_answer_writer_so_assumptions_can_be_disclosed():
    llm = FakeLLM(sql=[GOOD], answers=["Outage **1234** is **critical**."])
    asyncio.run(make_agent(llm, FakeTools(ok_handler)).ask("What priority does outage 1234 have?"))
    assert '"interpretation": "test"' in next(u for n, u in llm.calls if n == "AnswerDraft")
