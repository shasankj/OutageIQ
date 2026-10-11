# Progress

## Phase 0: Setup and data
- [x] Step 0: brief, options, check; ADRs 0001-0004
- [x] Step 1: skeleton (.gitignore, .env.example, requirements.txt, PROGRESS.md)
- [x] Step 2: RDS bootstrap scripts (user runs `db/admin/*.sql`)
- [x] Step 3: connection helper + smoke test
- [x] Step 4: migrations
- [x] Step 5: generator (9 tests pass), data loaded; outage 1234 verified
- [x] Step 6: knowledge docs (outages, tickets, sites, joins, glossary, example)
- [x] Step 7: break it + recap (LEARNING, INTERVIEW, METRICS, EXPERIMENTS stubs)

## Next step
DONE: whole system built (90 offline tests), three documents written (docs/01-APP-GUIDE.md, docs/02-EVALUATION-TOKENOMICS-AND-MODELS.md, docs/03-INTERVIEW-QA.md), ADRs 0001-0007.
The user already ran the live app (traces in data/traces/). Fixes made after the first traces: id formatting, Eastern 'now' note, interpretation disclosure, conversation memory, overlap rule in the knowledge file.
USER TODO (needs live services): python -m rag.indexer (re-embeds the 1 changed rules chunk), python -m scripts.check_connection (live read-only proofs),
python -m evals.retrieval_eval flat11 flat / typed11 typed, python -m evals.agent_eval v1. Paste results; fill the PENDING items in docs 01-03 and EXPERIMENTS.md.
Then: ablations E5-E13, grow golden set to 100, judge calibration (kappa), hybrid search, CI gate, AWS deployment.

## Facts
- RDS host: kenzo-coaching.cj6yseus2qi8.us-east-2.rds.amazonaws.com (us-east-2). Shared with other projects; touch only `outageiq`.
- Assistant never connects to the DB; the user runs all scripts.
- Domain rule: `end_time IS NULL` means the outage is still open; `start_time` is never NULL.
- Roles: outageiq_owner (DDL/loading), outageiq_indexer (rag write), outageiq_reader (agent, SELECT), outageiq_colleague_ro (colleague, SELECT, conn limit 5). Possible Phase 3 split: MCP role with ops-only access.
- PUBLIC can CONNECT to the other databases (coaching, healthcare) by default; deliberately not changed.
- Colleague shares the rag tables: version them if embedding model/dimensions change (Phase 2).
- Schema applied (0001). Generator: seed 42, as-of 2026-10-01 UTC, 1420 outages; outage 1234 / INC-55821 hand-crafted; edge cases in data/manifest.json.
- Test bug lesson: SET default_transaction_read_only applies to the NEXT transaction; guardrail != privilege boundary.
- Knowledge base is ONE file: knowledge/outageiq_knowledge.md (sections tagged `<!-- meta: type=...; tables=... -->`; parser in common/knowledge.py). Old per-table docs removed (in git history). Example SQL is gated by scripts/check_knowledge_examples.py.
- Relative-time questions: data is a fixed snapshot as of 2026-10-01, so golden questions use absolute dates; the prompt supplies 'today'.
- Bedrock Titan V2 blocked: applied on-demand RPM/TPM quota = 0 in us-east-2 (default 6000), not adjustable. Embeddings switched to Voyage voyage-4 via common/embeddings.py facade. Interview story: diagnose with Service Quotas, isolate provider behind an interface.
- Stack versions: anthropic 1.13.0, mcp 2.3.0 (MCPServer, not FastMCP), langgraph 1.2.14, fastapi 0.143.0, voyageai 0.5.0, sqlglot 30.22.0. cryptography pinned 48.0.1 (binary wheel; newest needs Rust on Intel mac).
- Models: SQL + judge = claude-sonnet-5-5 ($2/$10 per M), router + answer = claude-haiku-5-5 ($0.10/$0.50). Sonnet/Opus 5.5 reject temperature + forced tool_choice -> structured outputs + effort.
- User's .env LLM_MODEL (old haiku-4-5) is unused; models come from SQL_MODEL/ROUTER_MODEL/ANSWER_MODEL/JUDGE_MODEL env or AgentConfig defaults.
- Docs: 02 now has section 6.0 (how to read @k notation), section 8 (caching in agentic systems), Appendix A (glossary). v1 agent eval done: EX lenient 26/27, behaviour 30/30, $0.016/question. Pending: ablations E5-E13, bigger golden set, judge kappa, hybrid search, CI gate, AWS deploy.
