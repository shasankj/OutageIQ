-- 03_roles.sql  (safe to re-run)
-- Run as your RDS ADMIN user, connected to the `outageiq` database.
-- Replace each CHANGE_ME_* password before running (do NOT commit the edited file).
-- A role that already exists is left as is (its password is NOT changed). To change a
-- password later: ALTER ROLE <name> PASSWORD '...';
-- Grants are in 04_grants.sql.

DO $$
BEGIN
  -- 1. outageiq_app becomes outageiq_owner (DDL + data loading only).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outageiq_app')
     AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outageiq_owner') THEN
    ALTER ROLE outageiq_app RENAME TO outageiq_owner;
  END IF;

  -- 2. Writer for embeddings (rag schema only).
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outageiq_indexer') THEN
    CREATE ROLE outageiq_indexer LOGIN PASSWORD 'CHANGE_ME_INDEXER';
  END IF;

  -- 3. Read-only role for the agent / retriever / MCP.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outageiq_reader') THEN
    CREATE ROLE outageiq_reader LOGIN PASSWORD 'CHANGE_ME_READER';
  END IF;

  -- 4. Read-only role for your colleague's app.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'outageiq_colleague_ro') THEN
    CREATE ROLE outageiq_colleague_ro LOGIN PASSWORD 'CHANGE_ME_COLLEAGUE';
  END IF;
END
$$;

ALTER ROLE outageiq_colleague_ro CONNECTION LIMIT 5;

-- CONNECT on outageiq only (PUBLIC can still connect to your other databases; untouched).
GRANT CONNECT ON DATABASE outageiq TO outageiq_indexer, outageiq_reader, outageiq_colleague_ro;

-- Session defaults. Readers: read-only transactions and a 30 s statement timeout.
-- (default_transaction_read_only is a guardrail, not a security boundary: the real
-- boundary is that these roles only hold SELECT.)
ALTER ROLE outageiq_reader       IN DATABASE outageiq SET default_transaction_read_only = on;
ALTER ROLE outageiq_reader       IN DATABASE outageiq SET statement_timeout = '30s';
ALTER ROLE outageiq_colleague_ro IN DATABASE outageiq SET default_transaction_read_only = on;
ALTER ROLE outageiq_colleague_ro IN DATABASE outageiq SET statement_timeout = '30s';
ALTER ROLE outageiq_indexer      IN DATABASE outageiq SET statement_timeout = '60s';

ALTER ROLE outageiq_indexer      IN DATABASE outageiq SET search_path = rag, public;
ALTER ROLE outageiq_reader       IN DATABASE outageiq SET search_path = ops, rag, public;
ALTER ROLE outageiq_colleague_ro IN DATABASE outageiq SET search_path = ops, rag, public;
