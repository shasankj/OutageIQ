# 0006: Retrieval with a fixed budget per chunk type

Status: accepted, effect PENDING measurement (2026-10-10)

## Context
Measured baseline (plain top-k, 30 held-out questions): Recall@5 0.70, MRR 0.485, 12 questions missing a required
table chunk. The top-5 lists were dominated by short `Example:` chunks.

## Options
| Option | Pros | Cons |
|---|---|---|
| Plain top-k | simplest | examples crowd out tables |
| Larger k | more recall | more tokens, more noise |
| **Typed budget** (2 rules, 4 tables, 2 relationship/glossary, 3 examples) | guarantees table chunks; rules treated as instructions | fixed numbers need tuning |
| Hybrid search + reranker | helps identifiers and ordering | more moving parts; next step |

## Decision
`rag/retriever.py: retrieve_context`. Always-on rules chunks are instructions, not search results.

## Consequences
Evaluate at equal context size (k = 11) against plain top-k. Tune `tables_k` and `examples_k` by ablation. At 2,000
tables, add domain routing and metadata filtering before the typed budget.
