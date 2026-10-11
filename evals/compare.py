"""Execution accuracy: does the generated query return the same RESULT as the golden query?

SQL text is a poor metric (many different queries are equally correct), so we compare result sets:
  strict   same rows, same columns by position, order-insensitive
  lenient  the generated result may carry extra columns; some set of its columns must reproduce the
           golden rows exactly (aliases and column order are ignored)
Values are normalised first (numbers rounded, ISO timestamps compared as instants).
"""
from collections import Counter
from datetime import datetime
from itertools import permutations

from agent import facts as F


def normalize_cell(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).timestamp() if "T" in v and v[:4].isdigit() else v.strip()
        except ValueError:
            return v.strip()
    return v


def _norm_rows(rows):
    return [tuple(normalize_cell(c) for c in row) for row in rows]


def results_match(golden_rows, got_rows, strict: bool = False) -> bool:
    g, r = _norm_rows(golden_rows), _norm_rows(got_rows)
    if len(g) != len(r):
        return False
    if not g:
        return True
    if strict:
        return Counter(g) == Counter(r)
    k, m = len(g[0]), len(r[0])
    if m < k:
        return False
    g_cols = [Counter(row[j] for row in g) for j in range(k)]
    candidates = [[i for i in range(m) if Counter(row[i] for row in r) == g_cols[j]] for j in range(k)]
    if any(not c for c in candidates):
        return False
    target = Counter(g)

    def assign(j, used):
        if j == k:
            return [tuple(row[i] for i in used) for row in r]
        for i in candidates[j]:
            if i not in used:
                projected = assign(j + 1, used + [i])
                if projected is not None and Counter(projected) == target:
                    return projected
        return None

    return assign(0, []) is not None


def golden_values_in_answer(golden_columns, golden_rows, answer: str, cap: int = 40) -> tuple[bool, list[str]]:
    """Deterministic answer-correctness check: every golden value appears, formatted as users see it."""
    text = answer.replace(",", "").lower()
    missing = []
    for row in golden_rows[:cap]:
        for col, value in zip(golden_columns, row):
            if value is None or isinstance(value, bool):
                continue
            shown = F.format_value(value, col["type"], col["name"])
            candidates = {str(shown).replace(",", "").lower()}
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                candidates |= {str(int(value)) if float(value).is_integer() else f"{value:g}"}
                if value == 0:
                    candidates |= {"no ", "none", "not ", "zero"}
            if not any(c in text for c in candidates):
                missing.append(f"{col['name']}={shown}")
    return (not missing), missing
