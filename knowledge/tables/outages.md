---
doc_type: table
tables: [outages]
schema: ops
schema_version: 1
---
# Table ops.outages

**Purpose.** One row per network outage. This is the central table: tickets, alarms, updates, root causes and impacted services all point to it through `outage_id`. Start here for any question about an outage.

## Columns
| Column | Type | Meaning |
|---|---|---|
| outage_id | bigint PK | The outage number. "Outage 1234" means `outage_id = 1234`. |
| site_id | bigint FK → sites.site_id | The site where it happened. Join to `sites` for the site code and region. |
| outage_type | text | `OOS` Out of Service, `SC` Sleepy Cell, `TIS` Top Impaired Site, `MO` Micro Outage. |
| network_domain | text | `RAN`, `Core` or `Transport`. This is the "RAN outage" in plain English. It is a different thing from `outage_type`. |
| priority | text | `low`, `medium`, `high`, `critical` (lowercase). Not the same as `tickets.priority`. |
| start_time | timestamptz | When it began. Never NULL. UTC. |
| end_time | timestamptz | When service was restored. **NULL means the outage is still open.** |
| is_open | boolean | Generated: `end_time IS NULL`. Prefer it for "open / ongoing / active" questions. |
| cells_affected | integer | Number of cells impacted. |
| created_at, updated_at, created_by | | Audit columns: when the row was inserted or changed, and by which database role. Not business times. |

## Gotchas
- **Ongoing outages.** When `end_time IS NULL` there is no duration yet. Do not compute `end_time - start_time` (it is NULL). Report "ongoing" and, if needed, time elapsed so far.
- **"Open" means the outage, not the ticket.** Use `outages.is_open`, never ticket columns (`resolved_at`, `is_resolved`, `status`). A ticket can stay open after service is restored, and outages with no ticket have no ticket row at all.
- **Time zones.** Times are stored in UTC. For questions about "today", "yesterday" or a clock time, convert with `AT TIME ZONE 'America/New_York'` before comparing dates.
- **Total customers affected is not on this table.** It is `SUM(customers_impacted)` over `impacted_services` for the outage.
- **Root cause is not on this table.** It is in `outage_root_causes` (an outage can have several; one is primary).
- **Two priorities exist.** `outages.priority` is the outage's. A ticket may carry a different one. Use the table the question is about.

## Join paths
- Site: `outages.site_id = sites.site_id` (inner join is safe; every outage has a site).
- Tickets: `tickets.outage_id = outages.outage_id` (use LEFT JOIN: an outage may have none, or several).
- Others: see the relationship doc `outage_joins`.

## Typical questions
Details of outage N, open outages, outages by type or priority, outages at a site or region in a time window, longest outages, how many outages this week.
