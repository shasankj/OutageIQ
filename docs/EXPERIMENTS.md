# Experiments log

Each entry: what changed, metrics before/after, cost, latency, conclusion. No change is "better" without
numbers. Planned ablations are PENDING; nothing here is invented.

Full explanation of the metrics: `docs/02-EVALUATION-TOKENOMICS-AND-MODELS.md` section 6.

## E1. Retrieval baseline: plain top-k similarity (2026-10-10) *measured*
- **Setup:** 34 entity chunks (Voyage `voyage-4`, 1024 dims, cosine, HNSW); 30 held-out golden questions with graded
  relevant-chunk labels (2 = required, 1 = helpful); plain top-k over all chunks.
- **Result** (`data/retrieval_eval_baseline.json`):

  | k | Hit | Recall | Precision | nDCG |
  |---|---|---|---|---|
  | 3 | 0.600 | 0.517 | 0.244 | 0.422 |
  | 5 | 0.800 | 0.700 | 0.213 | 0.503 |
  | 8 | 0.900 | 0.817 | 0.171 | 0.556 |

  MRR 0.485. 12 of 30 questions miss a required chunk at k=5.
- **Diagnosis:** the top-5 lists are dominated by short, question-shaped `Example:` chunks, which crowd out the
  long `Table ops.*` chunks the LLM needs.
- **Conclusion:** change the retrieval design (E2). Precision is a poor target here (1 to 3 relevant chunks per question).

## E2. Retrieval: typed budget vs plain top-k at equal context size (k = 11) (2026-10-10) *measured*
- **Change:** reserve slots per chunk type (2 always-on rules, 4 tables, 2 relationship/glossary, 3 examples).
- **Result** (clean re-run after the stale duplicate chunk was pruned):

  | At k = 11 | Hit | Recall | nDCG | Misses in first 5 slots |
  |---|---|---|---|---|
  | Plain top-k | 0.967 | 0.933 | **0.604** | 12 |
  | Typed | **1.000** | **0.983** | 0.581 | 2 (g12, g22: `users` table) |

- **Caveats:** k = 11 is a third of the 34-chunk corpus, so the test barely discriminates; typed k=3/5 and MRR (0.364 vs 0.490) are not comparable because rules are listed first; 2 of the 12 plain misses were the always-on rules chunk.
- **Trade-off:** typed wins on Hit and Recall but is lower on nDCG (0.581 vs 0.604): the always-on rules chunks take the first ranks and are rarely labelled relevant.
- **Cache evidence:** the typed run took 596 s (28 uncached queries paced about 21 s apart by the rate-limit pacer); the plain run took 9 s (all queries cached).
- **Conclusion:** directionally positive; keep the typed design (it guarantees table chunks), and re-test with a smaller budget or a larger corpus.

## E3. Live smoke observations (2026-10-10) *measured, anecdotal (n = 6 SQL runs, 5 clarifications)*
Source: `data/traces/2026-10-10.jsonl`.
- Outage 1234: correct, fully grounded, 14.9 s, $0.0189, 4 LLM calls.
- SQL-answering runs: $0.019 to $0.058 (mean about $0.039), 11 to 23 s, 4 to 6 LLM calls. Clarifications: about $0.0001, about 1.5 s.
- **Issues found and fixed:** (1) ids formatted with thousands separators; (2) prompt said "today is 2026-10-01" although the snapshot is 2026-09-30 20:00 Eastern; (3) answer did not state its interpretation of "affected today"; (4) stateless agent: three follow-ups each triggered a clarification (conversation memory added).
- **Observation:** in both live runs of "How many sites were affected by outages today?" the LLM judge rejected a start-only count and the repair used an overlap condition; the overlap rule was added to the knowledge file. Whether the judge helps or hurts overall is E5.

## E4. Full agent evaluation v1 (2026-10-10) *measured*
`python -m evals.agent_eval v1`; Sonnet 5.5 (SQL, judge), Haiku 5.5 (router, prose); 30 held-out questions.

| Metric | Result |
|---|---|
| Behaviour accuracy | 30/30 = 1.000 (95% interval 0.89 to 1.00) |
| Execution accuracy, lenient | 26/27 = 0.963 (0.82 to 0.99) |
| Execution accuracy, strict | 12/27 = 0.444 (0.28 to 0.63) |
| Answer correctness | 26/27 = 0.963 |
| Grounded answers | 30/30 |
| First-try success | 28/30 = 0.933 |
| Repairs ending correct | 2 of 2 (g16, g20); mean retries 0.067 |
| Tokens per question | 8,206 input, 313 output (mean) |
| Cost | $0.016 per question, $0.479 total |
| Latency p50 / p95 | 71 s / 218 s: **artifact of Voyage rate limiting**, not service latency (live traces 11 to 23 s) |

- **The one miss (g21)** is a comparator false negative (LEFT JOIN NULL row vs golden `COUNT(*) = 0`); the answer was correct.
- **Strict vs lenient** differ because the prompt asks for identifying columns; lenient measures right data.
- **Defects found by the run and fixed:** Voyage rate-limit storm (shared pacer + persistent query-embedding cache; adding a payment method raises the limit), stale duplicate chunk (indexer now prunes superseded chunks).
- **Conclusion:** the system is accurate on this question set; with n = 30 the interval is wide. The next information-bearing steps are the ablations below and a larger golden set.

## Planned ablations (one variable each)
| ID | Variable | Values |
|---|---|---|
| E5 | `semantic_check` (LLM judge) | on / off |
| E6 | `max_retries` | 0, 1, 2, 3 |
| E7 | `SQL_MODEL` and `SQL_EFFORT` | Haiku 5.5, Sonnet 5.5, Opus 5.5; low, medium, high |
| E8 | `examples_k`, `tables_k` | 0, 1, 3, 5; 2, 4, 6 |
| E9 | Everything in the prompt vs retrieval | accuracy, tokens, cost |
| E10 | Embedding dimensions; query/document `input_type` | 256, 512, 1024; on / off |
| E11 | Chunking strategy | entity vs fixed-size vs recursive |
| E12 | Hybrid search (keyword + vector) | on / off; focus on identifier questions |
| E13 | Prompt version | p1 vs p2 |
