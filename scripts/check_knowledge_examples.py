"""Run every example SQL in the knowledge file against the database as outageiq_reader.

Run: python -m scripts.check_knowledge_examples
A broken example (wrong column, bad join) must never be embedded, so this is a gate.
0 rows is allowed (some examples can legitimately be empty) but is printed so you can judge.
"""
from common.db import connect
from common.knowledge import load_sections


def main() -> int:
    examples = [s for s in load_sections() if s.meta.get("type") == "example"]
    failures = 0
    with connect("reader") as conn:
        for s in examples:
            for sql in s.sql_blocks:
                try:
                    rows = conn.execute(sql).fetchall()
                    print(f"[ OK ] {len(rows):>4} rows  {s.heading}")
                except Exception as e:
                    conn.rollback()
                    failures += 1
                    print(f"[FAIL] {s.heading}: {type(e).__name__}: {str(e).splitlines()[0]}")
    print(f"\n{len(examples) - failures}/{len(examples)} examples executed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
