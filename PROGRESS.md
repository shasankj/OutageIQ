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
Phase 0 complete pending the user's commit. Next: Phase 1 (baseline without RAG): brief, options, check, then the 30-question golden dataset.

## Facts
- RDS host: kenzo-coaching.cj6yseus2qi8.us-east-2.rds.amazonaws.com (us-east-2). Shared with other projects; touch only `outageiq`.
- Assistant never connects to the DB; the user runs all scripts.
- Domain rule: `end_time IS NULL` means the outage is still open; `start_time` is never NULL.
- Roles: outageiq_owner (DDL/loading), outageiq_indexer (rag write), outageiq_reader (agent, SELECT), outageiq_colleague_ro (colleague, SELECT, conn limit 5). Possible Phase 3 split: MCP role with ops-only access.
- PUBLIC can CONNECT to the other databases (coaching, healthcare) by default; deliberately not changed.
- Colleague shares the rag tables: version them if embedding model/dimensions change (Phase 2).
- Schema applied (0001). Generator: seed 42, as-of 2026-10-01 UTC, 1420 outages; outage 1234 / INC-55821 hand-crafted; edge cases in data/manifest.json.
- Test bug lesson: SET default_transaction_read_only applies to the NEXT transaction; guardrail != privilege boundary.
