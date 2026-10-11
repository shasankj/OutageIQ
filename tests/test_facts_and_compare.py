from agent import facts as F
from evals.compare import golden_values_in_answer, results_match
from tests.fakes import rows_result

COLS = [("outage_id", "int8"), ("start_time", "timestamptz"), ("end_time", "timestamptz"), ("ticket_number", "text")]


def test_duration_and_time_formatting():
    assert F.format_duration(12900) == "3 h 35 min"
    assert F.format_duration(90000) == "1 d 1 h 0 min"
    assert F.format_timestamp("2026-09-14T12:12:00+00:00") == "2026-09-14 08:12 EDT"  # UTC -> Eastern (DST)
    assert F.format_timestamp("2026-01-14T13:12:00+00:00") == "2026-01-14 08:12 EST"


def test_closed_outage_gets_a_code_computed_duration_and_missing_ticket_is_flagged():
    res = rows_result(COLS, [[1234, "2026-09-14T12:12:00+00:00", "2026-09-14T15:47:00+00:00", None]])
    facts = F.build_facts(res, "2026-10-01")
    row = facts["rows"][0]
    assert row["duration"] == "3 h 35 min" and row["start_time"] == "2026-09-14 08:12 EDT"
    assert "ticket_number" not in row and facts["missing"] == [["ticket_number"]]


def test_open_outage_has_no_duration_and_no_end_time():
    res = rows_result(COLS, [[1305, "2026-09-20T10:41:23+00:00", None, "INC-51848"]])
    row = F.build_facts(res, "2026-10-01")["rows"][0]
    assert "duration" not in row and "end_time" not in row
    assert row["status"].startswith("ongoing") and "elapsed" in row["status"]


def test_numbers_are_grouped_for_display():
    assert F.format_value(1420, "int8") == "1,420" and F.format_value(12.0, "numeric") == "12"
    assert F.format_value(12.34, "numeric") == "12.34" and F.format_value(True, "bool") == "yes"


def test_faithfulness_accepts_grounded_and_rejects_invented_values():
    res = rows_result([("outage_id", "int8"), ("customers", "int8"), ("ticket_number", "text")],
                      [[1234, 1850, "INC-55821"]])
    facts = F.build_facts(res, "2026-10-01")
    assert F.faithfulness_violations("Outage **1234** affected **1,850** customers (**INC-55821**).", facts) == []
    assert F.faithfulness_violations("It affected 2,000 customers.", facts) == ["2,000"]
    assert F.faithfulness_violations("See INC-99999.", facts) == ["INC-99999"]


def test_results_match_ignores_row_order_aliases_and_extra_columns():
    golden = [[1234, "critical"], [9, "low"]]
    assert results_match(golden, [[9, "low"], [1234, "critical"]], strict=True)
    assert not results_match(golden, [[9, "low"], [1234, "high"]])
    extra = [[9, "x", "low"], [1234, "y", "critical"]]  # an extra identifying column in the middle
    assert results_match(golden, extra) and not results_match(golden, extra, strict=True)
    assert not results_match(golden, [[1234, "critical"]])  # missing a row
    assert results_match([[1.234]], [[1.2301]])  # rounding to 2 decimals


def test_results_match_is_not_fooled_by_columns_that_swap_values():
    golden = [[1, 2], [2, 1]]
    assert results_match(golden, [[1, 2], [2, 1]]) and not results_match(golden, [[1, 1], [2, 2]])


def test_golden_values_in_answer():
    cols = [{"name": "outage_count", "type": "int8"}, {"name": "site_code", "type": "text"}]
    ok, missing = golden_values_in_answer(cols, [[1420, "NJ-EDISON-042"]], "There are 1,420 outages at NJ-EDISON-042.")
    assert ok and missing == []
    ok, missing = golden_values_in_answer(cols, [[1420, "NJ-EDISON-042"]], "There are many outages.")
    assert not ok and len(missing) == 2
    zero = [{"name": "ticket_count", "type": "int8"}]
    assert golden_values_in_answer(zero, [[0]], "No, no ticket was created.")[0]


def test_identifiers_are_never_given_thousands_separators():
    assert F.format_value(1234, "int8", "outage_id") == "1234"
    assert F.format_value(1234, "int8", "customers_impacted") == "1,234"
    res = rows_result([("outage_id", "int8"), ("site_id", "int8")], [[1234, 60]])
    assert F.build_facts(res, "2026-10-01")["rows"][0] == {"outage_id": "1234", "site_id": "60"}
