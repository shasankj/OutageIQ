---
doc_type: table
tables: [sites]
schema: ops
schema_version: 1
---
# Table ops.sites

**Purpose.** One row per cell site (physical location). Used to turn a `site_id` into a readable site code, city, state and region, and to filter outages by place.

## Columns
| Column | Type | Meaning |
|---|---|---|
| site_id | bigint PK | Internal key. Joined from `outages.site_id` and `alarms.site_id`. |
| site_code | text, unique | What users call the site, e.g. `NJ-EDISON-042` (state, city, number). |
| site_name | text | Descriptive name, e.g. "Edison Site 042". |
| region | text | Operations region: `NJ-North`, `NJ-Central`, `NJ-South`, `NY-Metro`, `PA-East`, `CT-South`. |
| state | char(2) | Two-letter state code. |
| city | text | City name, capitalised ("Jersey City"). |

## Gotchas
- **Match on `site_code`, not `site_name`**, when a question gives something like NJ-EDISON-042.
- **`region` is not `state`.** NJ has three regions. "Central New Jersey" means `region = 'NJ-Central'`; "New Jersey" means `state = 'NJ'`.
- **`users.region` is separate.** It describes where a person works, not where an outage happened. Do not join `users` to `sites` through region.

## Join paths
`outages.site_id = sites.site_id` (inner join is safe). `alarms.site_id = sites.site_id`.

## Typical questions
Outages at a site, outages per region, sites with the most outages, which site had outage N.
