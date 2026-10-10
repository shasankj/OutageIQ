---
doc_type: table
tables: [tickets, ticket_assignments]
schema: ops
schema_version: 1
---
# Table ops.tickets (and ops.ticket_assignments)

**Purpose.** Incident tickets opened for outages. An outage can have no ticket, one, or several. Questions that name a ticket ("INC-55821") or ask who is working an outage start here.

## Columns: ops.tickets
| Column | Type | Meaning |
|---|---|---|
| ticket_id | bigint PK | Internal key. Users never say this. |
| ticket_number | text, unique | The ticket users mean, e.g. `INC-55821`. Match it as text. |
| outage_id | bigint FK → outages.outage_id | The outage this ticket is for. |
| status | text | `open`, `in_progress`, `resolved`, `closed`. |
| priority | text | `low`, `medium`, `high`, `critical`. May be escalated above the outage's priority. |
| assigned_user_id | bigint FK → users.user_id | Current assignee. NULL = unassigned. |
| created_at | timestamptz | **Business time the ticket was opened** (not the row insert time). |
| updated_at | timestamptz | **Business time of the last ticket change.** |
| resolved_at | timestamptz | When resolved. NULL = not resolved yet. |
| is_resolved | boolean | Generated: `resolved_at IS NOT NULL`. |

`status` is `resolved` or `closed` exactly when `resolved_at` is set.

## Columns: ops.ticket_assignments (history)
`ticket_id`, `user_id`, `assigned_at`, `unassigned_at`. The current assignee's row has `unassigned_at IS NULL` and matches `tickets.assigned_user_id`. A ticket with two or more rows was **reassigned**.

## Gotchas
- **No ticket is a valid answer.** If an outage has no row in `tickets`, say "no ticket was created". Do not invent one. An INNER JOIN from outages to tickets silently drops these outages, so use LEFT JOIN.
- **Several tickets per outage.** A join from outages to tickets can return more than one row for one outage. Do not assume one.
- **Assignee name.** `tickets.assigned_user_id` is a number; the person's name is `users.full_name`.
- **Ticket state is not outage state.** "Is the ticket resolved" uses this table. "Is the outage still happening" uses `outages.is_open`.
- **created_at here is a business time.** On other tables `created_at` is an audit column. Within tickets it is when the ticket was opened.

## Join paths
- Outage: `tickets.outage_id = outages.outage_id`.
- Assignee: `tickets.assigned_user_id = users.user_id` (LEFT JOIN, may be NULL).
- History: `ticket_assignments.ticket_id = tickets.ticket_id`.

## Typical questions
Who is assigned to ticket INC-X, tickets still open, tickets per team, outages without a ticket, how long to resolve, reassigned tickets.
