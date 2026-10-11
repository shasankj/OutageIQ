"""Run every golden SQL as outageiq_reader and show what it returns.

Run: python -m scripts.check_golden
Use it to confirm each golden answer is what you intend: not accidentally empty, not a tie that
makes 'top 1' ambiguous. Golden SQL that returns 0 rows is only right for behavior=not_found.
"""
from common.db import connect
from evals.golden import load_golden


def main() -> int:
    bad = 0
    with connect("reader") as conn:
        for q in load_golden():
            if q["golden_sql"] is None:
                print(f"[ -- ] {q['id']} {q['behavior']:<9} (no SQL) {q['question']}")
                continue
            rows = conn.execute(q["golden_sql"]).fetchall()
            expected_empty = q["behavior"] == "not_found"
            ok = (len(rows) == 0) == expected_empty
            bad += not ok
            preview = str(rows[0])[:70] if rows else "-"
            print(f"[{' OK ' if ok else 'WARN'}] {q['id']} {len(rows):>3} rows  {preview}")
    print(f"\n{bad} warnings")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
