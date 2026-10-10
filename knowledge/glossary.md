---
doc_type: glossary
tables: [outages, tickets, sites]
schema: ops
schema_version: 1
---
# Business glossary

| Term | Meaning | Where it lives |
|---|---|---|
| RAN | Radio Access Network: the radio part of the network (cell sites, antennas, radio units). | `outages.network_domain = 'RAN'` |
| Core | The central network that handles signaling, sessions and subscriber data. | `outages.network_domain = 'Core'` |
| Transport | The links (fiber, microwave) that connect sites to the core. Also called backhaul. | `outages.network_domain = 'Transport'` |
| OOS | Out of Service outage: the site or cell is not serving customers. | `outages.outage_type = 'OOS'` |
| SC (Sleepy Cell) | A cell that looks healthy but is not carrying traffic properly. | `outages.outage_type = 'SC'` |
| TIS (Top Impaired Site) | A site flagged as among the most degraded. | `outages.outage_type = 'TIS'` |
| MO (Micro Outage) | A very short outage, typically minutes. | `outages.outage_type = 'MO'` |
| Priority | How urgent: low, medium, high, critical. Outages and tickets each have their own. | `outages.priority`, `tickets.priority` |
| Open / ongoing / active outage | The outage has not ended. | `outages.is_open = true` (`end_time IS NULL`) |
| Resolved ticket | The ticket has a resolution time. | `tickets.is_resolved`, `tickets.resolved_at` |
| Duration | `end_time - start_time`. Undefined for open outages. | derived |
| MTTR (Mean Time To Restore) | Average outage duration, over ended outages only. | `AVG(end_time - start_time)` where `end_time IS NOT NULL` |
| Cell | One radio coverage unit at a site. | `outages.cells_affected` |
| Customers impacted | People affected, counted per service. | `SUM(impacted_services.customers_impacted)` |
| Root cause | Why it happened: category and subcategory. | `root_causes`, via `outage_root_causes` |

## Mapping user phrases to columns
| User says | Use |
|---|---|
| "outage 1234", "outage number 1234" | `outages.outage_id = 1234` |
| "ticket INC-55821", "incident INC-55821" | `tickets.ticket_number = 'INC-55821'` |
| "site NJ-EDISON-042" | `sites.site_code = 'NJ-EDISON-042'` |
| "assigned to Priya Shah" | `users.full_name = 'Priya Shah'` |
| "RAN outage" | `outages.network_domain = 'RAN'` (not `outage_type`) |
| "critical outage" | `outages.priority = 'critical'` |
| "yesterday", "this week" | convert `start_time` to America/New_York first |
