"""Deterministic formatting and grounding checks. Code, not the LLM, converts times to Eastern,
formats durations and numbers, and later verifies the prose only states facts present in the rows."""
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


def format_timestamp(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(ET).strftime("%Y-%m-%d %H:%M %Z")


def format_value(value, type_name: str, name: str = ""):
    if value is None:
        return None
    if name == "id" or name.endswith("_id"):
        return str(value)  # identifiers are labels, not quantities: 1234, never 1,234
    if type_name == "timestamptz":
        return format_timestamp(value)
    if type_name == "interval":
        return format_duration(value)
    if type_name == "bool":
        return "yes" if value else "no"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def build_facts(exec_result: dict, data_as_of: str) -> dict:
    """Display-ready facts from an MCP run_query result."""
    columns = exec_result["columns"]
    names = [c["name"] for c in columns]
    as_of = datetime.fromisoformat(data_as_of).replace(tzinfo=timezone.utc)
    rows, missing_by_row = [], []
    for raw in exec_result["rows"]:
        row = {c["name"]: format_value(v, c["type"], c["name"]) for c, v in zip(columns, raw)}
        raw_by_name = dict(zip(names, raw))
        # Derived, deterministic lifecycle facts for rows that carry start/end times.
        start, end = raw_by_name.get("start_time"), raw_by_name.get("end_time")
        if start is not None and "end_time" in raw_by_name:
            if end is not None:
                secs = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
                row["duration"] = format_duration(secs)
            else:
                elapsed = (as_of - datetime.fromisoformat(start)).total_seconds()
                row["status"] = (f"ongoing; no end time recorded; about {format_duration(max(elapsed, 0))} "
                                 f"elapsed as of the {data_as_of} data snapshot")
                row.pop("end_time", None)
        rows.append({k: v for k, v in row.items() if v is not None})
        missing_by_row.append([n for n in names if raw_by_name[n] is None and n != "end_time"])
    facts = {"row_count": exec_result["row_count"], "rows": rows}
    if any(missing_by_row):
        facts["missing"] = missing_by_row
    if exec_result.get("truncated"):
        facts["truncated"] = f"only the first {exec_result['row_count']} rows are included"
    return facts


def facts_json(facts: dict) -> str:
    return json.dumps(facts, indent=1, ensure_ascii=False)


_NUMBER = re.compile(r"\d[\d,]*\.?\d*")
_CODE = re.compile(r"\b(?:INC-\d+|[A-Z]{2}-[A-Z-]+-\d{3})\b")


def _flatten(facts: dict) -> str:
    return json.dumps(facts, ensure_ascii=False).replace(",", "")


def faithfulness_violations(answer: str, facts: dict) -> list[str]:
    """Numbers and codes in the answer that are not in the facts (an empty list means grounded).
    Small standalone digits (1-9) are allowed: they appear in ordinary prose ("one of", "2 tickets")
    but only when they equal the row count or appear in the facts."""
    haystack = _flatten(facts)
    allowed_small = {str(facts["row_count"])}
    bad = []
    for code in _CODE.findall(answer):
        if code not in haystack:
            bad.append(code)
    cleaned = _CODE.sub(" ", answer)
    for token in _NUMBER.findall(cleaned):
        t = token.rstrip(".,").replace(",", "")
        if not t:
            continue
        if len(t) == 1 and (t in allowed_small or t in haystack):
            continue
        if t not in haystack:
            bad.append(token)
    return bad


def template_answer(facts: dict) -> str:
    """Deterministic fallback used when the LLM prose fails the grounding check."""
    if facts["row_count"] == 0:
        return "No matching records were found."
    lines = []
    for i, row in enumerate(facts["rows"][:10]):
        lines.append("- " + "; ".join(f"{k}: {v}" for k, v in row.items()))
    missing = facts.get("missing")
    text = f"{facts['row_count']} row(s):\n" + "\n".join(lines)
    if missing and any(missing):
        text += "\nNot available: " + ", ".join(sorted({m for row in missing for m in row}))
    if facts.get("truncated"):
        text += "\n(Only the first rows are shown.)"
    return text
