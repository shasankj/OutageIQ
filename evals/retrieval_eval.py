"""Retrieval evaluation against the golden set.

Run: python -m evals.retrieval_eval [label] [flat|typed]
  flat  = plain top-k similarity over all chunks;  typed = a fixed budget per chunk role (11 chunks)
For each question: search the vector store, compare the ranked chunk sections with the labeled
relevant sections (grade 2 = required, 1 = helpful). Reports Hit@k, Recall@k, Precision@k, MRR
and nDCG@k, plus the misses, which are the useful part.
Relevance for hit/recall/MRR = grade 2 (required). Precision and nDCG use all grades.
"""
import json
import statistics
import sys
import time
from pathlib import Path

from evals.golden import load_golden
from evals.metrics import hit_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from rag.retriever import retrieve_context, search

KS = (3, 5, 8, 11)
OUT_DIR = Path(__file__).resolve().parent.parent / "data"


STRATEGIES = {"flat": lambda q, k: search(q, k=k), "typed": lambda q, k: retrieve_context(q)}


def evaluate(search_fn=search, ks=KS) -> tuple[dict, list[dict]]:
    rows, started = [], time.perf_counter()
    for n, q in enumerate(load_golden(), 1):
        print(f"  [{n:>2}/30] {q['id']} {time.perf_counter() - started:5.0f}s  {q['question'][:60]}", flush=True)
        grades = q["relevant"]
        required = {s for s, g in grades.items() if g == 2}
        ranked = [h.section for h in search_fn(q["question"], max(ks))]
        row = {"id": q["id"], "question": q["question"], "category": q["category"], "ranked": ranked,
               "missed_at_5": sorted(required - set(ranked[:5])), "rr": reciprocal_rank(ranked, required)}
        for k in ks:
            row[f"hit@{k}"] = hit_at_k(ranked, required, k)
            row[f"recall@{k}"] = recall_at_k(ranked, required, k)
            row[f"precision@{k}"] = precision_at_k(ranked, set(grades), k)
            row[f"ndcg@{k}"] = ndcg_at_k(ranked, grades, k)
        rows.append(row)
    summary = {"MRR": statistics.mean(r["rr"] for r in rows)}
    for k in ks:
        for m in ("hit", "recall", "precision", "ndcg"):
            summary[f"{m}@{k}"] = statistics.mean(r[f"{m}@{k}"] for r in rows)
    return summary, rows


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    strategy = sys.argv[2] if len(sys.argv) > 2 else "flat"
    summary, rows = evaluate(STRATEGIES[strategy])
    print(f"Retrieval eval '{label}' (strategy={strategy}): {len(rows)} questions\n")
    print(f"{'metric':<14}" + "".join(f"{'k=' + str(k):>8}" for k in KS))
    for m in ("hit", "recall", "precision", "ndcg"):
        print(f"{m + '@k':<14}" + "".join(f"{summary[f'{m}@{k}']:>8.3f}" for k in KS))
    print(f"{'MRR':<14}{summary['MRR']:>8.3f}\n")
    misses = [r for r in rows if r["missed_at_5"]]
    print(f"Questions missing a required chunk at k=5: {len(misses)}")
    if strategy == "typed":
        print("(typed lists put rules first, then tables, so read k=11 = the whole context the LLM would get)")
    for r in misses:
        print(f"  {r['id']} [{r['category']}] {r['question']}")
        print(f"      missed: {r['missed_at_5']}")
        print(f"      top5:   {r['ranked'][:5]}")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"retrieval_eval_{label}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
