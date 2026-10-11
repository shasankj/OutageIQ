# 0007: Self-correcting agent loop, empty-result guard and LLM judge

Status: accepted, value of the judge PENDING ablation (2026-10-10)

## Context
Failures in text-to-SQL are of different kinds. Syntax and schema errors are cheap to fix with feedback.
Runnable-but-wrong SQL (an INNER JOIN dropping outages with no ticket; start-only vs overlap semantics) raises
no error.

## Decision
- A LangGraph state machine with **typed failures**; each kind has its own response (retry, re-retrieve, give up softly, refuse).
- Repair prompt = reference + current time + conversation + question + all previous SQL with their errors + a kind-specific hint.
- Loop control: max 3 repairs, same normalized SQL twice stops, per-question cost cap.
- **Empty-result guard:** if the question names an outage or ticket, probe whether it exists; exists means retry, missing means a deterministic not-found answer.
- **LLM judge** (Sonnet, low effort) reviews each successful result once; at most one judge-triggered repair.
- Answers are built from facts computed in code and checked for grounding; the prose falls back to a template on violation.

## Consequences
Cost grows with retries because the reference context is re-sent. The judge adds about 1 to 3 s and one Sonnet call per question and may
over-correct; ablate with `semantic_check` on/off (E5). Destructive SQL is never retried.
