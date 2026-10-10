# 0004: Naming and audit conventions

Status: accepted (Phase 0)

## Context
Ambiguous column names are a top cause of wrong SQL (a bare `id` in every table, `user` meaning id or name).

## Decision
- Primary keys are `<entity>_id` (`outage_id`, `ticket_id`, `user_id`, `site_id`). Never a bare `id`.
- Foreign keys reuse the referenced PK name, so joins read `ON o.site_id = s.site_id`.
- Business keys get distinct names: `tickets.ticket_number` ("INC-55821"), `sites.site_code` ("NJ-EDISON-042"). Names of people are `full_name`.
- Every table has audit columns: `created_at`, `updated_at` (both `timestamptz`, default `now()`), and `created_by`.
- Enumerated values use CHECK constraints, and their allowed values are listed in the knowledge docs.
- Tables and columns carry `COMMENT ON`, used as raw material for the knowledge base.
- Glossary maps user phrasing to columns ("outage 1234" → `outages.outage_id`; "ticket INC-…" → `tickets.ticket_number`).

## Consequences
Unique names cost a few extra characters but remove a whole class of join and column-choice errors. We will measure this later by ablation (Phase 8).
