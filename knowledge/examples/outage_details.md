---
doc_type: example
tables: [outages, sites, tickets, users, outage_root_causes, root_causes, impacted_services]
schema: ops
schema_version: 1
---
# Example: details of one outage

**Question.** What are the details of outage 1234?

**Why this shape.** Start from `outages`. LEFT JOIN everything optional (ticket, assignee, root cause) so a missing ticket shows as NULL instead of dropping the outage. Total customers come from a subquery so other joins cannot multiply the sum. No duration is computed here; the application derives it, and only when `end_time` is not NULL.

```sql
SELECT o.outage_id, s.site_code, o.outage_type, o.network_domain, o.priority,
       o.start_time, o.end_time, o.is_open, o.cells_affected,
       (SELECT COALESCE(SUM(i.customers_impacted), 0)
          FROM ops.impacted_services i WHERE i.outage_id = o.outage_id) AS customers_impacted,
       rc.category AS root_cause_category, rc.subcategory AS root_cause_subcategory,
       rc.description AS root_cause_description,
       t.ticket_number, t.status AS ticket_status, t.created_at AS ticket_created_at,
       u.full_name AS assignee, u.team AS assignee_team, u.region AS assignee_region
FROM ops.outages o
JOIN ops.sites s ON s.site_id = o.site_id
LEFT JOIN ops.outage_root_causes orc ON orc.outage_id = o.outage_id AND orc.is_primary
LEFT JOIN ops.root_causes rc ON rc.root_cause_id = orc.root_cause_id
LEFT JOIN ops.tickets t ON t.outage_id = o.outage_id
LEFT JOIN ops.users u ON u.user_id = t.assigned_user_id
WHERE o.outage_id = 1234;
```

**If zero rows come back:** the outage does not exist. Say so. **If ticket columns are NULL:** the outage exists with no ticket. Say "no ticket was created".

The latest update is a separate query: `SELECT update_text, posted_at FROM ops.outage_updates WHERE outage_id = 1234 ORDER BY posted_at DESC LIMIT 1;`
