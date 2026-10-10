"""Smoke test: connects as each role and checks the security setup.

Run from the repo root:  python -m scripts.check_connection
Prints no secrets. Creates nothing (the one write attempt is expected to fail).
"""
import psycopg

from common.db import ROLES, connect


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> int:
    results = []

    for role in ROLES:
        try:
            with connect(role) as conn:
                user, ssl = conn.execute(
                    "SELECT current_user, "
                    "(SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid())"
                ).fetchone()
            results.append(check(f"{role}: connects with TLS", ssl is True, f"user={user}"))
        except Exception as e:
            results.append(check(f"{role}: connects with TLS", False, type(e).__name__))

    # TLS must be enforced by the server: a plaintext connection has to be rejected.
    try:
        connect("reader", sslmode="disable").close()
        results.append(check("server rejects non-TLS connections", False, "plaintext was accepted"))
    except psycopg.OperationalError:
        results.append(check("server rejects non-TLS connections", True))

    # The reader must not be able to write, even after turning off the read-only default.
    try:
        with connect("reader") as conn:
            conn.execute("SET default_transaction_read_only = off")
            # The SET only applies to the NEXT transaction (psycopg already opened one),
            # so commit to start a fresh read-write one before testing privileges.
            conn.commit()
            try:
                conn.execute("CREATE TABLE ops.should_fail (x int)")
                results.append(check("reader cannot CREATE tables", False, "CREATE succeeded"))
            except psycopg.errors.InsufficientPrivilege:
                results.append(check("reader cannot CREATE tables", True, "permission denied"))
    except Exception as e:
        results.append(check("reader cannot CREATE tables", False, type(e).__name__))

    # The indexer must not see the ops schema.
    try:
        with connect("indexer") as conn:
            (has_ops,) = conn.execute("SELECT has_schema_privilege('ops', 'USAGE')").fetchone()
        results.append(check("indexer has no access to ops", has_ops is False))
    except Exception as e:
        results.append(check("indexer has no access to ops", False, type(e).__name__))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
