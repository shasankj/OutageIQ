# Interview prep

Model answers are in first person. Numbers marked TBD are filled in after evals exist.

## Fundamentals

### Why is text-to-SQL hard? (Fundamentals)
The hard parts are not syntax. Ambiguity ("recent", "big"), joins across several tables, column names the model has never seen, NULL semantics, and time zones all produce plausible but wrong SQL. In my outage schema an ongoing outage has a NULL `end_time`, so durations are NULL, and an INNER JOIN to tickets silently drops outages that have no ticket. The worst failure is a query that runs and returns the wrong rows, because nothing errors and no repair loop fires. So I treat schema documentation and result-level evaluation as the real work. TBD: baseline accuracy from Phase 1.
- **Common wrong answer:** "LLMs write bad SQL syntax." Modern models rarely do.
- **Follow-up:** How would you detect a query that runs but is wrong?

### How do you stop an agent running destructive SQL? (Production)
I use layers, and only one of them is a real boundary. The database role has SELECT only, so INSERT, UPDATE, DELETE and DDL fail with permission denied even if the session turns off read-only mode. On top of that I set `default_transaction_read_only` and a statement timeout as guardrails, and a SQL validator that allows a single SELECT on allowlisted tables with a forced LIMIT. The MCP server adds a row cap and an EXPLAIN check. I tested the boundary directly: the reader role runs `SET default_transaction_read_only = off` and then a `CREATE TABLE` fails with permission denied.
- **Common wrong answer:** "I set the connection to read-only." A session can switch that back.
- **Follow-up:** What stops an expensive SELECT?

### How do you handle "not found" versus "found but incomplete"? (Design)
They look identical to an INNER JOIN: zero rows. I start the query from the outages table and LEFT JOIN optional tables. Zero rows then means the outage does not exist, and NULL ticket columns mean it exists with no ticket, and the answer says exactly that. The answer layer reports missing values as missing and never fills them in; every value must come from a returned row.
- **Common wrong answer:** "Return an empty answer."
- **Follow-up:** How do you test that behavior?

## Metrics
(Added from Phase 1 on; see docs/METRICS.md.)
