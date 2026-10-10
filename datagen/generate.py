"""Deterministic synthetic data for OutageIQ. Pure Python: no database access here.

generate() returns (tables, manifest). `tables` maps table name -> list of row dicts, in
foreign-key load order. `manifest` lists ids of deliberate edge cases for tests and evals.
All data is invented. "As of" time is fixed so the data never shifts (no now()).
"""
import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from faker import Faker

SEED = 42
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)
RANGE_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
N_SITES, N_USERS, N_OUTAGES = 60, 24, 1420
SHOWCASE_OUTAGE_ID = 1234
SHOWCASE_SITE_ID = 42
SHOWCASE_TICKET_NUMBER = "INC-55821"
NONEXISTENT_OUTAGE_IDS = [99999, 0, 5000]

CITIES = [  # (city, state, region); index 5 makes site 42 = NJ-EDISON-042
    ("Newark", "NJ", "NJ-North"), ("Jersey City", "NJ", "NJ-North"), ("Paterson", "NJ", "NJ-North"),
    ("Trenton", "NJ", "NJ-South"), ("Camden", "NJ", "NJ-South"), ("Edison", "NJ", "NJ-Central"),
    ("New Brunswick", "NJ", "NJ-Central"), ("Princeton", "NJ", "NJ-Central"),
    ("Brooklyn", "NY", "NY-Metro"), ("Yonkers", "NY", "NY-Metro"),
    ("Philadelphia", "PA", "PA-East"), ("Stamford", "CT", "CT-South"),
]
TEAMS = ["Field Ops"] * 8 + ["NOC"] * 6 + ["Transport Engineering"] * 5 + ["RAN Engineering"] * 5

# (category, subcategory, description, domains it can occur in)
ROOT_CAUSES = [
    ("Transport", "Physical", "Fiber cut on the backhaul link", ("Transport", "RAN")),
    ("Transport", "Equipment", "Router or switch failure", ("Transport",)),
    ("Power", "Commercial power", "Utility power loss at the site", ("RAN", "Transport")),
    ("Power", "Backup power", "Battery or generator failure", ("RAN", "Transport")),
    ("RAN Hardware", "Radio unit", "Radio unit hardware failure", ("RAN",)),
    ("RAN Hardware", "Antenna and cabling", "Antenna, feeder or cable fault", ("RAN",)),
    ("Software", "Configuration", "Bad configuration change", ("RAN", "Core", "Transport")),
    ("Software", "Upgrade defect", "Software defect after an upgrade", ("RAN", "Core")),
    ("Core", "Signaling", "Signaling overload", ("Core",)),
    ("Core", "Server", "Database or server failure", ("Core",)),
    ("Environmental", "Weather", "Storm or flood damage", ("RAN", "Transport")),
    ("Third Party", "Vendor or utility", "Issue at a vendor or utility", ("RAN", "Core", "Transport")),
    ("Planned Work", "Maintenance overrun", "Maintenance window overran", ("RAN", "Core", "Transport")),
    ("Unknown", "Under investigation", "Cause not yet determined", ("RAN", "Core", "Transport")),
]
SERVICES = ["voice", "data", "sms", "5G data"]
ALARM_CODES = {
    "RAN": [("RRU-LINK-DOWN", "Radio unit link down"), ("CELL-UNAVAIL", "Cell unavailable"),
            ("VSWR-HIGH", "Antenna VSWR threshold exceeded")],
    "Core": [("SIG-OVERLOAD", "Signaling overload"), ("DB-REPL-LAG", "Database replication lag")],
    "Transport": [("LOS", "Loss of signal"), ("LINK-FLAP", "Link flapping"), ("PKT-LOSS", "Packet loss high")],
}
PROGRESS_NOTES = [
    "Alarm acknowledged by NOC; investigating.", "Field team dispatched to site.",
    "Vendor engaged for support.", "Partial service restored; monitoring.",
    "Root cause isolated; repair in progress.",
]
PRIORITIES = ["low", "medium", "high", "critical"]
ET = ZoneInfo("America/New_York")


def _pick(rng, weighted):
    return rng.choices([v for v, _ in weighted], weights=[w for _, w in weighted])[0]


def _duration(rng, outage_type):
    median_minutes = {"OOS": 180, "SC": 720, "TIS": 2160, "MO": 8}[outage_type]
    minutes = rng.lognormvariate(math.log(median_minutes), 0.8)
    return timedelta(minutes=max(3, minutes))


def _make_ticket(rng, ticket_id, number, outage, created, users):
    """One ticket plus its assignment rows. Returns (ticket, assignments, is_reassigned)."""
    end = outage["end_time"]
    status, resolved_at = "open", None
    if end is not None:
        resolved = max(end, created) + timedelta(seconds=rng.uniform(60, 3600))
        if resolved <= AS_OF:
            resolved_at = resolved
            status = "closed" if rng.random() < 0.7 else "resolved"
    if resolved_at is None and rng.random() < 0.6:
        status = "in_progress"
    updated = resolved_at or min(AS_OF, created + timedelta(minutes=rng.uniform(5, 600)))
    priority = outage["priority"]
    if rng.random() < 0.15 and priority != "critical":
        priority = PRIORITIES[PRIORITIES.index(priority) + 1]  # escalated
    ticket = {
        "ticket_id": ticket_id, "ticket_number": number, "outage_id": outage["outage_id"],
        "status": status, "priority": priority, "assigned_user_id": None,
        "created_at": created, "updated_at": updated, "resolved_at": resolved_at,
    }
    assignments, reassigned = [], False
    if rng.random() >= 0.04:  # 4% stay unassigned
        first = rng.choice(users)["user_id"]
        t1 = created + timedelta(minutes=1)
        if rng.random() < 0.12 and updated > t1 + timedelta(minutes=10):
            second = rng.choice([u for u in users if u["user_id"] != first])["user_id"]
            t2 = t1 + (updated - t1) * rng.uniform(0.2, 0.7)
            assignments.append({"ticket_id": ticket_id, "user_id": first, "assigned_at": t1, "unassigned_at": t2})
            assignments.append({"ticket_id": ticket_id, "user_id": second, "assigned_at": t2, "unassigned_at": None})
            ticket["assigned_user_id"], reassigned = second, True
        else:
            assignments.append({"ticket_id": ticket_id, "user_id": first, "assigned_at": t1, "unassigned_at": None})
            ticket["assigned_user_id"] = first
    return ticket, assignments, reassigned


def generate():
    rng = random.Random(SEED)
    fake = Faker("en_US")
    fake.seed_instance(SEED)

    sites = []
    for i in range(1, N_SITES + 1):
        city, state, region = CITIES[(i - 1) % len(CITIES)]
        sites.append({
            "site_id": i, "site_code": f"{state}-{city.upper().replace(' ', '-')}-{i:03d}",
            "site_name": f"{city} Site {i:03d}", "region": region, "state": state, "city": city})

    users = []
    for i in range(1, N_USERS + 1):
        name = "Priya Shah" if i == 1 else fake.name()
        team, region = ("Field Ops", "NJ-Central") if i == 1 else (TEAMS[i - 1], rng.choice(CITIES)[2])
        users.append({"user_id": i, "full_name": name, "team": team, "region": region,
                      "email": f"{name.lower().replace(' ', '.').replace('\'', '')}.{i}@example.com"})

    root_causes = [{"root_cause_id": i, "category": c, "subcategory": s, "description": d}
                   for i, (c, s, d, _) in enumerate(ROOT_CAUSES, 1)]
    causes_by_domain = {dom: [rc["root_cause_id"] for rc, (_, _, _, doms) in zip(root_causes, ROOT_CAUSES)
                              if dom in doms] for dom in ("RAN", "Core", "Transport")}

    # Outages: sorted start times so outage_id increases with time.
    span = (AS_OF - RANGE_START).total_seconds()
    starts = sorted(RANGE_START + timedelta(seconds=rng.uniform(0, span)) for _ in range(N_OUTAGES))
    outages, ongoing = [], []
    for oid, start in enumerate(starts, 1):
        otype = _pick(rng, [("OOS", .35), ("SC", .25), ("TIS", .10), ("MO", .30)])
        end = start + _duration(rng, otype)
        if end > AS_OF:
            end = None
            ongoing.append(oid)
        outages.append({
            "outage_id": oid, "site_id": rng.randint(1, N_SITES), "outage_type": otype,
            "network_domain": _pick(rng, [("RAN", .6), ("Core", .15), ("Transport", .25)]),
            "priority": _pick(rng, [("low", .3), ("medium", .35), ("high", .25), ("critical", .1)]),
            "start_time": start, "end_time": end,
            "cells_affected": 1 if otype == "MO" else rng.randint(1, 12)})

    # Showcase outage 1234 (matches the example answer in CLAUDE.md section 4).
    showcase = outages[SHOWCASE_OUTAGE_ID - 1]
    showcase.update(
        site_id=SHOWCASE_SITE_ID, outage_type="OOS", network_domain="RAN", priority="critical",
        start_time=datetime(2026, 9, 14, 8, 12, tzinfo=ET).astimezone(timezone.utc),
        end_time=datetime(2026, 9, 14, 11, 47, tzinfo=ET).astimezone(timezone.utc), cells_affected=3)
    if SHOWCASE_OUTAGE_ID in ongoing:
        ongoing.remove(SHOWCASE_OUTAGE_ID)

    outage_root_causes, alarms, updates, tickets, assignments, services = [], [], [], [], [], []
    no_ticket, multi_cause, multi_ticket, reassigned_tickets, no_alarm = [], [], [], [], []
    ticket_numbers = iter(rng.sample([n for n in range(50000, 60000) if n != 55821], 5000))
    ticket_id = alarm_id = update_id = service_id = 0

    for o in outages:
        oid, start, end = o["outage_id"], o["start_time"], o["end_time"]
        if oid == SHOWCASE_OUTAGE_ID:
            continue  # built by hand below
        elapsed = ((end or AS_OF) - start).total_seconds()

        # root causes: ongoing outages often have none yet; 10% of the rest have two
        if end is None and rng.random() < 0.6:
            chosen = []
        else:
            pool = causes_by_domain[o["network_domain"]]
            chosen = rng.sample(pool, 2 if rng.random() < 0.10 else 1)
        for i, rc in enumerate(chosen):
            outage_root_causes.append({"outage_id": oid, "root_cause_id": rc, "is_primary": i == 0})
        if len(chosen) > 1:
            multi_cause.append(oid)

        n_alarms = 0 if rng.random() < 0.05 else rng.randint(1, 6)
        if n_alarms == 0:
            no_alarm.append(oid)
        for _ in range(n_alarms):
            alarm_id += 1
            code, text = rng.choice(ALARM_CODES[o["network_domain"]])
            raised = start + timedelta(seconds=rng.uniform(0, 0.3 * elapsed))
            cleared = None if end is None and rng.random() < 0.7 else \
                max(raised, (end or AS_OF) - timedelta(seconds=rng.uniform(0, 0.1 * elapsed)))
            alarms.append({"alarm_id": alarm_id, "outage_id": oid, "site_id": o["site_id"], "alarm_code": code,
                           "severity": rng.choice(["warning", "minor", "major", "critical"]),
                           "description": text, "raised_at": raised, "cleared_at": cleared})

        stamps = sorted(start + timedelta(seconds=rng.uniform(0.05, 0.9) * elapsed) for _ in range(rng.randint(1, 4)))
        for t in stamps:
            update_id += 1
            updates.append({"outage_update_id": update_id, "outage_id": oid, "posted_by_user_id": rng.choice(users)["user_id"],
                            "posted_at": t, "update_text": rng.choice(PROGRESS_NOTES)})
        if end is not None:
            update_id += 1
            updates.append({"outage_update_id": update_id, "outage_id": oid, "posted_by_user_id": rng.choice(users)["user_id"],
                            "posted_at": end - timedelta(minutes=1), "update_text": "Service restored; closing out."})

        for name in rng.sample(SERVICES, rng.randint(1, 3)):
            service_id += 1
            services.append({"impacted_service_id": service_id, "outage_id": oid, "service_name": name,
                             "customers_impacted": rng.randint(50, 900) * o["cells_affected"]})

        if rng.random() < 0.15:
            no_ticket.append(oid)
        else:
            n_tickets = 2 if rng.random() < 0.03 else 1
            for k in range(n_tickets):
                ticket_id += 1
                created = min(AS_OF - timedelta(minutes=1), start + timedelta(
                    seconds=min(rng.uniform(60, 1800), 0.8 * elapsed) + k * rng.uniform(3600, 7200)))
                t, a, re = _make_ticket(rng, ticket_id, f"INC-{next(ticket_numbers)}", o, created, users)
                tickets.append(t); assignments.extend(a)
                if re:
                    reassigned_tickets.append(ticket_id)
            if n_tickets == 2:
                multi_ticket.append(oid)

    # --- outage 1234, by hand
    oid, start, end = SHOWCASE_OUTAGE_ID, showcase["start_time"], showcase["end_time"]
    outage_root_causes.append({"outage_id": oid, "root_cause_id": 1, "is_primary": True})  # fiber cut
    alarm_id += 2
    alarms += [
        {"alarm_id": alarm_id - 1, "outage_id": oid, "site_id": SHOWCASE_SITE_ID, "alarm_code": "RRU-LINK-DOWN",
         "severity": "critical", "description": "Radio unit link down", "raised_at": start + timedelta(minutes=1),
         "cleared_at": end - timedelta(minutes=2)},
        {"alarm_id": alarm_id, "outage_id": oid, "site_id": SHOWCASE_SITE_ID, "alarm_code": "CELL-UNAVAIL",
         "severity": "major", "description": "Cell unavailable", "raised_at": start + timedelta(minutes=2),
         "cleared_at": end - timedelta(minutes=1)}]
    for text, when in [("Field team dispatched to site.", start + timedelta(minutes=40)),
                       ("Fiber spliced and traffic restored.", end - timedelta(minutes=1))]:
        update_id += 1
        updates.append({"outage_update_id": update_id, "outage_id": oid, "posted_by_user_id": 1,
                        "posted_at": when, "update_text": text})
    for name, customers in [("voice", 700), ("data", 900), ("sms", 250)]:  # total 1,850
        service_id += 1
        services.append({"impacted_service_id": service_id, "outage_id": oid, "service_name": name,
                         "customers_impacted": customers})
    ticket_id += 1
    created = datetime(2026, 9, 14, 8, 20, tzinfo=ET).astimezone(timezone.utc)
    resolved = end + timedelta(minutes=30)
    tickets.append({"ticket_id": ticket_id, "ticket_number": SHOWCASE_TICKET_NUMBER, "outage_id": oid,
                    "status": "closed", "priority": "critical", "assigned_user_id": 1,
                    "created_at": created, "updated_at": resolved, "resolved_at": resolved})
    assignments.append({"ticket_id": ticket_id, "user_id": 1, "assigned_at": created + timedelta(minutes=1),
                        "unassigned_at": None})

    # number the assignment rows
    for i, a in enumerate(assignments, 1):
        a["ticket_assignment_id"] = i

    tables = {
        "sites": sites, "users": users, "root_causes": root_causes, "outages": outages,
        "outage_root_causes": outage_root_causes, "alarms": alarms, "outage_updates": updates,
        "tickets": tickets, "ticket_assignments": assignments, "impacted_services": services,
    }
    manifest = {
        "showcase_outage_id": SHOWCASE_OUTAGE_ID, "showcase_ticket_number": SHOWCASE_TICKET_NUMBER,
        "ongoing_outage_ids": ongoing, "no_ticket_outage_ids": no_ticket,
        "multi_root_cause_outage_ids": multi_cause, "multi_ticket_outage_ids": multi_ticket,
        "reassigned_ticket_ids": reassigned_tickets, "no_alarm_outage_ids": no_alarm,
        "unassigned_ticket_ids": [t["ticket_id"] for t in tickets if t["assigned_user_id"] is None],
        "nonexistent_outage_ids": NONEXISTENT_OUTAGE_IDS,
    }
    return tables, manifest
