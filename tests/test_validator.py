import pytest

from agent.validator import MAX_ROWS, validate
from common.knowledge import load_sections


def kind(sql):
    r = validate(sql)
    return None if r.ok else r.kind


def test_simple_select_passes_and_gets_limit():
    r = validate("SELECT o.outage_id FROM ops.outages o WHERE o.is_open")
    assert r.ok and f"LIMIT {MAX_ROWS}" in r.sql


def test_existing_small_limit_is_kept_and_large_one_is_clamped():
    assert "LIMIT 5" in validate("SELECT outage_id FROM ops.outages LIMIT 5").sql
    assert f"LIMIT {MAX_ROWS}" in validate("SELECT outage_id FROM ops.outages LIMIT 100000").sql


@pytest.mark.parametrize("sql,expected", [
    ("DELETE FROM ops.outages", "not_select"),
    ("UPDATE ops.tickets SET status = 'closed'", "not_select"),
    ("INSERT INTO ops.sites (site_code) VALUES ('x')", "not_select"),
    ("DROP TABLE ops.outages", "not_select"),
    ("TRUNCATE ops.outages", "not_select"),
    ("SELECT * INTO ops.copy FROM ops.outages", "not_select"),
    ("SELECT outage_id FROM ops.outages FOR UPDATE", "not_select"),
    ("SELECT 1; DROP TABLE ops.outages", "multiple_statements"),
    ("SELECT outage_id FROM ops.outages; SELECT 1", "multiple_statements"),
    ("SELEC outage_id FRM ops.outages", "syntax"),
    ("SELECT outage_id FROM outages", "unqualified_table"),
    ("SELECT * FROM rag.chunks", "unknown_table"),
    ("SELECT * FROM pg_catalog.pg_user", "unknown_table"),
    ("SELECT * FROM information_schema.tables", "unknown_table"),
    ("SELECT * FROM ops.nonexistent", "unknown_table"),
    ("SELECT o.end_date FROM ops.outages o", "unknown_column"),
    ("SELECT outage_id, pg_sleep(10) FROM ops.outages", "forbidden"),
    ("SELECT pg_read_file('/etc/passwd')", "forbidden"),
    ("SELECT nextval('ops.sites_site_id_seq')", "forbidden"),
    ("SELECT setval('ops.sites_site_id_seq', 1)", "forbidden"),
])
def test_rejects_bad_sql_with_the_right_kind(sql, expected):
    assert kind(sql) == expected


def test_unknown_column_message_names_the_column():
    r = validate("SELECT o.end_date FROM ops.outages o")
    assert "end_date" in r.errors[0]


def test_cte_and_union_are_allowed():
    assert validate("WITH a AS (SELECT outage_id FROM ops.outages) SELECT outage_id FROM a").ok
    assert validate("SELECT outage_id FROM ops.outages UNION SELECT ticket_id FROM ops.tickets").ok


def test_comments_cannot_smuggle_a_second_statement():
    assert kind("SELECT 1 /* ; DROP TABLE ops.outages */") in (None, "unknown_table")
    assert kind("SELECT outage_id FROM ops.outages -- ; DROP TABLE x") is None


def test_every_knowledge_example_passes_the_validator():
    for s in load_sections():
        if s.meta.get("type") == "example":
            for sql in s.sql_blocks:
                r = validate(sql)
                assert r.ok, f"{s.heading}: {r.errors}"
