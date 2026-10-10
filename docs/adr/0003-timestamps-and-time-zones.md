# 0003: Timestamps and time zones

Status: accepted (Phase 0)

## Context
Users ask in Eastern Time; durations can span DST changes. Ongoing outages have a NULL end time.

## Options
| Approach | Pros | Cons |
|---|---|---|
| `timestamptz` (UTC) + convert to ET in code | Unambiguous, DST-safe | Prompts must mention `AT TIME ZONE` when filtering by local dates |
| `timestamp` without zone | Simple | Ambiguous, DST bugs |
| Store local time | Matches display | Breaks across zones and DST |

## Decision
All timestamps are `timestamptz`. Display formatting and duration text are produced by deterministic code (Phase 5), never by the LLM. For an ongoing outage the answer reports "ongoing" and elapsed time "so far", computed in code.

## Consequences
Knowledge docs must state that "yesterday"/"today" filters need `AT TIME ZONE 'America/New_York'`.
