"""Database connections for each OutageIQ role. Credentials come from .env only."""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

ROLES = ("owner", "indexer", "reader")


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value


def connect(role: str, sslmode: str | None = None) -> psycopg.Connection:
    """Open a connection as one of ROLES. SSL is required unless a test overrides it."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    prefix = f"OUTAGEIQ_{role.upper()}"
    return psycopg.connect(
        host=_require("PGHOST"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=_require("PGDATABASE"),
        user=_require(f"{prefix}_USER"),
        password=_require(f"{prefix}_PASSWORD"),
        sslmode=sslmode or os.environ.get("PGSSLMODE", "require"),
        connect_timeout=10,
    )
