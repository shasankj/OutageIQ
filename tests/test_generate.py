"""Invariants of the synthetic data. They mirror the DB constraints so a generator bug fails
here, in milliseconds, instead of during a load."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from datagen.generate import AS_OF, N_OUTAGES, generate


@pytest.fixture(scope="module")
def data():
    return generate()


def test_is_deterministic(data):
    assert generate() == data


def test_row_counts(data):
    tables, _ = data
    assert len(tables["outages"]) == N_OUTAGES
    assert len(tables["sites"]) == 60 and len(tables["users"]) == 24


def test_ids_unique_and_foreign_keys_resolve(data):
    t, _ = data
    outage_ids = {o["outage_id"] for o in t["outages"]}
    assert len(outage_ids) == len(t["outages"])
    ticket_ids = {x["ticket_id"] for x in t["tickets"]}
    assert len(ticket_ids) == len(t["tickets"])
    assert {o["site_id"] for o in t["outages"]} <= {s["site_id"] for s in t["sites"]}
    for table in ("alarms", "outage_updates", "tickets", "impacted_services", "outage_root_causes"):
        assert {r["outage_id"] for r in t[table]} <= outage_ids, table
    assert {a["ticket_id"] for a in t["ticket_assignments"]} <= ticket_ids
    user_ids = {u["user_id"] for u in t["users"]}
    assert {x["assigned_user_id"] for x in t["tickets"]} - {None} <= user_ids


def test_outage_time_rules(data):
    t, _ = data
    for o in t["outages"]:
        assert o["start_time"] < AS_OF
        assert o["end_time"] is None or o["start_time"] <= o["end_time"] <= AS_OF


def test_ticket_rules(data):
    t, _ = data
    numbers = [x["ticket_number"] for x in t["tickets"]]
    assert len(set(numbers)) == len(numbers)
    for x in t["tickets"]:
        assert re.fullmatch(r"INC-\d+", x["ticket_number"])
        assert (x["status"] in ("resolved", "closed")) == (x["resolved_at"] is not None)
        assert x["resolved_at"] is None or x["resolved_at"] >= x["created_at"]
        assert x["created_at"] <= x["updated_at"] <= AS_OF + timedelta(hours=1)


def test_alarm_and_assignment_rules(data):
    t, _ = data
    for a in t["alarms"]:
        assert a["cleared_at"] is None or a["cleared_at"] >= a["raised_at"]
    for a in t["ticket_assignments"]:
        assert a["unassigned_at"] is None or a["unassigned_at"] >= a["assigned_at"]


def test_one_primary_root_cause_per_outage(data):
    t, _ = data
    primaries = [r["outage_id"] for r in t["outage_root_causes"] if r["is_primary"]]
    assert len(primaries) == len(set(primaries))


def test_showcase_outage_1234(data):
    t, m = data
    o = next(o for o in t["outages"] if o["outage_id"] == 1234)
    assert (o["network_domain"], o["priority"], o["cells_affected"]) == ("RAN", "critical", 3)
    assert o["end_time"] - o["start_time"] == timedelta(hours=3, minutes=35)
    assert next(s for s in t["sites"] if s["site_id"] == o["site_id"])["site_code"] == "NJ-EDISON-042"
    assert sum(s["customers_impacted"] for s in t["impacted_services"] if s["outage_id"] == 1234) == 1850
    ticket = next(x for x in t["tickets"] if x["outage_id"] == 1234)
    assert ticket["ticket_number"] == "INC-55821"
    assert next(u for u in t["users"] if u["user_id"] == ticket["assigned_user_id"])["full_name"] == "Priya Shah"


def test_edge_cases_are_present_and_correct(data):
    t, m = data
    tickets_by_outage = {}
    for x in t["tickets"]:
        tickets_by_outage.setdefault(x["outage_id"], []).append(x)
    assert len(m["ongoing_outage_ids"]) >= 5
    for oid in m["ongoing_outage_ids"]:
        assert next(o for o in t["outages"] if o["outage_id"] == oid)["end_time"] is None
    assert len(m["no_ticket_outage_ids"]) >= 50
    assert all(oid not in tickets_by_outage for oid in m["no_ticket_outage_ids"])
    assert len(m["multi_root_cause_outage_ids"]) >= 20
    assert len(m["multi_ticket_outage_ids"]) >= 5
    assert len(m["reassigned_ticket_ids"]) >= 20
    assert len(m["unassigned_ticket_ids"]) >= 5
    assert 1234 not in m["no_ticket_outage_ids"] and 1234 not in m["ongoing_outage_ids"]
    assert not set(m["nonexistent_outage_ids"]) & {o["outage_id"] for o in t["outages"]}
