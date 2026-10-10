"""Apply db/migrations/NNNN_name.sql in order (docs/adr/0002). Run: python -m scripts.migrate

Connects as outageiq_owner. Each migration runs in its own transaction and is recorded in
public.schema_migrations with a checksum; editing an applied file is an error.
"""
import hashlib
from pathlib import Path

from common.db import connect

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def main() -> int:
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    with connect("owner") as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations ("
            " version text PRIMARY KEY, checksum text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        applied = dict(conn.execute("SELECT version, checksum FROM public.schema_migrations").fetchall())

        for path in files:
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    print(f"ERROR: {path.name} was changed after being applied. Add a new migration instead.")
                    return 1
                print(f"skip   {path.name}")
                continue
            try:
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO public.schema_migrations (version, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                print(f"FAILED {path.name} (rolled back)")
                raise
            print(f"apply  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
