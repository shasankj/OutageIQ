# Learning log

## Phase 0: Setup and data

### Concepts
- **Why text-to-SQL is hard:** ambiguity, joins, naming, NULLs, time zones, and *silent wrongness* (a query that runs but answers the wrong question).
- **Schema docs drive accuracy:** the LLM only knows what is in its prompt. Docs must say what columns *mean*, allowed values, join paths and traps.
- **Defense in depth for DB access:** privileges (real boundary) > read-only default (guardrail) > statement timeout > SQL validator (later phases).
- **Least privilege roles:** owner (DDL), indexer (writes `rag` only), reader (SELECT), colleague read-only.
- **Determinism:** seeded generator, fixed as-of time, no `now()`; this keeps golden datasets valid.
- **Generated columns** (`is_open`, `is_resolved`) remove ways for redundant columns to disagree.
- **Tests as constraints:** generator tests mirror DB CHECKs; they caught a ticket-resolved-before-created bug before loading.

### My mistakes / corrections
- Assumed an ongoing outage has a duration (it is NULL; never invent one).
- Thought `default_transaction_read_only` stops writes. It is session-settable; only privileges stop them.
- Named `resolved_at` / `end_date` loosely: `resolved_at` is on `tickets`; open outages use `outages.end_time` / `is_open`.
- Good instinct: unambiguous column names (`<entity>_id`, separate business keys) and audit columns (ADR 0004).

### Open questions
- Should the MCP role be ops-only, separate from the retriever's role? (Phase 3)
- How much do unique `<entity>_id` names help the LLM? Measure by ablation (Phase 8).
- How do we version `rag` tables for the colleague's app when embeddings change? (Phase 2)
