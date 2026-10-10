---
doc_type: relationship
tables: [outages, sites, tickets, users, outage_root_causes, root_causes, impacted_services, alarms, outage_updates]
schema: ops
schema_version: 1
---
# Join paths from an outage

`outages.outage_id` is the hub. Every other table reaches it directly or through one hop.

| To get | Join | Join type | Watch out |
|---|---|---|---|
| Site code, city, region | `outages.site_id = sites.site_id` | INNER | none |
| Tickets | `tickets.outage_id = outages.outage_id` | LEFT | zero, one or several rows per outage |
| Ticket assignee name | `tickets.assigned_user_id = users.user_id` | LEFT (from tickets) | NULL when unassigned |
| Primary root cause | `outage_root_causes.outage_id = outages.outage_id AND outage_root_causes.is_primary`, then `root_causes.root_cause_id = outage_root_causes.root_cause_id` | LEFT | an ongoing outage may have none yet |
| All root causes | the same without `is_primary` | LEFT | several rows per outage |
| Customers impacted | `impacted_services.outage_id = outages.outage_id`, aggregate with `SUM(customers_impacted)` | LEFT, aggregated | summing after joining other many-rows tables inflates the total; aggregate in a subquery |
| Alarms | `alarms.outage_id = outages.outage_id` | LEFT | many rows; some outages have none |
| Timeline / last update | `outage_updates.outage_id = outages.outage_id`, order by `posted_at` | LEFT | latest = highest `posted_at` |

## Rules of thumb
- Start the FROM clause at `outages`, and LEFT JOIN anything that may be missing, so an outage without a ticket or root cause still appears.
- Never join two one-to-many tables (tickets, alarms, impacted_services) in the same query without aggregating one of them first. The rows multiply.
- There is no direct link between `users` and `outages`. Go through `tickets`.
