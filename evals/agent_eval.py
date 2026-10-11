"""End-to-end evaluation of the agent against the golden set.

Run: python -m evals.agent_eval <label> [question_id ...]
Per question it records: behaviour (answer / not_found / clarify / refuse), execution accuracy (strict
and lenient), first-try success, repairs, answer correctness (golden values present in the answer),
grounding (no invented values), latency, tokens and cost. Results go to data/agent_eval_<label>.json.
Costs real LLM money (about $0.01-0.03 per question with the default models).
"""
import asyncio
import json
import statistics
import sys
from pathlib import Path

from agent.runner import create_agent
from evals.compare import golden_values_in_answer, results_match
from evals.golden import load_golden
from mcp_server.backends import PostgresBackend

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
EXPECTED_KIND = {"answer": {"answered"}, "not_found": {"not_found"}, "clarify": {"clarify"}, "refuse": {"refused"}}


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


def score(q: dict, result: dict, golden_result: dict | None) -> dict:
    final, kind = result["final"], result["final"]["kind"]
    row = {"id": q["id"], "question": q["question"], "category": q["category"], "difficulty": q["difficulty"],
           "behavior": q["behavior"], "kind": kind, "behavior_ok": kind in EXPECTED_KIND[q["behavior"]],
           "retries": len(result["attempts"]), "latency_s": result["latency_s"], **result["usage"],
           "sql": final.get("sql"), "answer": final.get("answer"), "grounded": final.get("grounded", True)}
    row["first_try"] = row["behavior_ok"] and row["retries"] == 0
    if golden_result is not None and golden_result["ok"] and q["behavior"] == "answer":
        got_rows = final.get("rows") if kind == "answered" else None
        row["exec_strict"] = bool(got_rows is not None and results_match(golden_result["rows"], got_rows, strict=True))
        row["exec_lenient"] = bool(got_rows is not None and results_match(golden_result["rows"], got_rows))
        ok, missing = golden_values_in_answer(golden_result["columns"], golden_result["rows"], final.get("answer", ""))
        row["answer_correct"] = ok and row["exec_lenient"]
        row["answer_missing"] = missing
    elif q["behavior"] == "not_found":
        row["exec_strict"] = row["exec_lenient"] = row["answer_correct"] = row["behavior_ok"]
    return row


async def main(label: str, only: list[str]) -> int:
    questions = [q for q in load_golden() if not only or q["id"] in only]
    backend = PostgresBackend()
    golden = {q["id"]: backend.run_query(q["golden_sql"]) for q in questions if q["golden_sql"]}
    rows = []
    async with create_agent() as agent:
        sem = asyncio.Semaphore(3)

        async def one(q):
            async with sem:
                result = await agent.ask(q["question"])
                scored = score(q, result, golden.get(q["id"]))
                mark = "ok " if scored["behavior_ok"] and scored.get("exec_lenient", True) else "BAD"
                print(f"[{mark}] {q['id']} {scored['kind']:<10} retries={scored['retries']} ${scored['cost_usd']:.4f} {q['question'][:60]}")
                return scored

        rows = await asyncio.gather(*(one(q) for q in questions))

    sql_rows = [r for r in rows if "exec_lenient" in r]
    n = len(rows)
    summary = {
        "label": label, "questions": n,
        "behavior_accuracy": sum(r["behavior_ok"] for r in rows) / n,
        "execution_accuracy_strict": sum(r.get("exec_strict", False) for r in sql_rows) / max(len(sql_rows), 1),
        "execution_accuracy_lenient": sum(r.get("exec_lenient", False) for r in sql_rows) / max(len(sql_rows), 1),
        "answer_correctness": sum(r.get("answer_correct", False) for r in sql_rows) / max(len(sql_rows), 1),
        "grounded_rate": sum(r["grounded"] for r in rows) / n,
        "first_try_rate": sum(r["first_try"] for r in rows) / n,
        "mean_retries": statistics.mean(r["retries"] for r in rows),
        "repaired": sum(1 for r in sql_rows if r["retries"] > 0 and r.get("exec_lenient")),
        "latency_p50_s": percentile([r["latency_s"] for r in rows], 0.5),
        "latency_p95_s": percentile([r["latency_s"] for r in rows], 0.95),
        "mean_input_tokens": statistics.mean(r["input_tokens"] for r in rows),
        "mean_output_tokens": statistics.mean(r["output_tokens"] for r in rows),
        "cost_per_question_usd": statistics.mean(r["cost_usd"] for r in rows),
        "total_cost_usd": sum(r["cost_usd"] for r in rows),
    }
    print("\n" + json.dumps(summary, indent=2))
    for r in rows:
        if not r["behavior_ok"] or r.get("exec_lenient") is False or r.get("answer_correct") is False:
            print(f"\n--- {r['id']} {r['question']}\n    kind={r['kind']} retries={r['retries']}\n    sql={r['sql']}\n"
                  f"    answer={str(r['answer'])[:300]}\n    missing_in_answer={r.get('answer_missing')}")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"agent_eval_{label}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(asyncio.run(main(args[0] if args else "run", args[1:])))
