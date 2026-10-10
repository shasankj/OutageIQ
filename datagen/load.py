"""Load the synthetic data into ops.* as outageiq_owner. Run: python -m datagen.load

Re-runnable: truncates the ops data tables first (never touches other schemas or databases),
loads everything in ONE transaction, resets identity sequences, writes data/manifest.json.
"""
import json
from datetime import datetime
from pathlib import Path

from common.db import connect
from datagen.generate import generate

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest.json"
TABLES_WITH_IDENTITY = {  # table -> identity column (outage_root_causes has none)
    "sites": "site_id", "users": "user_id", "root_causes": "root_cause_id", "outages": "outage_id",
    "alarms": "alarm_id", "outage_updates": "outage_update_id", "tickets": "ticket_id",
    "ticket_assignments": "ticket_assignment_id", "impacted_services": "impacted_service_id",
}


def main() -> int:
    tables, manifest = generate()
    with connect("owner") as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(f"ops.{t}" for t in tables) + " RESTART IDENTITY CASCADE")
        for name, rows in tables.items():  # dict order is foreign-key order
            columns = list(rows[0])
            with cur.copy(f"COPY ops.{name} ({', '.join(columns)}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row([row[c] for c in columns])
            print(f"loaded {len(rows):>6} rows into ops.{name}")
        for name, column in TABLES_WITH_IDENTITY.items():
            cur.execute(f"SELECT setval(pg_get_serial_sequence('ops.{name}', '{column}'), "
                        f"(SELECT max({column}) FROM ops.{name}))")
        conn.commit()

    MANIFEST_PATH.parent.mkdir(exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=lambda o: o.isoformat()
                                        if isinstance(o, datetime) else str(o)))
    print(f"wrote {MANIFEST_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
